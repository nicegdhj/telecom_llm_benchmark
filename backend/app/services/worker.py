import asyncio
import logging
import subprocess
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from backend.app.config import get_settings
from backend.app.db import get_session
from backend.app.models import (
    Batch, BatchCell, DatasetVersion, Evaluation, Job, JudgeLLM, Model, Prediction, Task,
)
from backend.app.services.batch_service import record_revision
from backend.app.services.docker_runner import (
    build_eval_cmd, build_infer_cmd, write_env_file,
)
from backend.app.services.scan import scan_eval_output, scan_infer_output

logger = logging.getLogger(__name__)


def _pick_next_job(db: Session) -> Job | None:
    """选取下一个可执行的 pending job，超出 Model 并发配额的会被跳过。"""
    q = db.query(Job).filter(Job.status == "pending")
    dirty = False
    for job in q.order_by(Job.id).all():
        if job.dependency_job_id:
            dep = db.get(Job, job.dependency_job_id)
            # 依赖已终结但非 success：直接把当前 job 标 failed，避免永远 pending
            if dep is not None and dep.status in ("failed", "cancelled", "timeout"):
                job.status = "failed"
                job.error_msg = f"dependency job {dep.id} {dep.status}"
                job.finished_at = datetime.utcnow()
                dirty = True
                continue
            if dep is None or dep.status != "success":
                continue
        # 检查 Model 并发配额（I1）
        model = db.get(Model, job.model_id)
        if model:
            running_count = (
                db.query(Job)
                .filter_by(model_id=job.model_id, status="running")
                .count()
            )
            if running_count >= model.concurrency:
                continue
        if dirty:
            db.commit()
        return job
    if dirty:
        db.commit()
    return None


def _env_vars_for_model(model: Model) -> dict[str, str]:
    key = model.model_config_key or "local_qwen"
    base = {"PYTHONUNBUFFERED": "1"}
    if key == "local_qwen":
        return {**base,
                "LOCAL_MODEL_NAME": model.model_name or "",
                "LOCAL_HOST_IP":    model.host or "",
                "LOCAL_HOST_PORT":  str(model.port or ""),
                "LOCAL_CONCURRENCY": str(model.concurrency)}
    elif key == "maas_gateway":
        return {**base,
                "MAAS_MODEL":       model.model_name or "",
                "MAAS_API_KEY":     model.api_key or "",
                "MAAS_HOST_IP":     model.host or "",
                "MAAS_HOST_PORT":   str(model.port or ""),
                "MAAS_URL":         model.url or "",
                "MAAS_CONCURRENCY": str(model.concurrency)}
    elif key == "common_gateway":
        return {**base,
                "COMMON_MODEL_NAME":   model.model_name or "",
                "COMMON_API_KEY":      model.api_key or "",
                "COMMON_URL":          model.url or "",
                "COMMON_CONCURRENCY":  str(model.concurrency)}

    else:
        # 未知 config_key：原样透传通用字段，让容器自行处理
        return {**base,
                "LOCAL_MODEL_NAME": model.model_name or "",
                "LOCAL_HOST_IP":    model.host or "",
                "LOCAL_HOST_PORT":  str(model.port or ""),
                "LOCAL_CONCURRENCY": str(model.concurrency)}


def _make_output_task_id(job: Job) -> str:
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    return f"batch{job.batch_id}_m{job.model_id}_t{job.task_id}_{ts}"


def _next_version_label(db: Session, kind: str, batch_id: int | None,
                        model_id: int, task_id: int) -> str:
    """计算 cell 内下一个 version_label。

    kind: 'infer' 或 'score'。同 cell 内按现有数量+1 累加。
    无 batch_id（独立 job）时退化为 "v1_infer"，不参与 cell 编号。
    """
    if batch_id is None:
        return f"v1_{kind}"
    if kind == "infer":
        n = (db.query(Prediction)
             .join(Job, Job.id == Prediction.job_id)
             .filter(Job.batch_id == batch_id,
                     Prediction.model_id == model_id,
                     Prediction.task_id == task_id)
             .count())
    else:
        n = (db.query(Evaluation)
             .join(Job, Job.id == Evaluation.job_id)
             .filter(Job.batch_id == batch_id,
                     Job.model_id == model_id,
                     Job.task_id == task_id)
             .count())
    return f"v{n + 1}_{kind}"


async def _run_infer(db: Session, job: Job, settings):
    """异步执行推理 job，scan 异常时自动将 job 置为 failed（防止卡 running）。"""
    env_file = None
    dv = None
    try:
        model = db.get(Model, job.model_id)
        task = db.get(Task, job.task_id)

        output_task_id = _make_output_task_id(job)

        # 统一提取当前任务关联的已上传数据集版本 (无论 custom 还是 generic 任务)
        cell = db.get(BatchCell, (job.batch_id, job.model_id, job.task_id)) if job.batch_id else None
        dv_id = (cell.dataset_version_id if cell and cell.dataset_version_id else None)
        if dv_id is not None:
            dv = db.get(DatasetVersion, dv_id)
        else:
            # 优先取 is_default，否则取最新上传的版本
            dv = (db.query(DatasetVersion)
                  .filter_by(task_id=job.task_id, is_default=True)
                  .first()
                  or db.query(DatasetVersion)
                     .filter_by(task_id=job.task_id)
                     .order_by(DatasetVersion.uploaded_at.desc())
                     .first())

        if dv:
            # 如果有已上传的数据集版本，一律将其作为 custom 任务读取和运行
            src = settings.workspace_dir / dv.data_path
            dst = settings.workspace_dir / "data" / "custom_task" / f"task_{task.id}.jsonl"
            dst.parent.mkdir(parents=True, exist_ok=True)
            if dst.is_symlink() or dst.exists():
                dst.unlink()
            # 使用相对路径软链，确保容器内挂载后也能解析
            import os
            rel = os.path.relpath(src.resolve(), dst.parent)
            dst.symlink_to(rel)
            logger.info("dataset symlink (unified): %s -> %s", dst, rel)

            run_task_type = "custom"
            run_custom_task_num = task.id
            run_suite_name = f"task_{task.id}_suite"
        else:
            # 如果没有已上传版本且原本为 custom 任务，则报错（因为 custom 任务必须有上传数据集）
            if task.type == "custom":
                raise RuntimeError(
                    f"Task {task.key} has no dataset version, please upload data first"
                )
            # 如果没有已上传版本且为 generic 任务，则退回使用其内置测试集
            run_task_type = task.type
            run_custom_task_num = task.custom_task_num
            run_suite_name = task.suite_name

        env_file = write_env_file(settings, job.id, _env_vars_for_model(model))
        cmd = build_infer_cmd(
            settings=settings, job_id=job.id, env_file=env_file,
            output_task_id=output_task_id,
            model_config_key=model.model_config_key,
            model_name=model.model_name,
            concurrency=model.concurrency,
            task_type=run_task_type,
            custom_task_num=run_custom_task_num,
            suite_name=run_suite_name,
        )

        log_path = settings.logs_dir / f"task_{job.batch_id}_job_{job.id}.log"
        settings.logs_dir.mkdir(parents=True, exist_ok=True)

        job.params_json = {**(job.params_json or {}), "output_task_id": output_task_id}
        job.status = "running"
        job.started_at = datetime.utcnow()
        job.log_path = str(log_path)
        db.commit()

        with open(log_path, "wb") as lf:
            proc = subprocess.Popen(cmd, stdout=lf, stderr=subprocess.STDOUT)
            job.pid = proc.pid
            db.commit()
            loop = asyncio.get_event_loop()
            returncode = await loop.run_in_executor(None, proc.wait)

        job.returncode = returncode
        job.finished_at = datetime.utcnow()

        if returncode == 0:
            info = scan_infer_output(settings, output_task_id, run_suite_name)
            label = _next_version_label(db, "infer", job.batch_id, job.model_id, job.task_id)
            pred = Prediction(
                model_id=job.model_id, task_id=job.task_id,
                dataset_version_id=dv.id if dv else None,
                status="success",
                output_task_id=output_task_id,
                output_path=info["output_path"],
                num_samples=info["num_samples"],
                duration_sec=(job.finished_at - job.started_at).total_seconds(),
                job_id=job.id, finished_at=job.finished_at,
                version_label=label,
            )
            db.add(pred)
            db.flush()
            job.produces_prediction_id = pred.id
            job.version_label = label
            job.status = "success"

            if job.batch_id:
                cell = db.get(BatchCell, (job.batch_id, job.model_id, job.task_id))
                if cell:
                    cell.current_prediction_id = pred.id
                    record_revision(
                        db, job.batch_id, "infer_done",
                        f"prediction {pred.id} for model={job.model_id} task={job.task_id}",
                    )
        else:
            job.status = "failed"
        db.commit()

    except Exception as e:
        logger.exception("infer job %d failed", job.id)
        job.status = "failed"
        job.error_msg = str(e)
        try:
            db.commit()
        except Exception:
            pass
        raise
    finally:
        if env_file and env_file.exists():
            env_file.unlink(missing_ok=True)


def _env_vars_for_judge(judge: JudgeLLM) -> dict[str, str]:
    key = judge.judge_config_key or "local_judge"
    concurrency = str(judge.concurrency or 5)
    if key == "local_judge":
        return {
            "SCORE_MODEL_NAME":      judge.model_name or "",
            "SCORE_HOST_IP":         judge.host or "",
            "SCORE_HOST_PORT":       str(judge.port or ""),
            "SCORE_LLM_CONCURRENCY": concurrency,
            "SCORE_MODEL_TYPE":      "maas",
        }
    else:  # api_judge
        return {
            "SCORE_MODEL_NAME":      judge.model_name or "",
            "SCORE_API_KEY":         judge.api_key or "",
            "SCORE_URL":             judge.url or "",
            "SCORE_LLM_CONCURRENCY": concurrency,
            "SCORE_MODEL_TYPE":      judge.score_model_type or "maas",
        }


async def _run_eval(db: Session, job: Job, settings):
    """异步执行评测 job，scan 异常时自动将 job 置为 failed。

    优先级取 prediction：
    1) job.params_json.source_prediction_id（cell 单元 eval-only 强制指定）
    2) job.dependency_job_id 对应 infer 产物
    3) BatchCell.current_prediction_id
    """
    env_file = None
    try:
        params = job.params_json or {}
        source_pid = params.get("source_prediction_id")
        if source_pid:
            prediction = db.get(Prediction, source_pid)
        elif job.dependency_job_id:
            dep = db.get(Job, job.dependency_job_id)
            prediction = db.get(Prediction, dep.produces_prediction_id)
        else:
            cell = db.get(BatchCell, (job.batch_id, job.model_id, job.task_id))
            prediction = db.get(Prediction, cell.current_prediction_id) if cell else None
        if not prediction:
            job.status = "failed"
            job.error_msg = "no prediction to evaluate"
            db.commit()
            return

        model = db.get(Model, job.model_id)
        task = db.get(Task, job.task_id)
        eval_version = job.params_json.get("eval_version", "eval_init")

        # 合并 judge 的 SCORE_* 环境变量
        judge_env: dict[str, str] = {}
        batch = db.get(Batch, job.batch_id) if job.batch_id else None
        if batch and batch.default_judge_id:
            judge = db.get(JudgeLLM, batch.default_judge_id)
            if judge:
                judge_env = _env_vars_for_judge(judge)

        env_file = write_env_file(settings, job.id, {**_env_vars_for_model(model), **judge_env})

        # 判断此次推理是不是使用了上传的数据集版本
        if prediction.dataset_version_id is not None:
            run_task_type = "custom"
            run_suite_name = f"task_{task.id}_suite"
        else:
            run_task_type = task.type
            run_suite_name = task.suite_name

        cmd = build_eval_cmd(
            settings=settings, job_id=job.id, env_file=env_file,
            output_task_id=prediction.output_task_id,
            eval_version=eval_version,
            suite_name=run_suite_name,
            task_type=run_task_type,
        )

        log_path = settings.logs_dir / f"task_{job.batch_id}_job_{job.id}.log"
        job.status = "running"
        job.started_at = datetime.utcnow()
        job.log_path = str(log_path)
        db.commit()

        with open(log_path, "wb") as lf:
            proc = subprocess.Popen(cmd, stdout=lf, stderr=subprocess.STDOUT)
            job.pid = proc.pid
            db.commit()
            loop = asyncio.get_event_loop()
            returncode = await loop.run_in_executor(None, proc.wait)

        job.returncode = returncode
        job.finished_at = datetime.utcnow()

        if returncode == 0:
            info = scan_eval_output(settings, prediction.output_task_id, eval_version,
                                   run_suite_name)
            label = _next_version_label(db, "score", job.batch_id, job.model_id, job.task_id)
            ev = Evaluation(
                prediction_id=prediction.id, eval_version=eval_version,
                status="success", accuracy=info["accuracy"],
                details_path=info["details_path"],
                num_samples=info["num_samples"],
                duration_sec=(job.finished_at - job.started_at).total_seconds(),
                job_id=job.id, finished_at=job.finished_at,
                version_label=label,
            )
            db.add(ev)
            db.flush()
            job.produces_evaluation_id = ev.id
            job.version_label = label
            job.status = "success"

            if job.batch_id:
                cell = db.get(BatchCell, (job.batch_id, job.model_id, job.task_id))
                if cell:
                    cell.current_evaluation_id = ev.id
                    record_revision(
                        db, job.batch_id, "eval_done",
                        f"evaluation {ev.id} for model={job.model_id} task={job.task_id}",
                    )
        else:
            job.status = "failed"
        db.commit()

    except Exception as e:
        logger.exception("eval job %d failed", job.id)
        job.status = "failed"
        job.error_msg = str(e)
        try:
            db.commit()
        except Exception:
            pass
        raise
    finally:
        if env_file and env_file.exists():
            env_file.unlink(missing_ok=True)


async def run_pending_jobs_once():
    settings = get_settings()
    job_id = None
    with get_session() as db:
        global_running = db.query(Job).filter_by(status="running").count()
        if global_running >= settings.default_job_concurrency:
            return
        job = _pick_next_job(db)
        if not job:
            return
        job_id = job.id
    with get_session() as db:
        job = db.get(Job, job_id)
        if job.type == "infer":
            await _run_infer(db, job, settings)
        else:
            await _run_eval(db, job, settings)


async def worker_loop():
    settings = get_settings()
    while True:
        try:
            await run_pending_jobs_once()
        except Exception as e:
            logger.exception("worker loop error")
        await asyncio.sleep(settings.worker_poll_interval_sec)
