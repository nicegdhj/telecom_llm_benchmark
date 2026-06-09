from sqlalchemy.orm import Session

from backend.app.models import (
    Batch, BatchCell, BatchRevision, Evaluation, Job, Model, Prediction, Task,
)


def _snapshot(db: Session, batch_id: int) -> dict:
    cells = db.query(BatchCell).filter_by(batch_id=batch_id).all()
    return {
        "cells": [
            {
                "model_id": c.model_id,
                "task_id": c.task_id,
                "dataset_version_id": c.dataset_version_id,
                "current_prediction_id": c.current_prediction_id,
                "current_evaluation_id": c.current_evaluation_id,
            }
            for c in cells
        ]
    }


def _next_rev_num(db: Session, batch_id: int) -> int:
    last = (
        db.query(BatchRevision.rev_num)
        .filter_by(batch_id=batch_id)
        .order_by(BatchRevision.rev_num.desc())
        .first()
    )
    return (last[0] + 1) if last else 1


def record_revision(
    db: Session, batch_id: int, change_type: str, change_summary: str,
    actor_user_id: int | None = None
):
    """
    记录 BatchRevision 快照。

    **调用顺序要求**：调用方须在修改 BatchCell 指针后（db.flush 后）、
    db.commit 前调用本函数。_snapshot 读取的是 session 内当前 cell 状态，
    而非数据库已提交状态。勿在 cell 修改前调用，否则快照不准确。
    """
    rev = BatchRevision(
        batch_id=batch_id,
        rev_num=_next_rev_num(db, batch_id),
        change_type=change_type,
        change_summary=change_summary,
        snapshot_json=_snapshot(db, batch_id),
        actor_user_id=actor_user_id,
    )
    db.add(rev)


def rerun_batch(db: Session, batch_id: int, payload,
                actor_user_id: int | None = None) -> list[Job]:
    """为 batch 的指定子集创建新 jobs，返回新创建的 job 列表。"""
    batch = db.get(Batch, batch_id)
    if not batch:
        raise ValueError("batch not found")

    jobs_created = []
    for mid in payload.model_ids:
        for tid in payload.task_ids:
            cell = db.get(BatchCell, (batch_id, mid, tid))
            if not cell:
                raise ValueError(f"cell not found for model={mid} task={tid}")

            if payload.dataset_version_id is not None:
                cell.dataset_version_id = payload.dataset_version_id

            infer_job = None
            if payload.what in ("infer", "both"):
                infer_job = Job(
                    type="infer", batch_id=batch_id,
                    model_id=mid, task_id=tid,
                    params_json={},
                    created_by_user_id=actor_user_id,
                )
                db.add(infer_job)
                db.flush()
                jobs_created.append(infer_job)

            if payload.what in ("eval", "both"):
                dep_id = infer_job.id if infer_job else None
                # eval-only 时尝试用现有 prediction 作为依赖
                if payload.what == "eval" and cell.current_prediction_id:
                    # eval job 不需要 infer job 依赖，但需要 prediction 存在
                    # 这里保持和 create_batch 相同的结构：eval job 的 dependency 指向 infer
                    # 但 rerun 中 infer 可能不存在，所以 dependency_job_id 设为 None
                    dep_id = None

                eval_job = Job(
                    type="eval", batch_id=batch_id,
                    model_id=mid, task_id=tid,
                    params_json={"eval_version": batch.default_eval_version},
                    dependency_job_id=dep_id,
                    created_by_user_id=actor_user_id,
                )
                db.add(eval_job)
                db.flush()
                jobs_created.append(eval_job)

    batch.last_modified_by_user_id = actor_user_id
    record_revision(
        db, batch_id, "rerun",
        f"rerun {payload.what} for models={payload.model_ids} tasks={payload.task_ids}",
        actor_user_id=actor_user_id,
    )
    return jobs_created


def create_batch(db: Session, payload,
                 actor_user_id: int | None = None) -> Batch:
    # 校验 model/task 存在
    models = db.query(Model).filter(Model.id.in_(payload.model_ids)).all()
    if len(models) != len(payload.model_ids):
        raise ValueError("some model_id not found")
    tasks = db.query(Task).filter(Task.id.in_(payload.task_ids)).all()
    if len(tasks) != len(payload.task_ids):
        raise ValueError("some task_id not found")

    batch = Batch(
        name=payload.name,
        mode=payload.mode,
        default_eval_version=payload.default_eval_version,
        default_judge_id=payload.default_judge_id,
        notes=payload.notes,
        created_by_user_id=actor_user_id,
        last_modified_by_user_id=actor_user_id,
    )
    db.add(batch)
    db.flush()

    # 生成 N×M 个 cells
    for m in models:
        for t in tasks:
            dv_id = None
            if getattr(payload, "task_version_map", None) and t.id in payload.task_version_map:
                dv_id = payload.task_version_map[t.id]
            db.add(BatchCell(
                batch_id=batch.id, model_id=m.id, task_id=t.id,
                dataset_version_id=dv_id,
            ))
    db.flush()

    # 生成 jobs
    for m in models:
        for t in tasks:
            infer_job = None
            if payload.mode in ("infer", "all"):
                infer_job = Job(
                    type="infer", batch_id=batch.id,
                    model_id=m.id, task_id=t.id,
                    params_json={},
                    created_by_user_id=actor_user_id,
                )
                db.add(infer_job)
                db.flush()
            if payload.mode in ("eval", "all"):
                eval_job = Job(
                    type="eval", batch_id=batch.id,
                    model_id=m.id, task_id=t.id,
                    params_json={"eval_version": batch.default_eval_version},
                    dependency_job_id=infer_job.id if infer_job else None,
                    created_by_user_id=actor_user_id,
                )
                db.add(eval_job)

    record_revision(db, batch.id, "create", f"create batch '{batch.name}'",
                    actor_user_id=actor_user_id)
    return batch


def _unique_eval_version(db: Session, batch_id: int, model_id: int, task_id: int,
                          base: str) -> str:
    """若 base 已被本 cell 用过（任何状态的 Evaluation），返回 base_v2、_v3…"""
    used = set()
    rows = (
        db.query(Job.params_json)
        .filter_by(batch_id=batch_id, model_id=model_id, task_id=task_id, type="eval")
        .all()
    )
    for (p,) in rows:
        if p and isinstance(p, dict) and p.get("eval_version"):
            used.add(p["eval_version"])
    if base not in used:
        return base
    n = 2
    while f"{base}_v{n}" in used:
        n += 1
    return f"{base}_v{n}"


# ── Cell 级操作 ───────────────────────────────────────────────────────

def get_cell_detail(db: Session, batch_id: int, model_id: int, task_id: int) -> dict:
    """返回单 cell 的详情 + 历史时间线（jobs/predictions/evaluations 聚合）。"""
    cell = db.get(BatchCell, (batch_id, model_id, task_id))
    if not cell:
        raise ValueError("cell not found")

    jobs = (db.query(Job)
            .filter_by(batch_id=batch_id, model_id=model_id, task_id=task_id)
            .order_by(Job.created_at.asc(), Job.id.asc())
            .all())

    history = []
    for j in jobs:
        item = {
            "job_id": j.id,
            "kind": "infer" if j.type == "infer" else "eval",
            "status": j.status,
            "version_label": j.version_label,
            "created_at": j.created_at.isoformat() if j.created_at else None,
            "started_at": j.started_at.isoformat() if j.started_at else None,
            "finished_at": j.finished_at.isoformat() if j.finished_at else None,
            "error_msg": j.error_msg,
            "returncode": j.returncode,
            "log_path": j.log_path,
            "prediction_id": j.produces_prediction_id,
            "evaluation_id": j.produces_evaluation_id,
            "accuracy": None,
            "num_samples": None,
            "duration_sec": None,
            "based_on_infer": None,
        }
        if j.produces_prediction_id:
            p = db.get(Prediction, j.produces_prediction_id)
            if p:
                item["num_samples"] = p.num_samples
                item["duration_sec"] = p.duration_sec
        if j.produces_evaluation_id:
            e = db.get(Evaluation, j.produces_evaluation_id)
            if e:
                item["accuracy"] = e.accuracy
                item["num_samples"] = e.num_samples
                item["duration_sec"] = e.duration_sec
                src = db.get(Prediction, e.prediction_id) if e.prediction_id else None
                if src:
                    item["based_on_infer"] = src.version_label
                    item["source_prediction_id"] = src.id
        history.append(item)

    return {
        "batch_id": batch_id,
        "model_id": model_id,
        "task_id": task_id,
        "dataset_version_id": cell.dataset_version_id,
        "current_prediction_id": cell.current_prediction_id,
        "current_evaluation_id": cell.current_evaluation_id,
        "history": history,
    }


def switch_cell_pointer(db: Session, batch_id: int, model_id: int, task_id: int,
                        current_prediction_id: int | None,
                        current_evaluation_id: int | None,
                        actor_user_id: int | None = None) -> BatchCell:
    """切换 cell 当前指针，写入 BatchRevision(change_type=switch_pointer)。

    校验：
    - prediction.model_id/task_id 必须匹配该 cell
    - evaluation.prediction_id 必须是 current_prediction_id（或显式置 null）
    """
    cell = db.get(BatchCell, (batch_id, model_id, task_id))
    if not cell:
        raise ValueError("cell not found")

    prev_p = cell.current_prediction_id
    prev_e = cell.current_evaluation_id

    new_pred = None
    if current_prediction_id is not None:
        new_pred = db.get(Prediction, current_prediction_id)
        if not new_pred:
            raise ValueError("prediction not found")
        if new_pred.model_id != model_id or new_pred.task_id != task_id:
            raise ValueError("prediction does not belong to this cell")

    if current_evaluation_id is not None:
        ev = db.get(Evaluation, current_evaluation_id)
        if not ev:
            raise ValueError("evaluation not found")
        # 必须是基于即将设置的 prediction（或当前未变的 prediction）
        target_pid = current_prediction_id if current_prediction_id is not None else prev_p
        if ev.prediction_id != target_pid:
            raise ValueError("evaluation is not based on the selected prediction")

    cell.current_prediction_id = current_prediction_id
    cell.current_evaluation_id = current_evaluation_id
    db.flush()

    summary = (
        f"cell(m={model_id},t={task_id}): "
        f"infer {prev_p}→{current_prediction_id}, "
        f"score {prev_e}→{current_evaluation_id}"
    )
    record_revision(db, batch_id, "switch_pointer", summary,
                    actor_user_id=actor_user_id)
    return cell


def rerun_cell(db: Session, batch_id: int, model_id: int, task_id: int,
               what: str, source_prediction_id: int | None,
               actor_user_id: int | None = None) -> list[Job]:
    """单 cell 重跑。

    - what="infer"|"both"：source_prediction_id 必须为空，新建 infer (+eval 依赖)
    - what="eval"：source_prediction_id 必填且属于该 cell 且 status=success
    """
    if what not in ("infer", "eval", "both"):
        raise ValueError("what must be infer|eval|both")
    cell = db.get(BatchCell, (batch_id, model_id, task_id))
    if not cell:
        raise ValueError("cell not found")
    batch = db.get(Batch, batch_id)
    if not batch:
        raise ValueError("batch not found")

    if what == "eval":
        if source_prediction_id is None:
            raise ValueError("仅评分模式必须指定 source_prediction_id（推理版本）")
        p = db.get(Prediction, source_prediction_id)
        if not p or p.model_id != model_id or p.task_id != task_id:
            raise ValueError("source_prediction_id 不属于该 cell")
        if p.status != "success":
            raise ValueError("source prediction 状态必须是 success")
    else:
        if source_prediction_id is not None:
            raise ValueError("非 eval-only 模式不需要 source_prediction_id")

    jobs_created: list[Job] = []
    infer_job = None
    if what in ("infer", "both"):
        infer_job = Job(
            type="infer", batch_id=batch_id,
            model_id=model_id, task_id=task_id,
            params_json={},
            created_by_user_id=actor_user_id,
        )
        db.add(infer_job)
        db.flush()
        jobs_created.append(infer_job)

    if what in ("eval", "both"):
        # 避免 eval_init 目录与历史冲突：若已存在同名 eval_version 的成功评测，则自动加后缀
        eval_version = _unique_eval_version(
            db, batch_id, model_id, task_id, batch.default_eval_version,
        )
        params = {"eval_version": eval_version}
        if what == "eval":
            params["source_prediction_id"] = source_prediction_id
        dep_id = infer_job.id if infer_job else None
        eval_job = Job(
            type="eval", batch_id=batch_id,
            model_id=model_id, task_id=task_id,
            params_json=params,
            dependency_job_id=dep_id,
            created_by_user_id=actor_user_id,
        )
        db.add(eval_job)
        db.flush()
        jobs_created.append(eval_job)

    batch.last_modified_by_user_id = actor_user_id
    summary_tail = ""
    if what == "eval":
        summary_tail = f" (based on prediction {source_prediction_id})"
    record_revision(
        db, batch_id, "rerun_cell",
        f"rerun cell(m={model_id},t={task_id}) what={what}{summary_tail}",
        actor_user_id=actor_user_id,
    )
    return jobs_created