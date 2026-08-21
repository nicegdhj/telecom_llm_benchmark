#!/usr/bin/env bash
# 加载 .env（export 给 ais_bench 子进程）
set -a; source "$(dirname "$0")/.env"; set +a

ais_bench \
  --models common_gateway \
  --datasets \
    ot_3gpp_tsg \
    ot_oranbench \
    ot_sixg_bench \
    ot_srsranbench \
    ot_telelogs \
    ot_telemath \
    ot_teleqna \
    ot_teletables \
  --debug \
  --max-num-workers 5
