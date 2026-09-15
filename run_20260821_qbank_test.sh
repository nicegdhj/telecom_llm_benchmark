#!/usr/bin/env bash
# 加载 .env（export 给 ais_bench 子进程，让 maas.py 里的 os.environ 能读到）
set -a; source "$(dirname "$0")/.env"; set +a


# 20260821 专业题库 task_201-211 快速测试
# 默认每个数据集只抽 1 条（--num-prompts 1）；去掉即全量（3675 条，含 LLM judge 打分，耗时较长）


# 快速冒烟（每个数据集 1 条，验证推理+评测全流程）
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
  --debug \
  --num-prompts 1


# 全量推理+评测
#ais_bench --models common_gateway \
#  --datasets task_201_suite task_202_suite task_203_suite task_204_suite task_205_suite \
#    task_206_suite task_207_suite task_208_suite task_209_suite task_210_suite task_211_suite \
#  --debug --max-num-workers 5


# 重推理（基于已有推理任务，仅评测）
#ais_bench --mode eval \
#  --reuse <推理任务ID> \
#  --models common_gateway \
#  --datasets task_201_suite task_202_suite task_203_suite task_204_suite task_205_suite \
#    task_206_suite task_207_suite task_208_suite task_209_suite task_210_suite task_211_suite \
#  --debug --max-num-workers 3
