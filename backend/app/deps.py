from typing import Generator, Iterable

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.config import get_settings
from backend.app.db import init_db
from backend.app.models import User
from backend.app.services.auth_service import resolve_session


# 虚拟 system admin（来自旧 EVAL_BACKEND_AUTH_TOKEN bypass，不入 DB）
_SYSTEM_USER = User(
    id=None,
    username="__system__",
    password_hash="",
    role="admin",
    display_name="系统",
    is_active=True,
)


def db_session() -> Generator[Session, None, None]:
    """FastAPI 依赖注入：自动 commit，异常自动 rollback。"""
    from backend.app.db import _SessionLocal

    if _SessionLocal is None:
        init_db()
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def current_user(authorization: str | None = Header(None),
                 db: Session = Depends(db_session)) -> User:
    """解析 Bearer token → User。无效则 401，停用则 403。"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "未登录")
    token = authorization[len("Bearer "):]

    settings = get_settings()
    # 旧 EVAL_BACKEND_AUTH_TOKEN bypass
    if settings.auth_token and token == settings.auth_token:
        return _SYSTEM_USER

    user = resolve_session(db, token)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "会话无效或已过期")
    return user


def require_role(*allowed_roles: str):
    """依赖工厂：require_role('admin') / require_role('admin','operator')。"""
    allowed = set(allowed_roles)

    def dep(user: User = Depends(current_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "权限不足")
        return user

    return dep
