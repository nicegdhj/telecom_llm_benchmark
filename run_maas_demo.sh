#!/usr/bin/env bash
# 加载 .env（export 给 ais_bench 子进程，让 maas.py 里的 os.environ 能读到）
set -a; source "$(dirname "$0")/.env"; set +a




# ais_bench --models maas --datasets task_60_suite --debug --num-prompts 1

#ais_bench --models local_qwen --datasets exam_gen_0_shot --debug  --num-prompts 1




#ais_bench --models common_gateway --datasets task_101_suite --debug --num-prompts 1
ais_bench --models common_gateway --datasets task_102_suite --debug --num-prompts 1




# task_1_suite
# task_34_suite
# task_36_suite
# task_43_suite
# task_44_suite
# task_60_suite
# task_101_suite
# 'mmlu_redux_gen_5_shot_str.py',
# 'ceval_gen_0_shot_str.py',
# 'gpqa_gen_0_shot_str.py',
# 'bbh_gen_3_shot_cot_chat.py',
# 'BFCL_gen_simple.py',
# 'ifeval_0_shot_gen_str.py',
# 'math500_gen_0_shot_cot_chat_prompt.py',
# 'aime2025_gen_0_shot_chat_prompt.py',
# 'humaneval_gen_0_shot.py',
# 'livecodebench_0_shot_chat_v6.py',
# 'telemath_gen_0_cot_shot.py',
# 'teleqna_gen_0_shot.py',
# 'tspec_gen_0_shot.py',
# 'teledata_gen_0_shot.py',
# 'telequad_gen_0_shot.py',
# 'tele_exam_gen_0_shot.py',
# 'tele_exam_gen_0_shot_str.py',
#            opseval_gen_0_shot
#            identity_gen_0_shot
#            exam_gen_0_shot

# alarm_data_gen_0_shot





