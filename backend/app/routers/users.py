from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.deps import db_session, require_role
from backend.app.models import User
from backend.app.schemas import (
    ResetPasswordIn, UserCreate, UserOut, UserUpdate,
)
from backend.app.services import user_service


router = APIRouter(prefix="/api/v1/users", tags=["users"])


@router.get("", response_model=list[UserOut])
def list_(_: User = Depends(require_role("admin")),
          db: Session = Depends(db_session)):
    return db.query(User).order_by(User.id.asc()).all()


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create(payload: UserCreate,
           _: User = Depends(require_role("admin")),
           db: Session = Depends(db_session)):
    try:
        u = user_service.create_user(db, payload.username, payload.password,
                                     payload.role, payload.display_name)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return u


def _get_or_404(db: Session, uid: int) -> User:
    u = db.get(User, uid)
    if not u:
        raise HTTPException(404, f"User {uid} not found")
    return u


@router.put("/{uid}", response_model=UserOut)
def update(uid: int, payload: UserUpdate,
           actor: User = Depends(require_role("admin")),
           db: Session = Depends(db_session)):
    u = _get_or_404(db, uid)
    try:
        user_service.update_user(
            db, u,
            role=payload.role,
            display_name=payload.display_name,
            is_active=payload.is_active,
            actor_user_id=actor.id,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return u


@router.post("/{uid}/reset-password", status_code=status.HTTP_204_NO_CONTENT)
def reset_password(uid: int, payload: ResetPasswordIn,
                   _: User = Depends(require_role("admin")),
                   db: Session = Depends(db_session)):
    u = _get_or_404(db, uid)
    user_service.reset_password(db, u, payload.new_password)
    return None


@router.delete("/{uid}", status_code=status.HTTP_204_NO_CONTENT)
def delete(uid: int,
           actor: User = Depends(require_role("admin")),
           db: Session = Depends(db_session)):
    u = _get_or_404(db, uid)
    try:
        user_service.deactivate_user(db, u, actor_user_id=actor.id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return None
