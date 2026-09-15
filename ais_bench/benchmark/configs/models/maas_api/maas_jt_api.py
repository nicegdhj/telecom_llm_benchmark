import os
from ais_bench.benchmark.models import MaaSJTAPI
from ais_bench.benchmark.utils.postprocess.model_postprocessors import extract_non_reasoning_content


models = [
    dict(
        attr="service",
        type=MaaSJTAPI,
        abbr="maas-jt-api",
        path="",
        model="JT-NET-75B-8k",
        stream=False,
        request_rate=0,
        retry=2,
        # 从.env取值，如果没取到默认 fallback 为 cxy_maas
        api_key=os.environ.get("JIUTIAN_API_KEY", "cxy_maas"),
        url="http://188.103.147.179:30175/gateway/api/On7sTN/metis/api/v2/chat/completions",
        max_out_len=512,
        batch_size=1,
        trust_remote_code=False,
        generation_kwargs=dict(
            temperature=0.01,
            ignore_eos=False,
        ),
        pred_postprocessor=dict(type=extract_non_reasoning_content),
    )
]
