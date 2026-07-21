import json
import os
import subprocess
from unittest.mock import MagicMock, call

import pytest

from app.services.sandbox.node_env import NodeEnvironmentManager


def test_ensure_environment_builds_and_reuses_cache(tmp_path, monkeypatch):
    manager = NodeEnvironmentManager(tmp_path)
    monkeypatch.setattr(manager, "_node_version", lambda: "v22")
    run = MagicMock()
    monkeypatch.setattr(subprocess, "run", run)

    packages = ["eslint@9", "@scope/pkg@2", "plain"]
    env_root, cache_hit = manager.ensure_environment(
        packages=packages,
        runtime_profile="standard",
        registry_url=" https://registry.example/npm/ ",
    )

    assert cache_hit is False
    assert env_root is not None
    assert json.loads((env_root / "package.json").read_text()) == {
        "name": "clouisle-sandbox-job",
        "private": True,
        "dependencies": {"eslint": "9", "@scope/pkg": "2", "plain": "latest"},
    }
    assert (env_root / "READY").read_text() == "ready"
    run.assert_called_once_with(
        [
            "npm",
            "install",
            "--ignore-scripts",
            "--registry",
            "https://registry.example/npm",
        ],
        cwd=env_root.parent / f".building-{env_root.name}",
        check=True,
    )

    (env_root / "node_modules" / ".bin").mkdir(parents=True)
    assert manager.ensure_environment(
        packages=packages,
        runtime_profile="standard",
        registry_url="https://registry.example/npm",
    ) == (env_root, True)


def test_ensure_environment_replaces_stale_cache_and_cleans_failed_build(
    tmp_path, monkeypatch
):
    manager = NodeEnvironmentManager(tmp_path)
    monkeypatch.setattr(manager, "_node_version", lambda: "v22")
    key = manager.build_env_key("v22", ["pkg"], "standard")
    env_root = manager.cache_root / key
    stale_build = manager.cache_root / f".building-{key}"
    env_root.mkdir()
    (env_root / "stale").write_text("old")
    stale_build.mkdir()
    (stale_build / "stale").write_text("old")

    def fail(*args, **kwargs):
        raise subprocess.CalledProcessError(1, args[0])

    monkeypatch.setattr(subprocess, "run", fail)

    with pytest.raises(subprocess.CalledProcessError):
        manager.ensure_environment(packages=["pkg"], runtime_profile="standard")

    assert not stale_build.exists()
    assert (env_root / "stale").read_text() == "old"

    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: None)
    built, cache_hit = manager.ensure_environment(
        packages=["pkg"], runtime_profile="standard"
    )
    assert (built, cache_hit) == (env_root, False)
    assert not (env_root / "stale").exists()


def test_cache_created_while_waiting_for_lock(tmp_path, monkeypatch):
    manager = NodeEnvironmentManager(tmp_path)
    monkeypatch.setattr(manager, "_node_version", lambda: "v22")
    key = manager.build_env_key("v22", ["pkg"], "standard")
    env_root = manager.cache_root / key

    class Lock:
        def __enter__(self):
            (env_root / "node_modules" / ".bin").mkdir(parents=True)
            (env_root / "READY").write_text("ready")

        def __exit__(self, *args):
            pass

    monkeypatch.setattr(
        "app.services.sandbox.node_env.acquire_cache_lock", lambda *args: Lock()
    )

    assert manager.ensure_environment(packages=["pkg"], runtime_profile="standard") == (
        env_root,
        True,
    )


def test_empty_packages_probes_and_environment_variables(tmp_path, monkeypatch):
    manager = NodeEnvironmentManager(tmp_path)
    probes = []

    def check_output(command, *, text):
        probes.append(call(command, text=text))
        return "v22.1.0\n" if command[-1] == "--version" else "/opt/node/bin/node\n"

    monkeypatch.setattr(subprocess, "check_output", check_output)
    monkeypatch.setenv("PATH", "/usr/bin")

    assert manager.ensure_environment(packages=[], runtime_profile="standard") == (
        None,
        False,
    )
    assert manager._node_version() == "v22.1.0"
    assert manager._node_version() == "v22.1.0"
    env = manager.build_env_vars(tmp_path / "env")
    assert env == {
        "NODE_PATH": str(tmp_path / "env" / "node_modules"),
        "SANDBOX_NODE_BINARY": "/opt/node/bin/node",
        "PATH": os.pathsep.join(
            [
                str(tmp_path / "env" / "node_modules" / ".bin"),
                "/opt/node/bin",
                "/usr/bin",
            ]
        ),
    }
    assert manager.node_binary() == "/opt/node/bin/node"
    assert probes == [
        call(["node", "--version"], text=True),
        call(["node", "-p", "process.execPath"], text=True),
    ]
