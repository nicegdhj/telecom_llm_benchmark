import logging

from pathlib import Path
from sqlalchemy.orm import Session

from backend.app.models import DatasetVersion, Task
from backend.app.task_meta import TASK_DATA_PATH


# 默认任务集（与 run_mixed_benchmark.sh 第 284~304 行保持一致）。
# 启动时与 backend/scripts/seed_tasks.py 共用此清单，避免重复定义。
DEFAULT_GENERIC = [
    "alarm_data_gen_0_shot", "ceval_gen_0_shot_str", "mmlu_redux_gen_5_shot_str",
    "teledata_gen_0_shot", "gpqa_gen_0_shot_str", "bbh_gen_3_shot_cot_chat",
    "BFCL_gen_simple", "ifeval_0_shot_gen_str", "math500_gen_0_shot_cot_chat_prompt",
    "aime2025_gen_0_shot_chat_prompt", "telemath_gen_0_cot_shot", "teleqna_gen_0_shot",
    "tspec_gen_0_shot", "telequad_gen_0_shot", "tele_exam_gen_0_shot",
    "tele_exam_gen_0_shot_str", "opseval_gen_0_shot", "identity_gen_0_shot",
    "exam_gen_0_shot",
]
DEFAULT_CUSTOM = [1, 34, 36, 43, 44, 60, 101, 102]


def _get_ais_bench_configs() -> Path:
    """Walk up from this file to find worktree root and derive AISBench configs path.

    seed.py is at: backend/app/services/seed.py
    worktree root is at: backend/ (parent of backend/)
    configs are at: worktree_root/../ais_bench/benchmark/configs/datasets
    """
    current = Path(__file__).resolve()
    # backend/app/services/seed.py -> backend/app/services -> backend/app -> backend/ -> eval-backend/
    for _ in range(4):  # safety limit
        current = current.parent
    worktree_root = current
    configs = worktree_root / "ais_bench" / "benchmark" / "configs" / "datasets"
    if not configs.exists():
        raise RuntimeError(
            f"AISBench configs not found at {configs}. "
            f"Expected from worktree root {worktree_root}"
        )
    return configs


def _detect_is_llm_judge(suite_name: str) -> bool:
    """扫描 suite 配置文件，判断是否使用 LLMJudgeEvaluator。configs 不存在时返回 False。"""
    try:
        configs = _get_ais_bench_configs()
    except RuntimeError:
        return False
    for py in configs.rglob(f"{suite_name}.py"):
        try:
            if "LLMJudgeEvaluator" in py.read_text(encoding="utf-8"):
                return True
        except (OSError, UnicodeDecodeError) as e:
            logging.warning(f"Failed to read {py}: {e}")
    return False


def seed_generic_tasks(session: Session, suite_names: list[str]):
    for suite in suite_names:
        path = TASK_DATA_PATH.get(suite)
        existing = session.query(Task).filter_by(key=suite).first()
        if existing:
            # 回填老库可能缺失的数据路径（早期 seed 未写入 TASK_DATA_PATH）
            if path and not existing.default_data_rel_path:
                existing.default_data_rel_path = path
            continue
        session.add(Task(
            key=suite,
            type="generic",
            suite_name=suite,
            display_name=suite,
            default_data_rel_path=path,
            is_llm_judge=_detect_is_llm_judge(suite),
        ))


def seed_custom_tasks(session: Session, task_nums: list[int]):
    for num in task_nums:
        key = f"task_{num}_suite"
        if session.query(Task).filter_by(key=key).first():
            continue
        session.add(Task(
            key=key,
            type="custom",
            suite_name=key,
            display_name=f"Custom Task {num}",
            custom_task_num=num,
            default_data_rel_path=TASK_DATA_PATH.get(key, f"data/custom_task/task_{num}.jsonl"),
            is_llm_judge=False,  # custom tasks use AccEvaluator, not LLMJudgeEvaluator
        ))


def seed_init_versions(session: Session):
    """为每个任务挂载 tag=init 的初始数据版本（幂等）。

    init 是逻辑指针：真实数据由 ais_bench 算子容器在评测时读取，后端容器未必能
    访问到数据文件（通用数据集打包在计算镜像内），故不校验本地文件是否存在，
    保证 dev / 本地 docker / 私域三处行为一致。
    若任务已存在用户设定的默认版本，则 init 不抢默认。
    """
    for task in session.query(Task).all():
        rel = TASK_DATA_PATH.get(task.key) or task.default_data_rel_path
        if not rel:
            continue
        if session.query(DatasetVersion).filter_by(task_id=task.id, tag="init").first():
            continue
        has_default = (
            session.query(DatasetVersion)
            .filter_by(task_id=task.id, is_default=True)
            .first()
            is not None
        )
        session.add(DatasetVersion(
            task_id=task.id,
            tag="init",
            data_path=rel,
            is_default=not has_default,
            note="初始评测数据",
        ))
