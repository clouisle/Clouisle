import asyncio
import os
import subprocess
from pathlib import Path
from unittest.mock import call

import pytest

from app.core.config import settings
from app.core.sandbox_network_policy import (
    DEFAULT_SANDBOX_NETWORK_ALLOWLIST,
    SandboxNetworkPolicyError,
)
from app.services.sandbox.node_env import NodeEnvironmentManager
from app.services.sandbox.process_launcher import ProcessLaunchResult


class FakeProcessLauncher:
    def __init__(self, exit_code: int = 0):
        self.exit_code = exit_code
        self.calls = []

    async def launch(self, command, **kwargs):
        self.calls.append((command, kwargs))
        return ProcessLaunchResult(
            exit_code=self.exit_code,
            stderr="install failed" if self.exit_code else "",
        )


class FakeNetworkProxy:
    allowed_hosts = frozenset(DEFAULT_SANDBOX_NETWORK_ALLOWLIST)
    blocked_diagnostics: list[str] = []


@pytest.mark.anyio
async def test_ensure_environment_builds_and_reuses_cache(tmp_path, monkeypatch):
    manager = NodeEnvironmentManager(tmp_path)
    monkeypatch.setattr(manager, "_node_version", lambda: "v22")
    launcher = FakeProcessLauncher()
    proxy = FakeNetworkProxy()

    packages = ["eslint@9", "@scope/pkg@2", "plain"]
    env_root, cache_hit = await manager.ensure_environment(
        packages=packages,
        runtime_profile="standard",
        process_launcher=launcher,
        network_proxy=proxy,
        registry_url=" https://registry.npmjs.org/npm/ ",
    )

    assert cache_hit is False
    assert env_root is not None
    assert __import__("json").loads((env_root / "package.json").read_text()) == {
        "name": "clouisle-sandbox-job",
        "private": True,
        "dependencies": {"eslint": "9", "@scope/pkg": "2", "plain": "latest"},
    }
    assert (env_root / "READY").read_text() == "ready"
    assert launcher.calls[0][0][1:] == [
        "install",
        "--ignore-scripts",
        "--registry",
        "https://registry.npmjs.org/npm",
    ]

    assert (
        launcher.calls[0][1]["timeout_seconds"]
        == settings.SANDBOX_PACKAGE_INSTALL_TIMEOUT_SECONDS
    )
    (env_root / "node_modules" / ".bin").mkdir(parents=True)
    assert await manager.ensure_environment(
        packages=packages,
        runtime_profile="standard",
        process_launcher=launcher,
        network_proxy=proxy,
        registry_url="https://registry.npmjs.org/npm",
    ) == (env_root, True)
    assert len(launcher.calls) == 1


@pytest.mark.anyio
async def test_ensure_environment_replaces_stale_cache_and_cleans_failed_build(
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

    with pytest.raises(subprocess.CalledProcessError):
        await manager.ensure_environment(
            packages=["pkg"],
            runtime_profile="standard",
            process_launcher=FakeProcessLauncher(exit_code=1),
            network_proxy=FakeNetworkProxy(),
        )

    assert not stale_build.exists()
    assert (env_root / "stale").read_text() == "old"

    built, cache_hit = await manager.ensure_environment(
        packages=["pkg"],
        runtime_profile="standard",
        process_launcher=FakeProcessLauncher(),
        network_proxy=FakeNetworkProxy(),
    )
    assert (built, cache_hit) == (env_root, False)
    assert not (env_root / "stale").exists()


@pytest.mark.anyio
async def test_cache_created_while_waiting_for_lock(tmp_path, monkeypatch):
    manager = NodeEnvironmentManager(tmp_path)
    monkeypatch.setattr(manager, "_node_version", lambda: "v22")
    key = manager.build_env_key("v22", ["pkg"], "standard")
    env_root = manager.cache_root / key

    class Lock:
        async def __aenter__(self):
            (env_root / "node_modules" / ".bin").mkdir(parents=True)
            (env_root / "READY").write_text("ready")

        async def __aexit__(self, *args):
            pass

    monkeypatch.setattr(
        "app.services.sandbox.node_env.acquire_async_cache_lock",
        lambda *args: Lock(),
    )

    assert await manager.ensure_environment(
        packages=["pkg"],
        runtime_profile="standard",
        process_launcher=FakeProcessLauncher(),
        network_proxy=FakeNetworkProxy(),
    ) == (env_root, True)


@pytest.mark.anyio
async def test_disallowed_registry_is_rejected_before_install(tmp_path, monkeypatch):
    manager = NodeEnvironmentManager(tmp_path)
    monkeypatch.setattr(manager, "_node_version", lambda: "v22")
    launcher = FakeProcessLauncher()

    with pytest.raises(SandboxNetworkPolicyError, match="blocked package source"):
        await manager.ensure_environment(
            packages=["pkg"],
            runtime_profile="standard",
            process_launcher=launcher,
            network_proxy=FakeNetworkProxy(),
            registry_url="https://attacker.example/npm",
        )

    assert launcher.calls == []


@pytest.mark.anyio
async def test_empty_packages_probes_and_environment_variables(tmp_path, monkeypatch):
    manager = NodeEnvironmentManager(tmp_path)
    probes = []

    def check_output(command, *, text):
        probes.append(call(command, text=text))
        return "v22.1.0\n" if command[-1] == "--version" else "/opt/node/bin/node\n"

    monkeypatch.setattr(subprocess, "check_output", check_output)
    monkeypatch.setenv("PATH", "/usr/bin")

    assert await manager.ensure_environment(
        packages=[],
        runtime_profile="standard",
        process_launcher=FakeProcessLauncher(),
        network_proxy=FakeNetworkProxy(),
    ) == (None, False)
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


@pytest.mark.anyio
async def test_concurrent_environment_requests_install_once(tmp_path, monkeypatch):
    manager = NodeEnvironmentManager(tmp_path)
    monkeypatch.setattr(manager, "_node_version", lambda: "v22")

    class BlockingLauncher(FakeProcessLauncher):
        def __init__(self):
            super().__init__()
            self.started = asyncio.Event()
            self.release = asyncio.Event()

        async def launch(self, command, **kwargs):
            self.calls.append((command, kwargs))
            building_root = Path(kwargs["cwd"])
            (building_root / "node_modules" / ".bin").mkdir(parents=True)
            self.started.set()
            await self.release.wait()
            return ProcessLaunchResult(exit_code=0)

    launcher = BlockingLauncher()
    kwargs = {
        "packages": ["pkg"],
        "runtime_profile": "standard",
        "process_launcher": launcher,
        "network_proxy": FakeNetworkProxy(),
    }
    first = asyncio.create_task(manager.ensure_environment(**kwargs))
    await launcher.started.wait()
    second = asyncio.create_task(manager.ensure_environment(**kwargs))
    await asyncio.sleep(0)
    launcher.release.set()

    results = await asyncio.gather(first, second)

    assert results[0][1] is False
    assert results[1][1] is True
    assert len(launcher.calls) == 1
