import secrets
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from backend.app.models import User, UserSession
from backend.app.utils.password import hash_password, verify_password


def login(session: Session, username: str, password: str, ttl_hours: int):
    """成功返回 (token, user, expires_at)。失败抛 ValueError / PermissionError。"""
    user = session.query(User).filter_by(username=username).first()
    if not user or not verify_password(password, user.password_hash):
        raise ValueError("用户名或密码错误")
    if not user.is_active:
        raise PermissionError("账号已停用")

    token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(hours=ttl_hours)
    sess = UserSession(token=token, user_id=user.id, expires_at=expires_at)
    user.last_login_at = datetime.utcnow()
    session.add(sess)
    return token, user, expires_at


def logout(session: Session, token: str):
    """删除指定 session。token 不存在则静默忽略。"""
    sess = session.query(UserSession).filter_by(token=token).first()
    if sess:
        session.delete(sess)


def logout_all_for_user(session: Session, user_id: int):
    """删除某用户所有 session（停用/删除用户时使用）。"""
    session.query(UserSession).filter_by(user_id=user_id).delete()


def resolve_session(session: Session, token: str) -> User | None:
    """根据 token 找用户。过期 / 不存在 / 用户停用 → 返回 None。"""
    sess = session.query(UserSession).filter_by(token=token).first()
    if not sess:
        return None
    if sess.expires_at < datetime.utcnow():
        return None
    user = session.get(User, sess.user_id)
    if not user or not user.is_active:
        return None
    sess.last_used_at = datetime.utcnow()
    return user


def change_password(session: Session, user: User, old: str, new: str):
    if not verify_password(old, user.password_hash):
        raise ValueError("原密码错误")
    user.password_hash = hash_password(new)


def cleanup_expired_sessions(session: Session) -> int:
    """删除所有过期 session，返回删除条数。"""
    n = session.query(UserSession).filter(
        UserSession.expires_at < datetime.utcnow()
    ).delete()
    return n
