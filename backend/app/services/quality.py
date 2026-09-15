"""执行质量统计：从评测产出的 *_details.jsonl 逐条样本判定"好坏"。

定义（与产品口径一致）：
- 空输出 (empty_output)：模型推理输出 prediction 为空/缺失。
- 解析失败 (parse_fail)：输出非空，但评估器未能解析（eval_details 为 null）。
- 好 (good)：其余样本（eval_details 为非空 dict，即解析成功，无论答案对错）。

good_ratio = good / total。total 为 0 时返回 None。
"""
import json
from pathlib import Path


def _prediction_text(pred_raw) -> str | None:
    """从 details 行的 prediction 字段取出模型原始输出文本。

    prediction 既可能是 dict（含 prediction 字段），也可能是字符串（可能是内嵌 JSON）。
    """
    if isinstance(pred_raw, dict):
        return pred_raw.get("prediction")
    if isinstance(pred_raw, str):
        try:
            parsed = json.loads(pred_raw)
        except json.JSONDecodeError:
            return pred_raw
        if isinstance(parsed, dict):
            return parsed.get("prediction")
        return pred_raw
    return None


def _classify(d: dict) -> str:
    """返回 'good' | 'empty_output' | 'parse_fail'。"""
    text = _prediction_text(d.get("prediction"))
    if text is None or (isinstance(text, str) and text.strip() == ""):
        return "empty_output"
    if d.get("eval_details") is None:
        return "parse_fail"
    return "good"


def _render_prompt(pred_raw) -> str:
    """把 origin_prompt（[{role, prompt}, ...]）渲染成可读文本。"""
    op = pred_raw.get("origin_prompt") if isinstance(pred_raw, dict) else None
    if isinstance(op, list):
        parts = []
        for m in op:
            if isinstance(m, dict):
                parts.append(f"{m.get('role', '')}: {m.get('prompt', '')}".strip())
            else:
                parts.append(str(m))
        return "\n\n".join(parts)
    if op is not None:
        return str(op)
    return ""


def _to_text(v) -> str:
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    return json.dumps(v, ensure_ascii=False)


def _sample_view(d: dict) -> dict:
    """单条样本的展示视图（用于"结果展示"抽样）。"""
    pred_raw = d.get("prediction")
    gold = pred_raw.get("gold") if isinstance(pred_raw, dict) else None
    return {
        "kind": _classify(d),
        "prompt": _render_prompt(pred_raw),
        "prediction": _to_text(_prediction_text(pred_raw)),
        "gold": _to_text(gold),
        "eval_res": _to_text(d.get("eval_res")),
        "eval_details": _to_text(d.get("eval_details")),
    }


def compute_eval_quality(details_path: str | Path | None,
                         sample_limit: int = 0) -> dict | None:
    """扫描 details_path/results/**/*_details.jsonl，统计执行质量。

    details_path 即 Evaluation.details_path（评测产出目录，如 .../eval_init）。
    sample_limit > 0 时额外返回前 N 条样本的展示视图（samples）。
    找不到任何样本时返回 None。
    """
    if not details_path:
        return None
    base = Path(details_path)
    if not base.exists():
        return None

    total = good = empty_output = parse_fail = 0
    samples: list[dict] = []
    for jf in sorted(base.glob("results/**/*_details.jsonl")):
        try:
            with open(jf, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    total += 1
                    kind = _classify(d)
                    if kind == "good":
                        good += 1
                    elif kind == "empty_output":
                        empty_output += 1
                    else:
                        parse_fail += 1
                    if sample_limit and len(samples) < sample_limit:
                        samples.append(_sample_view(d))
        except OSError:
            continue

    if total == 0:
        return None
    result = {
        "total": total,
        "good": good,
        "empty_output": empty_output,
        "parse_fail": parse_fail,
        "good_ratio": good / total,
    }
    if sample_limit:
        result["samples"] = samples
    return result
