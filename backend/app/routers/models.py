from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.deps import db_session, require_role
from backend.app.models import Model, User
from backend.app.schemas import ConnTestOut, ModelCreate, ModelOut, ModelUpdate
from backend.app.services.connectivity import test_model


router = APIRouter(prefix="/api/v1/models", tags=["models"])


@router.post("", response_model=ModelOut, status_code=status.HTTP_201_CREATED)
def create(payload: ModelCreate,
           _: User = Depends(require_role("operator", "admin")),
           db: Session = Depends(db_session)):
    m = Model(**payload.model_dump())
    db.add(m)
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(status_code=409, detail=f"保存失败：{e.orig}")
    db.refresh(m)
    return m


@router.get("", response_model=list[ModelOut])
def list_(db: Session = Depends(db_session),
          _: User = Depends(require_role("viewer", "operator", "admin"))):
    return db.query(Model).order_by(Model.id).all()


@router.get("/{mid}", response_model=ModelOut)
def get(mid: int,
        db: Session = Depends(db_session),
        _: User = Depends(require_role("viewer", "operator", "admin"))):
    m = db.get(Model, mid)
    if not m:
        raise HTTPException(404)
    return m


@router.put("/{mid}", response_model=ModelOut)
def update(mid: int, payload: ModelUpdate,
           db: Session = Depends(db_session),
           _: User = Depends(require_role("operator", "admin"))):
    m = db.get(Model, mid)
    if not m:
        raise HTTPException(404)
    for k, v in payload.model_dump(exclude_none=True).items():
        setattr(m, k, v)
    db.commit()
    db.refresh(m)
    return m


@router.delete("/{mid}", status_code=204)
def delete(mid: int,
           db: Session = Depends(db_session),
           _: User = Depends(require_role("operator", "admin"))):
    m = db.get(Model, mid)
    if not m:
        raise HTTPException(404)
    db.delete(m)
    db.commit()


@router.post("/{mid}/test", response_model=ConnTestOut)
def test_connectivity(mid: int,
                      db: Session = Depends(db_session),
                      _: User = Depends(require_role("operator", "admin"))):
    """向该模型配置发一次最小请求，验证连通性与鉴权是否正常。"""
    m = db.get(Model, mid)
    if not m:
        raise HTTPException(404)
    return test_model(m)
