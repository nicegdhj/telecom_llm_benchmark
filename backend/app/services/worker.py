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
from backend.app.services.framework_log import (
    detect_framework_error, eval_log_files, infer_log_files,
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
                "MAAS_AUTH_HEADER": model.auth_header or "Authorization-Gateway",
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


def resolve_run_target(task) -> tuple[str, int | None, str]:
    """决定任务跑哪个固定专属 suite（每个任务的数据路径 + 评估器算子都是固定的）。

    - custom：用 **custom_task_num**（非 DB 主键 id）命中 task_{num}_suite，
      读固定 data/custom_task/task_{num}.jsonl。用 id 会因 id≠num 跑错任务。
    - generic：用 suite_name 跑内置数据集（如 alarm_data_gen_0_shot），
      不因 init 版本被误当 custom。

    返回 (run_task_type, run_custom_task_num, run_suite_name)。
    """
    if task.type == "custom":
        if task.custom_task_num is None:
            raise RuntimeError(f"custom 任务 {task.key} 缺少 custom_task_num")
        num = task.custom_task_num
        return "custom", num, f"task_{num}_suite"
    return "generic", None, task.suite_name


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

        # 按任务类型路由到各自固定专属的 suite（数据路径 + 评估器算子）。
        run_task_type, run_custom_task_num, run_suite_name = resolve_run_target(task)
        if run_task_type == "custom":
            import os
            num = run_custom_task_num
            canonical = settings.workspace_dir / "data" / "custom_task" / f"task_{num}.jsonl"
            builtin = canonical.with_name(f"task_{num}.jsonl.builtin")
            canonical_rel = f"data/custom_task/task_{num}.jsonl"

            # init/内置版本 data_path 即固定路径本身；上传版本 data_path 指向 data/versions/...
            is_upload = dv is not None and dv.data_path.replace("\\", "/") != canonical_rel
            if is_upload:
                # 上传版本：把所选版本数据软链到固定读取路径；首次覆盖前备份内置原文件，避免丢失
                src = (settings.workspace_dir / dv.data_path).resolve()
                if canonical.exists() and not canonical.is_symlink() and not builtin.exists():
                    canonical.rename(builtin)
                if canonical.is_symlink() or canonical.exists():
                    canonical.unlink()
                canonical.parent.mkdir(parents=True, exist_ok=True)
                canonical.symlink_to(os.path.relpath(src, canonical.parent))
                logger.info("custom dataset (upload) symlink: %s -> %s", canonical, src)
            else:
                # init/内置版本：确保读到真实内置文件（若之前被上传版本软链过则还原）
                if canonical.is_symlink():
                    canonical.unlink()
                    if builtin.exists():
                        builtin.rename(canonical)
                    logger.info("custom dataset restored to builtin: %s", canonical)

            if not canonical.exists():
                raise RuntimeError(
                    f"custom 任务 {task.key} 缺少数据文件 {canonical}，请确认数据集已放置或已上传版本"
                )

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

        # 框架可能内部捕获异常仍 exit 0，需扫描框架日志兜底判失败
        fw_err = (detect_framework_error(
            infer_log_files(settings.workspace_dir, output_task_id))
            if returncode == 0 else None)

        if returncode == 0 and not fw_err:
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
            if fw_err:
                job.error_msg = f"框架执行报错：{fw_err}"
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

        # 合并 judge 的 SCORE_* 环境变量。
        # 优先用 job 参数里显式指定的 judge_id（重跑"仅评分"可换评分模型），否则用批次默认。
        judge_env: dict[str, str] = {}
        judge_id = (job.params_json or {}).get("judge_id")
        if not judge_id and job.batch_id:
            batch = db.get(Batch, job.batch_id)
            judge_id = batch.default_judge_id if batch else None
        if judge_id:
            judge = db.get(JudgeLLM, judge_id)
            if judge:
                judge_env = _env_vars_for_judge(judge)

        env_file = write_env_file(settings, job.id, {**_env_vars_for_model(model), **judge_env})

        # 评测必须与推理跑同一个固定 suite：custom 按 custom_task_num，generic 按 suite_name。
        run_task_type, _, run_suite_name = resolve_run_target(task)

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

        # 框架可能内部捕获异常仍 exit 0，需扫描框架日志兜底判失败
        fw_err = (detect_framework_error(eval_log_files(
            settings.workspace_dir, prediction.output_task_id, eval_version))
            if returncode == 0 else None)

        if returncode == 0 and not fw_err:
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
            if fw_err:
                job.error_msg = f"框架执行报错：{fw_err}"
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


# 在途的后台 job 执行任务：持有引用防 GC，并支持等待/优雅关闭
_inflight: set[asyncio.Task] = set()


async def _run_job(job_id: int, job_type: str, settings):
    """后台执行单个已领取（已置 running）的 job，使用独立 session。"""
    with get_session() as db:
        job = db.get(Job, job_id)
        if job is None:
            return
        if job_type == "infer":
            await _run_infer(db, job, settings)
        else:
            await _run_eval(db, job, settings)


def _dispatch(job_id: int, job_type: str, settings) -> asyncio.Task:
    """把一个已领取的 job 丢到后台并行执行（不阻塞调度循环）。"""
    task = asyncio.create_task(_run_job(job_id, job_type, settings))
    _inflight.add(task)

    def _done(t: asyncio.Task):
        _inflight.discard(t)
        if not t.cancelled() and t.exception() is not None:
            logger.error("job %d task crashed", job_id, exc_info=t.exception())

    task.add_done_callback(_done)
    return task


async def run_pending_jobs_once():
    """在全局并发上限内，尽量多地领取 pending job 并【并行】派发执行。

    关键：领取即把 job 置 running 并提交，使并发计数立刻准确，避免下一轮
    （或下一个 poll 周期）重复领取同一个 job。派发后不 await 其完成，
    调度循环继续填满空闲并发槽，直到达到上限或没有可执行 job。
    """
    settings = get_settings()
    while True:
        with get_session() as db:
            running = db.query(Job).filter_by(status="running").count()
            if running >= settings.default_job_concurrency:
                return
            job = _pick_next_job(db)
            if job is None:
                return
            # 领取即标 running（防并发重复领取）；started_at 先占位，
            # 具体执行函数内还会再 commit 一次 log_path 等运行态信息。
            job.status = "running"
            job.started_at = datetime.utcnow()
            jid, jtype = job.id, job.type
            db.commit()
        _dispatch(jid, jtype, settings)


async def wait_inflight():
    """等待所有在途 job 执行完（供测试与优雅关闭使用）。"""
    while _inflight:
        await asyncio.gather(*list(_inflight), return_exceptions=True)


async def worker_loop():
    settings = get_settings()
    while True:
        try:
            await run_pending_jobs_once()
        except Exception as e:
            logger.exception("worker loop error")
        await asyncio.sleep(settings.worker_poll_interval_sec)
