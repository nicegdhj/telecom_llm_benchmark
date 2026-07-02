import json

from backend.app.config import Settings
from backend.app.services.scan import scan_infer_output, scan_eval_output


def _make_settings(tmp_path):
    return Settings(backend_data_dir=tmp_path/"bd",
                    workspace_dir=tmp_path/"ws",
                    code_dir=tmp_path/"ws/code")


def test_scan_infer_output_reads_infer_meta(tmp_path):
    s = _make_settings(tmp_path)
    task_id = "abc"
    d = s.workspace_dir / "outputs" / task_id
    d.mkdir(parents=True)
    # infer_meta.json tasks 是 dict，key=suite_name（与 eval_entry.py 实际格式一致）
    (d / "infer_meta.json").write_text(json.dumps({
        "model_config": "local_qwen",
        "tasks": {
            "task_34_suite": {"num_samples": 500, "status": "success"},
        },
    }))
    info = scan_infer_output(s, task_id, "task_34_suite")
    assert info["num_samples"] == 500
    assert info["output_path"] == str(d)


def test_scan_infer_output_missing_file(tmp_path):
    s = _make_settings(tmp_path)
    d = s.workspace_dir / "outputs" / "xyz"
    d.mkdir(parents=True)
    info = scan_infer_output(s, "xyz", "no_suite")
    assert info["num_samples"] is None
    assert "xyz" in info["output_path"]


def test_scan_eval_output_reads_summary(tmp_path):
    s = _make_settings(tmp_path)
    task_id = "abc"
    eval_ver = "eval_v2"
    suite = "task_34_suite"
    eval_dir = s.workspace_dir / "outputs" / task_id / eval_ver
    eval_dir.mkdir(parents=True)
    (eval_dir / "report.json").write_text(json.dumps({
        "accuracy": 87.5,
        "tasks": [{"suite": suite, "num_samples": 500}],
    }))
    info = scan_eval_output(s, task_id, eval_ver, suite)
    assert info["accuracy"] == 87.5
    assert info["num_samples"] == 500


def test_scan_eval_output_missing_dir(tmp_path):
    s = _make_settings(tmp_path)
    info = scan_eval_output(s, "noop", "eval_init", "suite_x")
    assert info["accuracy"] is None
    assert info["num_samples"] is None
