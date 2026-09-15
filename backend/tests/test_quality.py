"""执行质量统计：从 *_details.jsonl 判定 好 / 空输出 / 解析失败。

口径：
- 空输出   ：prediction 文本为空/缺失
- 解析失败 ：输出非空但 eval_details 为 null
- 好       ：其余（eval_details 为非空 dict，解析成功，无论答案对错）
"""
import json

from backend.app.services.quality import compute_eval_quality


def _write_details(tmp_path, rows):
    d = tmp_path / "results" / "task_x_suite"
    d.mkdir(parents=True)
    f = d / "task_x_details.jsonl"
    with open(f, "w", encoding="utf-8") as fp:
        for r in rows:
            fp.write(json.dumps(r, ensure_ascii=False) + "\n")
    return tmp_path


def test_mixed_classification(tmp_path):
    rows = [
        # 好：有输出 + 解析成功（答案错也算好）
        {"prediction": {"prediction": "答案A"}, "eval_res": False,
         "eval_details": {"__overall__": 0.0}},
        # 好：有输出 + 解析成功 + 答对
        {"prediction": {"prediction": "答案B"}, "eval_res": True,
         "eval_details": {"__overall__": 1.0}},
        # 空输出：prediction 文本为空
        {"prediction": {"prediction": ""}, "eval_res": False,
         "eval_details": None},
        # 空输出：prediction 文本缺失
        {"prediction": {"gold": "x"}, "eval_res": False, "eval_details": None},
        # 解析失败：输出非空但 eval_details 为 null
        {"prediction": {"prediction": "乱码无法解析"}, "eval_res": False,
         "eval_details": None},
    ]
    r = compute_eval_quality(_write_details(tmp_path, rows))
    assert r["total"] == 5
    assert r["good"] == 2
    assert r["empty_output"] == 2
    assert r["parse_fail"] == 1
    assert abs(r["good_ratio"] - 0.4) < 1e-9


def test_prediction_as_nested_json_string(tmp_path):
    # prediction 可能是内嵌 JSON 字符串
    rows = [
        {"prediction": json.dumps({"prediction": "有内容"}),
         "eval_details": {"__overall__": 1.0}},
        {"prediction": json.dumps({"prediction": ""}), "eval_details": None},
    ]
    r = compute_eval_quality(_write_details(tmp_path, rows))
    assert r["good"] == 1
    assert r["empty_output"] == 1


def test_empty_and_missing_paths():
    assert compute_eval_quality(None) is None
    assert compute_eval_quality("/no/such/dir") is None


def test_no_samples_returns_none(tmp_path):
    (tmp_path / "results").mkdir()
    assert compute_eval_quality(tmp_path) is None


def test_sample_views_returned(tmp_path):
    rows = [
        {"prediction": {"prediction": "答案A", "gold": "答案A",
                        "origin_prompt": [{"role": "HUMAN", "prompt": "问题1"}]},
         "eval_res": True, "eval_details": {"__overall__": 1.0}},
        {"prediction": {"prediction": "", "gold": "x"}, "eval_res": False,
         "eval_details": None},
    ]
    r = compute_eval_quality(_write_details(tmp_path, rows), sample_limit=10)
    assert len(r["samples"]) == 2
    s0 = r["samples"][0]
    assert s0["kind"] == "good"
    assert "问题1" in s0["prompt"]
    assert s0["prediction"] == "答案A"
    assert s0["gold"] == "答案A"
    assert r["samples"][1]["kind"] == "empty_output"


def test_sample_limit_caps(tmp_path):
    rows = [{"prediction": {"prediction": f"a{i}"},
             "eval_details": {"__overall__": 1.0}} for i in range(15)]
    r = compute_eval_quality(_write_details(tmp_path, rows), sample_limit=10)
    assert r["total"] == 15
    assert len(r["samples"]) == 10


def test_no_samples_field_without_limit(tmp_path):
    rows = [{"prediction": {"prediction": "x"}, "eval_details": {"__overall__": 1.0}}]
    r = compute_eval_quality(_write_details(tmp_path, rows))
    assert "samples" not in r
