"""从现有配置种植 Task 表。用法：python -m backend.scripts.seed_tasks"""
from backend.app.db import get_session, init_db
from backend.app.services.seed import seed_generic_tasks, seed_custom_tasks


# 与 run_mixed_benchmark.sh 第 284~304 行保持一致的默认任务集
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


def main():
    init_db()
    with get_session() as session:
        seed_generic_tasks(session, DEFAULT_GENERIC)
        seed_custom_tasks(session, DEFAULT_CUSTOM)
        session.commit()
    print("Seeded tasks.")


if __name__ == "__main__":
    main()
