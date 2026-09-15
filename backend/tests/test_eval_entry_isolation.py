import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import eval_entry


def _write_fake_ais_bench_output(command):
    work_dir = Path(command[command.index("--work-dir") + 1])
    suite = command[command.index("--datasets") + 1]
    run_dir = work_dir / "20260715_120000"
    (run_dir / "configs").mkdir(parents=True)
    (run_dir / "configs" / "config.py").write_text(
        f"datasets = ['{suite}']\n", encoding="utf-8"
    )
    predictions = run_dir / "predictions" / "local_qwen"
    predictions.mkdir(parents=True)
    (predictions / f"{suite}.jsonl").write_text("{}\n", encoding="utf-8")
    return subprocess.CompletedProcess(command, 0)


def test_infer_uses_task_scoped_ais_bench_work_dir(tmp_path, monkeypatch):
    root = tmp_path / "app"
    output_dir = root / "outputs"
    shared_default = output_dir / "default"
    shared_default.mkdir(parents=True)
    sentinel = shared_default / "other-job-is-writing"
    sentinel.write_text("keep", encoding="utf-8")

    commands = []

    def fake_run(command, **kwargs):
        commands.append(command)
        return _write_fake_ais_bench_output(command)

    monkeypatch.setattr(eval_entry, "ROOT", root)
    monkeypatch.setattr(eval_entry.subprocess, "run", fake_run)
    monkeypatch.setattr(eval_entry, "_cleanup_leaked_shm", lambda: None)

    task_id = "batch15_m10_t26_j42_20260715_120000"
    results = eval_entry.run_evaluation(
        task_nums=[101],
        generic_datasets=[],
        output_dir=output_dir,
        task_id=task_id,
        model_config="local_qwen",
        concurrency=10,
    )
    eval_entry.generate_infer_meta(
        results, task_id, "local_qwen", "qwen3-27b", output_dir
    )

    expected_work_dir = output_dir / task_id / "_ais_bench_work"
    assert commands[0][commands[0].index("--work-dir") + 1] == str(expected_work_dir)
    assert sentinel.read_text(encoding="utf-8") == "keep"
    assert (output_dir / task_id / "details" / "20260715_120000").is_dir()
    assert not expected_work_dir.exists()
    assert results[0]["status"] == "success"
    infer_meta = json.loads(
        (output_dir / task_id / "infer_meta.json").read_text(encoding="utf-8")
    )
    timestamp = infer_meta["tasks"]["task_101_suite"]["timestamp"]
    assert (output_dir / task_id / "details" / timestamp).is_dir()


def test_concurrent_infer_jobs_keep_work_dirs_isolated(tmp_path, monkeypatch):
    job_count = 24
    output_dir = tmp_path / "outputs"
    all_jobs_started = Barrier(job_count)

    def fake_run(command, **kwargs):
        all_jobs_started.wait(timeout=5)
        return _write_fake_ais_bench_output(command)

    monkeypatch.setattr(eval_entry, "ROOT", tmp_path / "app")
    monkeypatch.setattr(eval_entry.subprocess, "run", fake_run)
    monkeypatch.setattr(eval_entry, "_cleanup_leaked_shm", lambda: None)

    def run_job(job_id):
        task_id = f"batch15_m10_t26_j{job_id}_20260715_120000"
        results = eval_entry.run_evaluation(
            task_nums=[],
            generic_datasets=["alarm_data_gen_0_shot"],
            output_dir=output_dir,
            task_id=task_id,
            model_config="local_qwen",
            concurrency=10,
        )
        eval_entry.generate_infer_meta(
            results, task_id, "local_qwen", "qwen3-27b", output_dir
        )
        return task_id, results

    with ThreadPoolExecutor(max_workers=job_count) as executor:
        completed = list(executor.map(run_job, range(1, job_count + 1)))

    assert all(results[0]["status"] == "success" for _, results in completed)
    for task_id, _ in completed:
        task_dir = output_dir / task_id
        assert (task_dir / "infer_meta.json").is_file()
        assert (task_dir / "details" / "20260715_120000").is_dir()
        assert not (task_dir / "_ais_bench_work").exists()
