# -*- coding= utf-8 -*-
# @Time    = 2026/1/22 17=37
# @Author  = jia
# @File    = bailian_qwen.py
# @Desc    =
import os
from ais_bench.benchmark.models import VLLMCustomAPIChat
from ais_bench.benchmark.utils.postprocess.model_postprocessors import (
    extract_non_reasoning_content,
)

models = [
    dict(
        attr="service",
        type=VLLMCustomAPIChat,
        abbr="common_gateway",
        path="",
        model=os.environ["COMMON_MODEL_NAME"],
        stream=False,
        request_rate=0,
        retry=2,
        api_key=os.environ["COMMON_API_KEY"],
        url=os.environ["COMMON_URL"],
        max_out_len=16000,
        batch_size=int(os.environ.get("COMMON_CONCURRENCY", "5")),
        trust_remote_code=False,
        verbose=os.environ.get("EVAL_VERBOSE", "false").lower() == "true",
        generation_kwargs=dict(
            temperature=0.01,
            ignore_eos=False,
        ),
        pred_postprocessor=dict(type=extract_non_reasoning_content),
    ),
]
