"""测评分析：AnalysisView CRUD + 导出。

每个 AnalysisView 是一组用户勾选的 evaluation_ids + 图表配置，
作为对比模板保存。只有 owner 能看/改/删/导出。
"""
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from backend.app.deps import db_session, require_role
from backend.app.models import AnalysisView, User
from backend.app.schemas import AdhocExportIn, AnalysisViewIn, AnalysisViewOut


router = APIRouter(prefix="/api/v1/analysis-views", tags=["analytics"])


def _zip_response(stream, stem: str) -> StreamingResponse:
    """统一构造 zip 下载响应，文件名按 RFC 5987 双重编码（兼容非 ASCII）。"""
    ascii_fallback = stem.encode("ascii", "replace").decode("ascii").replace("?", "_")
    encoded = quote(stem, safe="")
    headers = {
        "Content-Disposition": (
            f'attachment; filename="{ascii_fallback}.zip"; '
            f"filename*=UTF-8''{encoded}.zip"
        )
    }
    return StreamingResponse(stream, media_type="application/zip", headers=headers)


def _clean_stem(raw: str | None, fallback: str) -> str:
    stem = (raw or fallback or "analysis").strip()
    stem = stem.replace("/", "_").replace("\\", "_")
    return stem or "analysis"


def _ensure_owner(view: AnalysisView | None, actor: User) -> AnalysisView:
    if not view:
        raise HTTPException(status_code=404, detail="AnalysisView not found")
    if view.owner_user_id != actor.id:
        raise HTTPException(status_code=403, detail="不是该模板的所有者")
    return view


@router.get("", response_model=list[AnalysisViewOut])
def list_(db: Session = Depends(db_session),
          actor: User = Depends(require_role("viewer", "operator", "admin"))):
    return (db.query(AnalysisView)
            .filter_by(owner_user_id=actor.id)
            .order_by(AnalysisView.updated_at.desc())
            .all())


@router.post("", response_model=AnalysisViewOut, status_code=201)
def create(payload: AnalysisViewIn,
           db: Session = Depends(db_session),
           actor: User = Depends(require_role("viewer", "operator", "admin"))):
    view = AnalysisView(
        name=payload.name,
        owner_user_id=actor.id,
        evaluation_ids=payload.evaluation_ids,
        chart_config=payload.chart_config,
    )
    db.add(view)
    db.commit()
    db.refresh(view)
    return view


@router.get("/{vid}", response_model=AnalysisViewOut)
def get(vid: int,
        db: Session = Depends(db_session),
        actor: User = Depends(require_role("viewer", "operator", "admin"))):
    return _ensure_owner(db.get(AnalysisView, vid), actor)


@router.put("/{vid}", response_model=AnalysisViewOut)
def update(vid: int, payload: AnalysisViewIn,
           db: Session = Depends(db_session),
           actor: User = Depends(require_role("viewer", "operator", "admin"))):
    view = _ensure_owner(db.get(AnalysisView, vid), actor)
    view.name = payload.name
    view.evaluation_ids = payload.evaluation_ids
    view.chart_config = payload.chart_config
    db.commit()
    db.refresh(view)
    return view


@router.delete("/{vid}", status_code=204)
def delete(vid: int,
           db: Session = Depends(db_session),
           actor: User = Depends(require_role("viewer", "operator", "admin"))):
    view = _ensure_owner(db.get(AnalysisView, vid), actor)
    db.delete(view)
    db.commit()
    return None


@router.post("/{vid}/export")
def export(vid: int,
           filename: str | None = Query(None),
           db: Session = Depends(db_session),
           actor: User = Depends(require_role("viewer", "operator", "admin"))):
    """导出已保存模板的 zip：summary.xlsx + charts.html + raw/<eval_id>/。"""
    from backend.app.services.export import build_analysis_zip

    view = _ensure_owner(db.get(AnalysisView, vid), actor)
    stem = _clean_stem(filename, view.name or f"analysis_{view.id}")
    stream = build_analysis_zip(db, view.evaluation_ids or [],
                                title=view.name or stem, view_id=view.id)
    return _zip_response(stream, stem)


@router.post("/export-adhoc")
def export_adhoc(payload: AdhocExportIn,
                 db: Session = Depends(db_session),
                 _: User = Depends(require_role("viewer", "operator", "admin"))):
    """临时导出：直接对一组 evaluation_ids 打包，不必先保存为模板。"""
    from backend.app.services.export import build_analysis_zip

    if not payload.evaluation_ids:
        raise HTTPException(status_code=400, detail="evaluation_ids 不能为空")
    stem = _clean_stem(payload.filename, "对比导出")
    stream = build_analysis_zip(db, payload.evaluation_ids, title=stem, view_id=None)
    return _zip_response(stream, stem)
