import json

from backend.app.config import Settings


def scan_infer_output(settings: Settings, output_task_id: str,
                      suite_name: str) -> dict:
    """扫描 outputs/{output_task_id}/infer_meta.json 得到推理产物信息。"""
    root = settings.workspace_dir / "outputs" / output_task_id
    num_samples = None
    meta = root / "infer_meta.json"
    if meta.exists():
        try:
            data = json.loads(meta.read_text(encoding="utf-8"))
            # tasks 是 dict，key=suite_name（见 eval_entry.generate_infer_meta）
            task_info = data.get("tasks", {}).get(suite_name)
            if task_info:
                num_samples = task_info.get("num_samples")
        except Exception:
            pass
    return {"output_path": str(root), "num_samples": num_samples}


def scan_eval_output(settings: Settings, output_task_id: str,
                     eval_version: str, suite_name: str) -> dict:
    """扫描 outputs/{output_task_id}/{eval_version}/report.json 得到 accuracy。"""
    eval_dir = settings.workspace_dir / "outputs" / output_task_id / eval_version
    accuracy = None
    num_samples = None
    report = eval_dir / "report.json"
    if report.exists():
        try:
            data = json.loads(report.read_text(encoding="utf-8"))
            # 优先用总平均准确率
            accuracy = data.get("avg_accuracy", data.get("accuracy"))
            # 从 tasks 列表累加样本数
            tasks = data.get("tasks", [])
            if tasks:
                nums = [t.get("num_samples") for t in tasks if t.get("num_samples") is not None]
                if nums:
                    num_samples = sum(nums)
        except Exception:
            pass
    return {"accuracy": accuracy, "details_path": str(eval_dir),
            "num_samples": num_samples}
