"""模型 / 打分模型连通性测试：按各 config 的真实规则拼 URL + 鉴权头，
向 /v1/chat/completions 发一次最小 chat 请求，验证配置是否可用。

URL / 鉴权头规则与评测时一致（见 worker._env_vars_for_*、ais_bench 各 *_api.py）：
  模型 local_qwen     : http://{host}:{port}/v1/chat/completions ，无鉴权头
  模型 maas_gateway   : {url} ，头 {auth_header}: {api_key}（原样，不加 Bearer）
  模型 common_gateway : {url} ，头 Authorization: Bearer {api_key}
  评委 local_judge    : http://{host}:{port}/v1/chat/completions ，无鉴权头
  评委 api_judge+maas : {url} ，头 Authorization-Gateway: {api_key}
  评委 api_judge+bailian: {url} ，头 Authorization: Bearer {api_key}
"""
import json
import time
import urllib.error
import urllib.request

from backend.app.models import JudgeLLM, Model

TIMEOUT_SEC = 20
_REPLY_MAX = 200
_ERR_BODY_MAX = 500


class _IncompleteConfig(Exception):
    """配置缺少必填项，无法构造请求。"""


def build_model_request(model: Model) -> tuple[str, dict[str, str]]:
    """返回 (url, headers)；配置不完整时抛 _IncompleteConfig。"""
    key = model.model_config_key or "local_qwen"
    if key == "maas_gateway":
        if not model.url:
            raise _IncompleteConfig("缺少完整 URL")
        headers = {}
        if model.api_key:
            headers[model.auth_header or "Authorization-Gateway"] = model.api_key
        return model.url, headers
    if key == "common_gateway":
        if not model.url:
            raise _IncompleteConfig("缺少完整 URL")
        headers = {}
        if model.api_key:
            headers["Authorization"] = f"Bearer {model.api_key}"
        return model.url, headers
    # local_qwen 及未知 config：本地 vLLM 形态
    if not model.host or not model.port:
        raise _IncompleteConfig("缺少 Host IP / 端口")
    return f"http://{model.host}:{model.port}/v1/chat/completions", {}


def build_judge_request(judge: JudgeLLM) -> tuple[str, dict[str, str]]:
    key = judge.judge_config_key or "local_judge"
    if key == "api_judge":
        if not judge.url:
            raise _IncompleteConfig("缺少 API URL")
        headers = {}
        if judge.api_key:
            if "bailian" in (judge.score_model_type or "maas").lower():
                headers["Authorization"] = f"Bearer {judge.api_key}"
            else:
                headers["Authorization-Gateway"] = judge.api_key
        return judge.url, headers
    # local_judge：本地 vLLM 形态
    if not judge.host or not judge.port:
        raise _IncompleteConfig("缺少 Host IP / 端口")
    return f"http://{judge.host}:{judge.port}/v1/chat/completions", {}


def _extract_reply(raw: str) -> str:
    try:
        content = json.loads(raw)["choices"][0]["message"]["content"]
        return (content or "")[:_REPLY_MAX]
    except (ValueError, KeyError, IndexError, TypeError):
        return raw[:_REPLY_MAX]


def _probe(url: str, headers: dict[str, str], model_name: str) -> dict:
    body = json.dumps({
        "model": model_name,
        "stream": False,
        "messages": [{"role": "user", "content": "你好"}],
    }).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    for k, v in headers.items():
        req.add_header(k, v)

    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:
            raw = resp.read().decode("utf-8", "replace")
            return {
                "ok": True,
                "status": resp.status,
                "latency_ms": int((time.monotonic() - t0) * 1000),
                "message": "ok",
                "reply": _extract_reply(raw),
            }
    except urllib.error.HTTPError as e:
        try:
            detail = e.read().decode("utf-8", "replace")[:_ERR_BODY_MAX]
        except Exception:
            detail = ""
        return {
            "ok": False,
            "status": e.code,
            "latency_ms": int((time.monotonic() - t0) * 1000),
            "message": f"HTTP {e.code}：{detail or e.reason}",
            "reply": None,
        }
    except urllib.error.URLError as e:
        return {"ok": False, "status": None, "latency_ms": None,
                "message": f"连接失败：{e.reason}", "reply": None}
    except Exception as e:  # 兜底：超时等
        return {"ok": False, "status": None, "latency_ms": None,
                "message": f"{type(e).__name__}：{e}", "reply": None}


def _incomplete(msg: str) -> dict:
    return {"ok": False, "status": None, "latency_ms": None,
            "message": f"配置不完整：{msg}", "reply": None}


def test_model(model: Model) -> dict:
    try:
        url, headers = build_model_request(model)
    except _IncompleteConfig as e:
        return _incomplete(str(e))
    return _probe(url, headers, model.model_name or "")


def test_judge(judge: JudgeLLM) -> dict:
    try:
        url, headers = build_judge_request(judge)
    except _IncompleteConfig as e:
        return _incomplete(str(e))
    return _probe(url, headers, judge.model_name or "")
