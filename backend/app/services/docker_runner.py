from pathlib import Path

from backend.app.config import Settings


def _common_docker_args(settings: Settings, job_id: int,
                        env_file: Path, container_name: str,
                        task_type: str) -> list[str]:
    data_vol_src = settings.workspace_dir / "data"
    if task_type != "custom":
        data_vol_src = Path(settings.workspace_dir).parent / "data"

    return [
        "docker", "run", "--rm",
        "--name", container_name,
        "--memory=128g", "--memory-swap=128g", "--shm-size=16g",
        "--env-file", str(env_file),
        "-v", f"{data_vol_src}:/app/data",
        "-v", f"{settings.workspace_dir}/outputs:/app/outputs",
        "-v", f"{settings.code_dir}/eval_entry.py:/app/eval_entry.py",
        "-v", f"{settings.code_dir}/eval_judge.py:/app/eval_judge.py",
        "-v", f"{settings.code_dir}/scripts:/app/scripts",
        "-v", f"{settings.code_dir}/ais_bench:/app/ais_bench",
        settings.docker_image_tag,
    ]


def build_infer_cmd(
    settings: Settings,
    job_id: int,
    env_file: Path,
    output_task_id: str,
    model_config_key: str,
    model_name: str,
    concurrency: int,
    task_type: str,          # 'custom' | 'generic'
    custom_task_num: int | None,
    suite_name: str,
) -> list[str]:
    cmd = _common_docker_args(
        settings, job_id, env_file, f"eval-{job_id}-infer", task_type
    )
    cmd += [
        "python", "eval_entry.py",
        "--task-id", output_task_id,
        "--model-config", model_config_key,
        "--model", model_name,
        "--concurrency", str(concurrency),
    ]
    if task_type == "custom":
        cmd += ["--tasks", str(custom_task_num)]
    else:
        cmd += ["--generic-datasets", suite_name]
    return cmd


def build_eval_cmd(
    settings: Settings,
    job_id: int,
    env_file: Path,
    output_task_id: str,
    eval_version: str,
    suite_name: str,
    task_type: str = "generic",
) -> list[str]:
    cmd = _common_docker_args(
        settings, job_id, env_file, f"eval-{job_id}-judge", task_type
    )
    cmd += [
        "python", "eval_judge.py",
        "--infer-task", output_task_id,
        "--eval-version", eval_version,
        "--eval-tasks", suite_name,
    ]
    return cmd


def write_env_file(settings: Settings, job_id: int,
                   env_vars: dict[str, str]) -> Path:
    settings.envs_dir.mkdir(parents=True, exist_ok=True)
    path = settings.envs_dir / f"job_{job_id}.env"
    lines = [f"{k}={v}" for k, v in env_vars.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
