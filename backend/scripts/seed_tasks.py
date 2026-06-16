"""手动补种 Task 表。用法：python -m backend.scripts.seed_tasks

注：init_db() 启动时已会幂等执行同样的种植；本脚本仅供手动触发/补种。"""
from backend.app.db import get_session, init_db
from backend.app.services.seed import (
    seed_generic_tasks, seed_custom_tasks, seed_init_versions,
    DEFAULT_GENERIC, DEFAULT_CUSTOM,
)


def main():
    init_db()
    with get_session() as session:
        seed_generic_tasks(session, DEFAULT_GENERIC)
        seed_custom_tasks(session, DEFAULT_CUSTOM)
        session.flush()  # 确保 task.id 可用，供挂载 init 版本
        seed_init_versions(session)
        session.commit()
    print("Seeded tasks and init versions.")


if __name__ == "__main__":
    main()
