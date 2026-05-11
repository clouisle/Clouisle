import sys
from unittest.mock import patch

import pytest

from main import (
    PROJECT_ROOT,
    build_sandbox_worker_image,
    main,
    start_sandbox_worker,
    start_sandbox_worker_container,
)


def test_start_sandbox_worker_uses_solo_pool_by_default():
    with patch("main.os.chdir") as mock_chdir, patch("main.subprocess.run") as mock_run:
        start_sandbox_worker()

    mock_chdir.assert_called_once_with(str(PROJECT_ROOT) + "/backend")
    mock_run.assert_called_once_with(
        [
            str(PROJECT_ROOT) + "/backend/.venv/bin/python",
            "-m",
            "celery",
            "-A",
            "app.core.celery:celery_app",
            "worker",
            "--loglevel=info",
            "--concurrency=1",
            "--queues=sandbox",
            "--pool=solo",
        ]
    )


def test_start_sandbox_worker_keeps_prefork_for_higher_concurrency():
    with patch("main.os.chdir") as mock_chdir, patch("main.subprocess.run") as mock_run:
        start_sandbox_worker(concurrency=2)

    mock_chdir.assert_called_once_with(str(PROJECT_ROOT) + "/backend")
    mock_run.assert_called_once_with(
        [
            str(PROJECT_ROOT) + "/backend/.venv/bin/python",
            "-m",
            "celery",
            "-A",
            "app.core.celery:celery_app",
            "worker",
            "--loglevel=info",
            "--concurrency=2",
            "--queues=sandbox",
        ]
    )


def test_build_sandbox_worker_image_uses_repo_context():
    with patch("main.subprocess.run") as mock_run:
        build_sandbox_worker_image(image_tag="sandbox:test")

    mock_run.assert_called_once_with(
        [
            "docker",
            "build",
            "-f",
            "deploy/dockerfiles/sandbox-worker.Dockerfile",
            "-t",
            "sandbox:test",
            ".",
        ],
        cwd=PROJECT_ROOT,
        check=True,
    )


def test_build_sandbox_worker_image_supports_no_cache():
    with patch("main.subprocess.run") as mock_run:
        build_sandbox_worker_image(no_cache=True, image_tag="sandbox:test")

    assert "--no-cache" in mock_run.call_args.args[0]


def test_start_sandbox_worker_container_runs_without_bind_mounts(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("REDIS_HOST", "redis.local")

    with (
        patch("main.build_sandbox_worker_image") as mock_build,
        patch("main.subprocess.run") as mock_run,
    ):
        start_sandbox_worker_container(concurrency=3, image_tag="sandbox:test")

    mock_build.assert_called_once_with(no_cache=False, image_tag="sandbox:test")
    cmd = mock_run.call_args.args[0]
    assert cmd[:3] == ["docker", "run", "--rm"]
    assert "-v" not in cmd
    assert "--volume" not in cmd
    assert "--mount" not in cmd
    assert ["python", "main.py", "sandbox-worker", "-c", "3"] == cmd[-5:]
    assert "-e" in cmd
    assert "REDIS_HOST=redis.local" in cmd
    mock_run.assert_called_once_with(cmd, cwd=PROJECT_ROOT, check=True)


def test_start_sandbox_worker_container_reads_root_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path
):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "REDIS_PASSWORD=secret\nPOSTGRES_USER=postgres\nREDIS_HOST=redis.local\n"
    )
    monkeypatch.setattr("main.PROJECT_ROOT", str(tmp_path))
    monkeypatch.delenv("REDIS_PASSWORD", raising=False)
    monkeypatch.delenv("POSTGRES_USER", raising=False)

    with (
        patch("main.build_sandbox_worker_image"),
        patch("main.subprocess.run") as mock_run,
    ):
        start_sandbox_worker_container(image_tag="sandbox:test")

    cmd = mock_run.call_args.args[0]
    assert "REDIS_PASSWORD=secret" in cmd
    assert "POSTGRES_USER=postgres" in cmd
    assert "REDIS_HOST=redis.local" in cmd


def test_start_sandbox_worker_container_maps_localhost_env_to_host_gateway(
    monkeypatch: pytest.MonkeyPatch, tmp_path
):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "REDIS_HOST=localhost\n"
        "POSTGRES_SERVER=127.0.0.1\n"
        "QDRANT_URL=http://localhost:6333\n"
        "API_BASE_URL=http://localhost:8000\n"
        "SANDBOX_ARTIFACT_UPLOAD_BASE_URL=http://127.0.0.1:9000\n"
    )
    monkeypatch.setattr("main.PROJECT_ROOT", str(tmp_path))
    monkeypatch.delenv("REDIS_HOST", raising=False)
    monkeypatch.delenv("POSTGRES_SERVER", raising=False)
    monkeypatch.delenv("QDRANT_URL", raising=False)
    monkeypatch.delenv("API_BASE_URL", raising=False)
    monkeypatch.delenv("SANDBOX_ARTIFACT_UPLOAD_BASE_URL", raising=False)

    with (
        patch("main.build_sandbox_worker_image"),
        patch("main.subprocess.run") as mock_run,
    ):
        start_sandbox_worker_container(image_tag="sandbox:test")

    cmd = mock_run.call_args.args[0]
    assert "REDIS_HOST=host.docker.internal" in cmd
    assert "POSTGRES_SERVER=host.docker.internal" in cmd
    assert "QDRANT_URL=http://host.docker.internal:6333" in cmd
    assert "API_BASE_URL=http://host.docker.internal:8000" in cmd
    assert "SANDBOX_ARTIFACT_UPLOAD_BASE_URL=http://host.docker.internal:9000" in cmd


def test_start_sandbox_worker_container_defaults_host_service_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path
):
    monkeypatch.setattr("main.PROJECT_ROOT", str(tmp_path))
    monkeypatch.delenv("REDIS_HOST", raising=False)
    monkeypatch.delenv("POSTGRES_SERVER", raising=False)
    monkeypatch.delenv("API_BASE_URL", raising=False)
    monkeypatch.delenv("SANDBOX_ARTIFACT_UPLOAD_BASE_URL", raising=False)

    with (
        patch("main.build_sandbox_worker_image"),
        patch("main.subprocess.run") as mock_run,
    ):
        start_sandbox_worker_container(image_tag="sandbox:test")

    cmd = mock_run.call_args.args[0]
    assert "REDIS_HOST=host.docker.internal" in cmd
    assert "POSTGRES_SERVER=host.docker.internal" in cmd
    assert "QDRANT_URL=http://host.docker.internal:6333" in cmd


def test_sandbox_worker_local_dev_cli_dispatches_container_mode(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "main.py",
            "sandbox-worker",
            "--local-dev",
            "--no-cache",
            "--image-tag",
            "sandbox:test",
            "-c",
            "2",
        ],
    )

    with patch("main.start_sandbox_worker_container") as mock_start_container:
        main()

    mock_start_container.assert_called_once_with(
        concurrency=2,
        no_cache=True,
        image_tag="sandbox:test",
    )
