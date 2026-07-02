from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    backend_data_dir: Path = Path("./backend_data")
    workspace_dir: Path = Path("/opt/eval_workspace")
    code_dir: Path = Path("/opt/eval_workspace/code")
    docker_image_tag: str = "benchmark-eval:latest"
    worker_poll_interval_sec: float = 60.0
    default_job_concurrency: int = 6
    auth_token: str | None = None

    # 权限系统新增
    admin_username: str = "admin"
    admin_password: str | None = None        # 仅首次启动时初始化使用
    session_ttl_hours: int = 168             # 7 天
    session_cleanup_interval_sec: int = 3600 # 每小时清理一次

    @property
    def db_path(self) -> Path:
        return self.backend_data_dir / "eval_backend.db"

    @property
    def envs_dir(self) -> Path:
        return self.backend_data_dir / "envs"

    @property
    def logs_dir(self) -> Path:
        return self.backend_data_dir / "logs"

    class Config:
        env_prefix = "EVAL_BACKEND_"
        env_file = ".env"
        extra = "ignore"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
