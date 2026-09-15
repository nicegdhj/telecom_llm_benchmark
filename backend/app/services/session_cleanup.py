import asyncio
import logging

from backend.app.config import get_settings
from backend.app.db import get_session
from backend.app.services.auth_service import cleanup_expired_sessions


_log = logging.getLogger(__name__)


async def session_cleanup_loop():
    """后台协程：周期性清理过期 session。"""
    settings = get_settings()
    interval = settings.session_cleanup_interval_sec
    while True:
        try:
            with get_session() as s:
                n = cleanup_expired_sessions(s)
                s.commit()
                if n:
                    _log.info("cleaned %d expired session(s)", n)
        except Exception:
            _log.exception("session cleanup failed")
        await asyncio.sleep(interval)
