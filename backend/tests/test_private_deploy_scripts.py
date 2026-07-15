import io
import json
import os
from pathlib import Path
import subprocess
import tarfile


ROOT = Path(__file__).resolve().parents[2]


def test_private_runner_never_pulls_benchmark_image():
    script = (ROOT / "run_mixed_benchmark.sh").read_text(encoding="utf-8")
    common_args = script.split("DOCKER_common_args=(", 1)[1].split(")", 1)[0]

    assert "--pull=never" in common_args


def test_private_runner_verifies_loaded_image_tag():
    script = (ROOT / "run_mixed_benchmark.sh").read_text(encoding="utf-8")
    load_pos = script.index('docker load < "${IMAGE_TAR}"')
    verify_pos = script.index('docker image inspect "${IMAGE_TAG}"', load_pos)

    assert verify_pos > load_pos


def test_production_backend_uses_six_concurrent_jobs():
    dockerfile = (
        ROOT / "deploy_docker" / "backend" / "Dockerfile"
    ).read_text(encoding="utf-8")

    assert "ENV EVAL_BACKEND_DEFAULT_JOB_CONCURRENCY=6" in dockerfile


def test_platform_update_rejects_archive_missing_required_image(tmp_path):
    release = tmp_path / "package" / "score_platform"
    (release / "code").mkdir(parents=True)
    (release / "docker-compose.prod.yml").write_text("services: {}\n")
    init_script = release / "init_workspace.sh"
    init_script.write_text("#!/usr/bin/env bash\nexit 0\n")
    init_script.chmod(0o755)

    manifest = [{
        "Config": "config.json",
        "RepoTags": ["score-backend:latest", "score-frontend:latest"],
        "Layers": [],
    }]
    image_archive = release / "score-platform-images.tar.gz"
    with tarfile.open(image_archive, "w:gz") as archive:
        payload = json.dumps(manifest).encode()
        info = tarfile.TarInfo("manifest.json")
        info.size = len(payload)
        archive.addfile(info, io.BytesIO(payload))

    package = tmp_path / "score_platform_test.tar.gz"
    with tarfile.open(package, "w:gz") as archive:
        archive.add(release, arcname="score_platform")

    base = tmp_path / "base"
    data_root = base / "score_data"
    backend_data = data_root / "eval_backend_data"
    workspace = data_root / "eval_workspace"
    backend_data.mkdir(parents=True)
    workspace.mkdir()
    (data_root / ".env").write_text(
        f"WORKSPACE_DIR={workspace}\nBACKEND_DATA_DIR={backend_data}\n"
    )

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    for command in ("docker", "docker-compose", "curl"):
        executable = fake_bin / command
        executable.write_text("#!/usr/bin/env bash\nexit 0\n")
        executable.chmod(0o755)

    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}:{env['PATH']}"
    env["LC_ALL"] = "C"
    result = subprocess.run(
        [
            "bash",
            str(ROOT / "scripts" / "deploy_scripts" / "platform_update.sh"),
            "--pkg", str(package),
            "--base", str(base),
            "--name", "score_platform_test",
            "--yes",
            "--skip-backup",
        ],
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode != 0
    assert "镜像包缺少期望镜像：benchmark-eval:latest" in result.stdout + result.stderr
