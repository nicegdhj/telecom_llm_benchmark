from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.app.deps import db_session, require_role
from backend.app.models import Prediction, User
from backend.app.schemas import PredictionOut


router = APIRouter(prefix="/api/v1/predictions", tags=["predictions"])


@router.get("/{pid}", response_model=PredictionOut)
def get(pid: int, db: Session = Depends(db_session),
        _: User = Depends(require_role("viewer", "operator", "admin"))):
    p = db.get(Prediction, pid)
    if not p:
        raise HTTPException(status_code=404, detail=f"Prediction {pid} not found")
    return p
