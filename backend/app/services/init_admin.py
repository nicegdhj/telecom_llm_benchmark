from sqlalchemy.orm import Session

from backend.app.models import User
from backend.app.utils.password import hash_password


def ensure_admin(session: Session, username: str, password: str | None):
    """启动时调用：确保至少存在一个 admin。
    若 password 为 None：什么都不做（部署者未设环境变量）。
    若该 username 已存在：跳过（DB 为准，不覆盖密码）。
    否则创建一个 admin 用户。
    """
    if not password:
        return
    existing = session.query(User).filter_by(username=username).first()
    if existing:
        return
    session.add(User(
        username=username,
        password_hash=hash_password(password),
        role="admin",
        display_name="超级管理员",
        is_active=True,
    ))
