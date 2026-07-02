from pathlib import Path

from backend.app.services.docker_runner import build_infer_cmd, build_eval_cmd


def _settings(tmp_path):
    from backend.app.config import Settings
    return Settings(
        backend_data_dir=tmp_path / "bd",
        workspace_dir=tmp_path / "ws",
        code_dir=tmp_path / "ws" / "code",
        docker_image_tag="benchmark-eval:latest",
    )


def test_build_infer_cmd_custom_task(tmp_path):
    s = _settings(tmp_path)
    cmd = build_infer_cmd(
        settings=s,
        job_id=42,
        env_file=tmp_path / "env",
        output_task_id="mixed_eval_xyz",
        model_config_key="local_qwen",
        model_name="qwen",
        concurrency=4,
        task_type="custom",
        custom_task_num=34,
        suite_name="task_34_suite",
    )
    assert "docker" in cmd[0]
    assert "run" in cmd
    assert "--env-file" in cmd
    assert str(tmp_path / "env") in cmd
    assert "--tasks" in cmd
    assert "34" in cmd
    assert "python" in cmd
    assert "eval_entry.py" in cmd


def test_build_infer_cmd_generic(tmp_path):
    s = _settings(tmp_path)
    cmd = build_infer_cmd(
        settings=s, job_id=1, env_file=tmp_path/"e",
        output_task_id="t", model_config_key="local_qwen",
        model_name="qwen", concurrency=4,
        task_type="generic", custom_task_num=None,
        suite_name="mmlu_redux_gen_5_shot_str",
    )
    assert "--generic-datasets" in cmd
    assert "mmlu_redux_gen_5_shot_str" in cmd


def test_build_eval_cmd(tmp_path):
    s = _settings(tmp_path)
    cmd = build_eval_cmd(
        settings=s, job_id=3, env_file=tmp_path/"e",
        output_task_id="mixed_eval_xyz",
        eval_version="eval_v2",
        suite_name="task_34_suite",
    )
    assert "eval_judge.py" in cmd
    assert "--infer-task" in cmd
    assert "mixed_eval_xyz" in cmd
    assert "--eval-version" in cmd
    assert "eval_v2" in cmd
    assert "--eval-tasks" in cmd
    assert "task_34_suite" in cmd
