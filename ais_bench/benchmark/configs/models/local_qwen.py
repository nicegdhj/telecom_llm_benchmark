# -*- coding= utf-8 -*-
# @Time    = 2026/1/22 17=37
# @Author  = jia
# @File    = maas.py
# @Desc    =
import os
from ais_bench.benchmark.models import MaaSAPI
from ais_bench.benchmark.utils.postprocess.model_postprocessors import (
    extract_non_reasoning_content,
)

models = [
    dict(
        attr="service",
        type=MaaSAPI,
        abbr="local_qwen",
        path="",
        model=os.environ.get("LOCAL_MODEL_NAME", "qwen3-14b"),
        stream=False,
        request_rate=0,
        retry=1,
        host_ip=os.environ.get("LOCAL_HOST_IP"),
        host_port=int(os.environ.get("LOCAL_HOST_PORT")),
        url=f"http://{os.environ.get('LOCAL_HOST_IP')}:{os.environ.get('LOCAL_HOST_PORT')}/v1/chat/completions",
        # max_out_len：仅供框架内部使用（数据集 truncation、统计指标等），
        # 不会作为 max_tokens 发送给模型服务端 —— 已在 MaaSAPI.get_request_body 中
        # 注释掉 request_body["max_tokens"] = max_out_len。
        # 服务端会自动以 (max_model_len - input_tokens) 作为输出上限，避免因
        # max_tokens + input > max_model_len 触发 400 BadRequest。
        # 注意：必须保持 > 0，否则会触发 get_request_body 中的 max_out_len <= 0 守卫导致跳过请求。
        max_out_len=16000,
        batch_size=int(os.environ.get("LOCAL_CONCURRENCY", "20")),
        trust_remote_code=False,
        verbose=os.environ.get("EVAL_VERBOSE", "false").lower() == "true",
        generation_kwargs=dict(
            temperature=0.01,
            ignore_eos=False,
        ),
        pred_postprocessor=dict(type=extract_non_reasoning_content),
    ),
]
