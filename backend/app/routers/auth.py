from fastapi import APIRouter, Depends, HTTPException, Header, status
from sqlalchemy.orm import Session

from backend.app.config import get_settings
from backend.app.deps import current_user, db_session
from backend.app.models import User
from backend.app.schemas import (
    ChangePasswordIn, LoginIn, LoginOut, UserBrief,
)
from backend.app.services import auth_service


router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/login", response_model=LoginOut)
def login(payload: LoginIn, db: Session = Depends(db_session)):
    settings = get_settings()
    try:
        token, user, expires = auth_service.login(
            db, payload.username, payload.password,
            ttl_hours=settings.session_ttl_hours,
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(e))
    except PermissionError as e:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(e))
    return LoginOut(
        session_token=token,
        expires_at=expires,
        user=UserBrief.model_validate(user),
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(authorization: str | None = Header(None),
           _: User = Depends(current_user),
           db: Session = Depends(db_session)):
    if authorization and authorization.startswith("Bearer "):
        auth_service.logout(db, authorization[len("Bearer "):])
    return None


@router.get("/me", response_model=UserBrief)
def me(user: User = Depends(current_user)):
    return UserBrief.model_validate(user)


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(payload: ChangePasswordIn,
                    user: User = Depends(current_user),
                    db: Session = Depends(db_session)):
    if user.id is None:
        # __system__ 用户不能改密
        raise HTTPException(403, "系统账号不支持修改密码")
    try:
        auth_service.change_password(db, user, payload.old_password, payload.new_password)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return None
