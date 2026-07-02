from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.app.config import get_settings
from backend.app.deps import db_session, require_role
from backend.app.models import BatchCell, Evaluation, Job, Prediction, User
from backend.app.schemas import JobOut, JobQualityOut
from backend.app.services.framework_log import eval_log_files, infer_log_files
from backend.app.services.quality import compute_eval_quality


router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])


def _resolve_eval_prediction(db: Session, job: Job) -> Prediction | None:
    """按 worker._run_eval 同样的优先级定位 eval job 评的那条 prediction。

    用于运行中（produces_evaluation_id 尚未写库）也能定位框架日志目录。
    """
    params = job.params_json or {}
    sid = params.get("source_prediction_id")
    if sid:
        return db.get(Prediction, sid)
    if job.dependency_job_id:
        dep = db.get(Job, job.dependency_job_id)
        if dep and dep.produces_prediction_id:
            return db.get(Prediction, dep.produces_prediction_id)
    if job.batch_id:
        cell = db.get(BatchCell, (job.batch_id, job.model_id, job.task_id))
        if cell and cell.current_prediction_id:
            return db.get(Prediction, cell.current_prediction_id)
    return None


def _collect_framework_log(db: Session, job: Job) -> str | None:
    """收集 ais_bench 框架内部产生的 .out/.log 日志，拼接成一段文本。

    - infer job → prediction.output_task_id → outputs/<otid>/details/**/logs/infer/**/*.out
    - eval  job → prediction.output_task_id + eval_version → outputs/<otid>/<ver>/logs/**/*.out
    eval 运行中 produces_evaluation_id 尚未写库，回退到与 worker 一致的 prediction
    定位方式 + params_json.eval_version，保证"测评任务进行时"也能看到框架日志。
    定位不到（如尚未产出 / failed）时返回 None。
    """
    ws = get_settings().workspace_dir
    outputs = ws / "outputs"
    files: list = []

    if job.type == "infer":
        otid = None
        if job.produces_prediction_id:
            p = db.get(Prediction, job.produces_prediction_id)
            otid = p.output_task_id if p else None
        if not otid:
            otid = (job.params_json or {}).get("output_task_id")
        if otid:
            files = infer_log_files(ws, otid)
    else:  # eval
        otid, ver = None, None
        if job.produces_evaluation_id:  # 已完成：直接读评测记录
            e = db.get(Evaluation, job.produces_evaluation_id)
            if e:
                ver = e.eval_version
                p = db.get(Prediction, e.prediction_id) if e.prediction_id else None
                otid = p.output_task_id if p else None
        if not (otid and ver):  # 运行中 / 未写库：回退解析
            ver = ver or (job.params_json or {}).get("eval_version", "eval_init")
            p = _resolve_eval_prediction(db, job)
            otid = otid or (p.output_task_id if p else None)
        if otid and ver:
            files = eval_log_files(ws, otid, ver)

    if not files:
        return None
    parts = []
    for f in files:
        try:
            txt = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        parts.append(f"===== {f.relative_to(outputs)} =====\n{txt}")
    return "\n\n".join(parts) if parts else None


@router.get("", response_model=list[JobOut])
def list_(db: Session = Depends(db_session),
          batch_id: int | None = Query(None),
          status: str | None = Query(None),
          _: User = Depends(require_role("viewer", "operator", "admin"))):
    q = db.query(Job)
    if batch_id is not None:
        q = q.filter_by(batch_id=batch_id)
    if status is not None:
        q = q.filter_by(status=status)
    return q.order_by(Job.id.desc()).limit(200).all()


@router.get("/{jid}", response_model=JobOut)
def get(jid: int,
        db: Session = Depends(db_session),
        _: User = Depends(require_role("viewer", "operator", "admin"))):
    j = db.get(Job, jid)
    if not j:
        raise HTTPException(status_code=404, detail=f"Job {jid} not found")
    return j


@router.get("/{jid}/log")
def get_log(jid: int,
            db: Session = Depends(db_session),
            _: User = Depends(require_role("viewer", "operator", "admin"))):
    j = db.get(Job, jid)
    if not j:
        raise HTTPException(status_code=404, detail=f"Job {jid} not found")
    if not j.log_path:
        raise HTTPException(status_code=404, detail="No log available")
    try:
        content = open(j.log_path, encoding="utf-8", errors="replace").read()
    except OSError:
        raise HTTPException(status_code=404, detail="Log file not found")
    return {"log": content, "log_path": j.log_path}


@router.get("/{jid}/framework-log")
def get_framework_log(jid: int,
                      db: Session = Depends(db_session),
                      _: User = Depends(require_role("viewer", "operator", "admin"))):
    """ais_bench 框架内部运行日志（比执行日志更细）。"""
    j = db.get(Job, jid)
    if not j:
        raise HTTPException(status_code=404, detail=f"Job {jid} not found")
    content = _collect_framework_log(db, j)
    if content is None:
        return {"log": "", "available": False}
    return {"log": content, "available": True}


@router.get("/{jid}/quality", response_model=JobQualityOut)
def get_quality(jid: int,
                db: Session = Depends(db_session),
                _: User = Depends(require_role("viewer", "operator", "admin"))):
    """执行质量：该 eval 任务每条样本中"好"的占比（非空输出且解析成功）。"""
    j = db.get(Job, jid)
    if not j:
        raise HTTPException(status_code=404, detail=f"Job {jid} not found")
    if j.type != "eval" or not j.produces_evaluation_id:
        return JobQualityOut(available=False)
    ev = db.get(Evaluation, j.produces_evaluation_id)
    stats = compute_eval_quality(ev.details_path if ev else None, sample_limit=10)
    if stats is None:
        return JobQualityOut(available=False)
    return JobQualityOut(available=True, **stats)


@router.post("/{jid}/cancel")
def cancel(jid: int,
           db: Session = Depends(db_session),
           _: User = Depends(require_role("operator", "admin"))):
    j = db.get(Job, jid)
    if not j:
        raise HTTPException(status_code=404, detail=f"Job {jid} not found")
    if j.status not in ("pending", "running"):
        raise HTTPException(400, f"Cannot cancel job with status {j.status}")
    import subprocess
    if j.pid:
        try:
            subprocess.run(["docker", "kill", f"eval-{jid}-infer"],
                           capture_output=True)
            subprocess.run(["docker", "kill", f"eval-{jid}-judge"],
                           capture_output=True)
        except Exception:
            pass
    j.status = "cancelled"
    j.error_msg = "Cancelled by user"
    db.commit()
    return {"status": "cancelled", "job_id": jid}
