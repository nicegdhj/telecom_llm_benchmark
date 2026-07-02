import hashlib
import io
import json
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.config import get_settings
from backend.app.deps import db_session, require_role
from backend.app.models import DatasetVersion, Task, User
from backend.app.schemas import DatasetVersionOut, TaskOut
from backend.app.task_meta import TASK_META, TASK_ORDER


router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])


def _enrich(task: Task, dataset_count: int) -> TaskOut:
    meta = TASK_META.get(task.key, {})
    return TaskOut(
        id=task.id,
        key=task.key,
        type=task.type,
        suite_name=task.suite_name,
        display_name=task.display_name,
        custom_task_num=task.custom_task_num,
        default_data_rel_path=task.default_data_rel_path,
        is_llm_judge=task.is_llm_judge,
        created_at=task.created_at,
        alias=meta.get("alias"),
        category=meta.get("category"),
        dataset_count=dataset_count,
    )


@router.get("", response_model=list[TaskOut])
def list_(db: Session = Depends(db_session),
          _: User = Depends(require_role("viewer", "operator", "admin"))):
    # 仅展示白名单内任务（对齐 run_mixed_benchmark.sh），并按其在脚本中的顺序排序
    tasks = [t for t in db.query(Task).all() if t.key in TASK_ORDER]
    tasks.sort(key=lambda t: TASK_ORDER[t.key])
    counts = dict(
        db.query(DatasetVersion.task_id, func.count())
        .group_by(DatasetVersion.task_id)
        .all()
    )
    return [_enrich(t, counts.get(t.id, 0)) for t in tasks]


@router.get("/{tid}", response_model=TaskOut)
def get(tid: int,
        db: Session = Depends(db_session),
        _: User = Depends(require_role("viewer", "operator", "admin"))):
    t = db.get(Task, tid)
    if not t:
        raise HTTPException(status_code=404, detail="Task not found")
    count = db.query(func.count()).select_from(DatasetVersion).filter_by(task_id=tid).scalar()
    return _enrich(t, count)


@router.post("/{tid}/datasets", response_model=DatasetVersionOut)
def upload_dataset(
    tid: int,
    tag: str = Form(...),
    is_default: bool = Form(False),
    note: str | None = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(db_session),
    _: User = Depends(require_role("operator", "admin")),
):
    task = db.get(Task, tid)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # 校验文件扩展名
    if not file.filename or not file.filename.endswith(".jsonl"):
        raise HTTPException(400, "Only .jsonl files are supported")

    content = file.file.read()

    # 校验首行可解析为 JSON
    first_line = content.split(b"\n")[0].strip()
    if not first_line:
        raise HTTPException(400, "File is empty")
    try:
        json.loads(first_line)
    except json.JSONDecodeError:
        raise HTTPException(400, "Invalid JSONL format: first line is not valid JSON")

    # 计算 SHA256
    content_hash = hashlib.sha256(content).hexdigest()

    # 落盘
    settings = get_settings()
    version_dir = settings.workspace_dir / "data" / "versions" / task.key / tag
    version_dir.mkdir(parents=True, exist_ok=True)
    data_path = version_dir / "data.jsonl"
    data_path.write_bytes(content)

    rel_path = str(data_path.relative_to(settings.workspace_dir))

    # 若 is_default，清除其他默认版本
    if is_default:
        db.query(DatasetVersion).filter_by(task_id=tid, is_default=True).update(
            {"is_default": False}
        )

    dv = DatasetVersion(
        task_id=tid,
        tag=tag,
        data_path=rel_path,
        content_hash=content_hash,
        is_default=is_default,
        note=note,
    )
    db.add(dv)
    db.commit()
    db.refresh(dv)
    return dv


@router.get("/{tid}/datasets", response_model=list[DatasetVersionOut])
def list_datasets(tid: int,
                  db: Session = Depends(db_session),
                  _: User = Depends(require_role("viewer", "operator", "admin"))):
    task = db.get(Task, tid)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return (
        db.query(DatasetVersion)
        .filter_by(task_id=tid)
        .order_by(DatasetVersion.uploaded_at.desc())
        .all()
    )


def _resolve_data_file(data_path: str) -> Path:
    """解析数据版本物理路径：依次尝试 workspace_dir、code_dir、项目根。"""
    settings = get_settings()
    proj_root = Path(__file__).resolve().parents[3]  # backend/app/routers/tasks.py -> 项目根
    for base in (settings.workspace_dir, settings.code_dir, proj_root):
        candidate = base / data_path
        if candidate.exists():
            return candidate
    raise HTTPException(status_code=404, detail=f"数据文件不存在: {data_path}")


@router.get("/{tid}/datasets/{vid}/download")
def download_dataset(
    tid: int,
    vid: int,
    db: Session = Depends(db_session),
    _: User = Depends(require_role("viewer", "operator", "admin")),
):
    task = db.get(Task, tid)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    dv = db.get(DatasetVersion, vid)
    if not dv or dv.task_id != tid:
        raise HTTPException(status_code=404, detail="Dataset version not found")

    src = _resolve_data_file(dv.data_path)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        if src.is_file():
            zf.write(src, arcname=src.name)
        else:  # 目录：打包整个目录（保留顶层目录名）
            for f in sorted(src.rglob("*")):
                if f.is_file():
                    zf.write(f, arcname=str(f.relative_to(src.parent)))
    buf.seek(0)

    filename = f"{task.key}_v_{dv.tag}.zip"
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
