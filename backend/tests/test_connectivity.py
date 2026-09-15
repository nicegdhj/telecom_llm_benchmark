"""连通性测试的 URL / 鉴权头构造（不触网，仅校验映射规则）。"""
import pytest

from backend.app.models import JudgeLLM, Model
from backend.app.services.connectivity import (
    _IncompleteConfig,
    build_judge_request,
    build_model_request,
)


# ── 模型 ──────────────────────────────────────────────────────────────

def test_local_qwen_url_no_auth():
    m = Model(model_config_key="local_qwen", model_name="qwen3-14b",
              host="1.2.3.4", port=8000)
    url, headers = build_model_request(m)
    assert url == "http://1.2.3.4:8000/v1/chat/completions"
    assert headers == {}


def test_maas_gateway_custom_auth_header_value_raw():
    m = Model(model_config_key="maas_gateway", model_name="ds",
              url="http://gw/x/v1/chat/completions",
              api_key="tok123", auth_header="Authorization")
    url, headers = build_model_request(m)
    assert url == "http://gw/x/v1/chat/completions"
    # value 原样，不加 Bearer
    assert headers == {"Authorization": "tok123"}


def test_maas_gateway_default_auth_header():
    m = Model(model_config_key="maas_gateway", model_name="ds",
              url="http://gw/v1/chat/completions", api_key="tok", auth_header=None)
    _, headers = build_model_request(m)
    assert headers == {"Authorization-Gateway": "tok"}


def test_common_gateway_bearer():
    m = Model(model_config_key="common_gateway", model_name="qwen-plus",
              url="https://api/v1/chat/completions", api_key="sk-abc")
    url, headers = build_model_request(m)
    assert headers == {"Authorization": "Bearer sk-abc"}


def test_model_incomplete_raises():
    m = Model(model_config_key="local_qwen", model_name="x", host="", port=None)
    with pytest.raises(_IncompleteConfig):
        build_model_request(m)
    m2 = Model(model_config_key="maas_gateway", model_name="x", url="")
    with pytest.raises(_IncompleteConfig):
        build_model_request(m2)


# ── 评委 ──────────────────────────────────────────────────────────────

def test_local_judge_url_no_auth():
    j = JudgeLLM(judge_config_key="local_judge", model_name="qwen",
                 host="10.0.0.1", port=8001)
    url, headers = build_judge_request(j)
    assert url == "http://10.0.0.1:8001/v1/chat/completions"
    assert headers == {}


def test_api_judge_maas_header():
    j = JudgeLLM(judge_config_key="api_judge", model_name="m",
                 url="http://gw/v1/chat/completions", api_key="k",
                 score_model_type="maas")
    _, headers = build_judge_request(j)
    assert headers == {"Authorization-Gateway": "k"}


def test_api_judge_bailian_bearer():
    j = JudgeLLM(judge_config_key="api_judge", model_name="m",
                 url="https://dashscope/v1/chat/completions", api_key="sk-x",
                 score_model_type="bailian")
    _, headers = build_judge_request(j)
    assert headers == {"Authorization": "Bearer sk-x"}


def test_judge_incomplete_raises():
    j = JudgeLLM(judge_config_key="api_judge", model_name="m", url="")
    with pytest.raises(_IncompleteConfig):
        build_judge_request(j)
