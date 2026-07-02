from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.app.deps import db_session, require_role
from backend.app.models import Batch, Evaluation, Job, Model, Prediction, Task, User
from backend.app.schemas import EvaluationOut, EvaluationSearchOut


router = APIRouter(prefix="/api/v1/evaluations", tags=["evaluations"])


@router.get("/search", response_model=list[EvaluationSearchOut])
def search(
    db: Session = Depends(db_session),
    eval_ids: list[int] | None = Query(None),
    model_ids: list[int] | None = Query(None),
    task_ids: list[int] | None = Query(None),
    batch_ids: list[int] | None = Query(None),
    status: str | None = Query(None),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    limit: int = Query(200, ge=1, le=1000),
    _: User = Depends(require_role("viewer", "operator", "admin")),
):
    """全库筛选 Evaluation，返回带关联字段的视图模型。"""
    q = (
        db.query(Evaluation, Prediction, Job, Model, Task, Batch)
        .join(Prediction, Prediction.id == Evaluation.prediction_id)
        .outerjoin(Job, Job.id == Evaluation.job_id)
        .outerjoin(Model, Model.id == Prediction.model_id)
        .outerjoin(Task, Task.id == Prediction.task_id)
        .outerjoin(Batch, Batch.id == Job.batch_id)
    )
    if eval_ids:
        q = q.filter(Evaluation.id.in_(eval_ids))
    if model_ids:
        q = q.filter(Prediction.model_id.in_(model_ids))
    if task_ids:
        q = q.filter(Prediction.task_id.in_(task_ids))
    if batch_ids:
        q = q.filter(Job.batch_id.in_(batch_ids))
    if status:
        q = q.filter(Evaluation.status == status)
    if date_from:
        q = q.filter(Evaluation.created_at >= date_from)
    if date_to:
        q = q.filter(Evaluation.created_at <= date_to)

    q = q.order_by(Evaluation.created_at.desc()).limit(limit)

    out: list[EvaluationSearchOut] = []
    for ev, pred, job, model, task, batch in q.all():
        out.append(EvaluationSearchOut(
            id=ev.id,
            model_id=pred.model_id,
            model_name=model.name if model else None,
            task_id=pred.task_id,
            task_key=task.key if task else None,
            batch_id=job.batch_id if job else None,
            batch_name=batch.name if batch else None,
            version_label=ev.version_label,
            status=ev.status,
            accuracy=ev.accuracy,
            num_samples=ev.num_samples,
            duration_sec=ev.duration_sec,
            eval_version=ev.eval_version,
            created_at=ev.created_at,
            finished_at=ev.finished_at,
        ))
    return out


@router.get("/{eid}", response_model=EvaluationOut)
def get(eid: int,
        db: Session = Depends(db_session),
        _: User = Depends(require_role("viewer", "operator", "admin"))):
    ev = db.get(Evaluation, eid)
    if not ev:
        raise HTTPException(status_code=404, detail=f"Evaluation {eid} not found")
    return ev
