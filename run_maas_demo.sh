#!/usr/bin/env bash
# 加载 .env（export 给 ais_bench 子进程，让 maas.py 里的 os.environ 能读到）
set -a; source "$(dirname "$0")/.env"; set +a






#ais_bench --models common_gateway --datasets task_1_suite  -num-prompts 1


#ais_bench --models common_gateway --datasets task_1_suite  --debug --num-prompts 1


#全流程
#ais_bench --models common_gateway --datasets task_1_suite task_34_suite task_36_suite task_43_suite task_44_suite task_60_suite task_101_suite task_102_suite --debug --max-num-workers 5

#重推理
#ais_bench --mode eval \
#  --reuse 20260806_003034 \
#  --models common_gateway \
#  --datasets task_101_suite task_102_suite \
#  --debug \
#  --max-num-workers 3


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




#ais_bench \
#  --models common_gateway \
#  --datasets \
#    ot_3gpp_tsg \
#    ot_oranbench \
#    ot_sixg_bench \
#    ot_srsranbench \
#    ot_telelogs \
#    ot_telemath \
#    ot_teleqna \
#    ot_teletables \
#  --debug \
#  --num-prompts 1

ais_bench \
  --models common_gateway \
  --datasets \
    task_201_suite \
    task_202_suite \
    task_203_suite \
    task_204_suite \
    task_205_suite \
    task_206_suite \
    task_207_suite \
    task_208_suite \
    task_209_suite \
    task_210_suite \
    task_211_suite \
    task_212_suite \
    task_213_suite \
    task_214_suite \
    task_215_suite \
    task_216_suite \
    task_217_suite \
    task_218_suite \
    task_219_suite \
    task_220_suite \
    task_221_suite \
    task_222_suite \
    task_223_suite \
    task_224_suite \
    task_225_suite \
    task_226_suite \
    task_227_suite \
    task_234_suite \
    task_235_suite \
    task_236_suite \
    task_240_suite \
    task_247_suite \
    task_250_suite \
    task_253_suite \
    task_256_suite \
    task_258_suite \
    task_260_suite \
  --debug \
  --num-prompts 1

