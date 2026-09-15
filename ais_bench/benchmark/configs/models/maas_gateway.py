# -*- coding: utf-8 -*-
# @Time    : 2026/4/17
# @Author  : jia
# @File    : maas_gateway.py
# @Desc    : 临时 MaaS 网关配置（带 Authorization-Gateway 鉴权），
#            用于一次性调用外部 MaaS 服务（如 deepseekv3.1-w8a8）。
#            与 local_qwen.py 的区别：
#              1. 需要 api_key（Authorization-Gateway 头）
#              2. url 为带网关前缀的完整地址
#              3. 模型名默认 deepseekv3.1-w8a8
import os
from ais_bench.benchmark.models import MaaSAPI
from ais_bench.benchmark.utils.postprocess.model_postprocessors import (
    extract_non_reasoning_content,
)

models = [
    dict(
        attr="service",
        type=MaaSAPI,
        abbr="maas_gateway",
        path="",
        model=os.environ.get("MAAS_MODEL", "deepseekv3.1-w8a8"),
        stream=False,
        request_rate=0,
        retry=1,
        api_key=os.environ.get("MAAS_API_KEY", ""),
        # 鉴权头名称可配（默认 Authorization-Gateway；部分网关用 Authorization 等）
        auth_header=os.environ.get("MAAS_AUTH_HEADER", "Authorization-Gateway"),
        host_ip=os.environ.get("MAAS_HOST_IP", ""),
        host_port=int(os.environ.get("MAAS_HOST_PORT", "30175")),
        # 完整 URL（含网关路径），示例：
        #   http://188.103.147.179:30175/gateway/api/XKpb9p/v1/chat/completions
        url=os.environ.get("MAAS_URL", ""),
        # max_out_len：仅供框架内部使用（数据集 truncation、统计指标等），
        # 不会作为 max_tokens 发送给模型服务端（已在 MaaSAPI.get_request_body 注释）。
        # 必须 > 0，否则 get_request_body 会触发 max_out_len <= 0 守卫跳过请求。
        max_out_len=16000,
        batch_size=int(os.environ.get("MAAS_CONCURRENCY", "5")),
        trust_remote_code=False,
        verbose=os.environ.get("EVAL_VERBOSE", "false").lower() == "true",
        generation_kwargs=dict(
            temperature=0.01,
            ignore_eos=False,
        ),
        pred_postprocessor=dict(type=extract_non_reasoning_content),
    ),
]
