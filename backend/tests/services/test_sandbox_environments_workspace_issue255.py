import json
import subprocess
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import call, patch

import pytest

from app.services.sandbox.node_env import NodeEnvironmentManager
from app.services.sandbox.python_env import PythonEnvironmentManager
from app.services.sandbox.workspace import SandboxWorkspaceManager


def test_python_environment_builds_with_index_and_cleans_failed_cache(tmp_path: Path):
    manager = PythonEnvironmentManager(tmp_path)
    manager.python_version = lambda: "3.13"
    manager.python_binary = lambda: "/usr/bin/python3"

    with (
        patch(
            "app.services.sandbox.python_env.acquire_cache_lock",
            return_value=nullcontext(),
        ),
        patch("app.services.sandbox.python_env.subprocess.run") as run,
    ):
        env_dir, cache_hit = manager.ensure_environment(
            packages=["requests==2.32.3"],
            runtime_profile="standard",
            package_index_url="https://packages.example/simple/",
        )

    assert cache_hit is False
    assert (env_dir.parent / "READY").read_text() == "ready"
    assert run.call_args_list == [
        call(
            ["/usr/bin/python3", "-m", "venv", str(env_dir)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ),
        call(
            [
                str(env_dir / "bin" / "pip"),
                "install",
                "--index-url",
                "https://packages.example/simple",
                "requests==2.32.3",
            ],
            check=True,
        ),
    ]

    failed_root = manager.cache_root / manager.build_env_key(
        "3.13", ["broken"], "standard"
    )
    with (
        patch(
            "app.services.sandbox.python_env.acquire_cache_lock",
            return_value=nullcontext(),
        ),
        patch(
            "app.services.sandbox.python_env.subprocess.run",
            side_effect=RuntimeError("install failed"),
        ),
        pytest.raises(RuntimeError, match="install failed"),
    ):
        manager.ensure_environment(packages=["broken"], runtime_profile="standard")
    assert not failed_root.exists()


def test_python_environment_cache_hit_and_version_probe_are_reused(tmp_path: Path):
    manager = PythonEnvironmentManager(tmp_path)
    with patch(
        "app.services.sandbox.python_env.subprocess.check_output",
        return_value="Python 3.13.5\n",
    ) as check_output:
        assert manager.python_version() == manager.python_version() == "3.13.5"
    check_output.assert_called_once()

    env_key = manager.build_env_key("3.13.5", ["requests"], "standard")
    env_dir = manager.cache_root / env_key / "venv"
    env_dir.mkdir(parents=True)
    (env_dir.parent / "READY").write_text("ready")
    with patch("app.services.sandbox.python_env.subprocess.run") as run:
        assert manager.ensure_environment(
            packages=["requests"], runtime_profile="standard"
        ) == (env_dir, True)
    run.assert_not_called()


def test_node_environment_parses_packages_and_replaces_stale_cache(tmp_path: Path):
    manager = NodeEnvironmentManager(tmp_path)
    manager._node_version_cache = "v22"
    env_key = manager.build_env_key(
        "v22",
        ["eslint@9", "@scope/pkg@2", "plain"],
        "standard",
        "https://registry.example/npm",
    )
    stale_root = manager.cache_root / env_key
    stale_root.mkdir()
    (stale_root / "stale").write_text("old")

    with (
        patch(
            "app.services.sandbox.node_env.acquire_cache_lock",
            return_value=nullcontext(),
        ),
        patch("app.services.sandbox.node_env.subprocess.run") as run,
    ):
        env_dir, cache_hit = manager.ensure_environment(
            packages=["eslint@9", "@scope/pkg@2", "plain"],
            runtime_profile="standard",
            registry_url="https://registry.example/npm/",
        )

    assert cache_hit is False
    assert json.loads((env_dir / "package.json").read_text())["dependencies"] == {
        "eslint": "9",
        "@scope/pkg": "2",
        "plain": "latest",
    }
    assert not (env_dir / "stale").exists()
    assert (env_dir / "READY").read_text() == "ready"
    run.assert_called_once_with(
        [
            "npm",
            "install",
            "--ignore-scripts",
            "--registry",
            "https://registry.example/npm",
        ],
        cwd=manager.cache_root / f".building-{env_key}",
        check=True,
    )


def test_node_environment_cleans_failed_build(tmp_path: Path):
    manager = NodeEnvironmentManager(tmp_path)
    manager._node_version_cache = "v22"
    env_key = manager.build_env_key("v22", ["broken"], "standard")
    building_root = manager.cache_root / f".building-{env_key}"

    with (
        patch(
            "app.services.sandbox.node_env.acquire_cache_lock",
            return_value=nullcontext(),
        ),
        patch(
            "app.services.sandbox.node_env.subprocess.run",
            side_effect=RuntimeError("npm failed"),
        ),
        pytest.raises(RuntimeError, match="npm failed"),
    ):
        manager.ensure_environment(packages=["broken"], runtime_profile="standard")

    assert not building_root.exists()


def test_workspace_rejects_escape_and_symlink_and_counts_regular_files(tmp_path: Path):
    manager = SandboxWorkspaceManager(root=str(tmp_path / "jobs"))
    workspace = manager.prepare("job")
    (workspace.input_dir / "one.txt").write_bytes(b"123")
    (workspace.output_dir / "two.txt").write_bytes(b"4567")

    assert (
        manager.resolve_workspace_path(workspace, "/workspace/output")
        == workspace.output_dir
    )
    assert manager.workspace_size_bytes(workspace) == 7
    with pytest.raises(ValueError, match="escapes workspace"):
        manager.resolve_workspace_path(workspace, "/workspace/../../outside")

    link = workspace.root / "link"
    target = workspace.root / "target"
    target.mkdir()
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlinks are unavailable")
    with pytest.raises(ValueError, match="contains symlink"):
        manager._check_no_symlinks(link / "file.txt", workspace.root)
    with pytest.raises(ValueError, match="escapes workspace"):
        manager.resolve_workspace_path(workspace, "/workspace/link/../../outside")
