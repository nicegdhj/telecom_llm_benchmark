from sqlalchemy.orm import Session

from backend.app.models import User
from backend.app.services.auth_service import logout_all_for_user
from backend.app.utils.password import hash_password


VALID_ROLES = {"admin", "operator", "viewer"}


def _count_active_admins(session: Session) -> int:
    return session.query(User).filter_by(role="admin", is_active=True).count()


def create_user(session: Session, username: str, password: str,
                role: str, display_name: str | None) -> User:
    if role not in VALID_ROLES:
        raise ValueError(f"非法角色：{role}（允许：{sorted(VALID_ROLES)}）")
    if session.query(User).filter_by(username=username).first():
        raise ValueError(f"用户名 {username!r} 已存在")
    u = User(
        username=username,
        password_hash=hash_password(password),
        role=role,
        display_name=display_name,
        is_active=True,
    )
    session.add(u)
    session.flush()
    return u


def update_user(session: Session, user: User, *,
                role: str | None = None,
                display_name: str | None = None,
                is_active: bool | None = None,
                actor_user_id: int | None = None) -> User:
    """部分更新用户属性，附带业务约束校验。"""
    # 角色变更：不允许把唯一 active admin 降级
    if role is not None:
        if role not in VALID_ROLES:
            raise ValueError(f"非法角色：{role}")
        if (user.role == "admin" and role != "admin"
                and _count_active_admins(session) <= 1):
            raise ValueError("不能降级最后一个 admin")
        user.role = role

    # 停用：不允许停用唯一 active admin；不允许停用自己
    if is_active is not None:
        if is_active is False:
            if actor_user_id is not None and actor_user_id == user.id:
                raise ValueError("不能停用/删除自己")
            if user.role == "admin" and _count_active_admins(session) <= 1:
                raise ValueError("不能停用最后一个 admin")
        user.is_active = is_active
        if is_active is False:
            logout_all_for_user(session, user.id)

    if display_name is not None:
        user.display_name = display_name

    return user


def reset_password(session: Session, user: User, new_password: str):
    user.password_hash = hash_password(new_password)


def deactivate_user(session: Session, user: User, actor_user_id: int | None = None):
    """等价于 update_user(is_active=False)。"""
    update_user(session, user, is_active=False, actor_user_id=actor_user_id)
