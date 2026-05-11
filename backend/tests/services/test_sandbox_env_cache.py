from pathlib import Path
from unittest.mock import patch

import pytest

from app.services.sandbox.manager import SandboxManager
from app.services.sandbox.models import SandboxJob, SandboxJobSource
from app.services.sandbox.node_env import NodeEnvironmentManager
from app.services.sandbox.workspace import SandboxWorkspaceManager


class InMemoryResultStore:
    async def update_status(self, job_id, status, *, metadata=None, **updates):
        from app.services.sandbox.models import SandboxResult

        result = SandboxResult(job_id=job_id, status=status, metadata=metadata)
        for key, value in updates.items():
            setattr(result, key, value)
        return result


class FakePythonEnvManager:
    def __init__(self, env_dir: Path, cache_hit: bool = True):
        self.env_dir = env_dir
        self.cache_hit = cache_hit
        self.calls = []

    def ensure_environment(self, *, packages, runtime_profile, package_index_url=None):
        self.calls.append((packages, runtime_profile, package_index_url))
        return self.env_dir, self.cache_hit

    def build_env_vars(self, env_dir: Path):
        return {
            "VIRTUAL_ENV": str(env_dir),
            "PATH": f"{env_dir / 'bin'}:/usr/bin",
        }

    def runtime_path(self):
        return "/usr/local/bin:/usr/bin:/bin"


class FakeNodeEnvManager:
    def __init__(self, env_dir: Path, cache_hit: bool = False):
        self.env_dir = env_dir
        self.cache_hit = cache_hit
        self.calls = []

    def ensure_environment(self, *, packages, runtime_profile, registry_url=None):
        self.calls.append((packages, runtime_profile, registry_url))
        return self.env_dir, self.cache_hit

    def node_binary(self):
        return "/usr/bin/node"

    def build_env_vars(self, env_dir: Path):
        return {
            "NODE_PATH": str(env_dir / "node_modules"),
            "SANDBOX_NODE_BINARY": "/usr/bin/node",
            "PATH": f"{env_dir / 'node_modules' / '.bin'}:/usr/bin",
        }


@pytest.mark.anyio
class TestSandboxEnvironmentCache:
    async def test_build_command_env_injects_python_env(self, tmp_path: Path):
        workspace_manager = SandboxWorkspaceManager(root=str(tmp_path / "jobs"))
        workspace = workspace_manager.prepare("job-python")
        python_env = tmp_path / "cache" / "py-env"
        (python_env / "bin").mkdir(parents=True, exist_ok=True)

        manager = SandboxManager(
            workspace_manager=workspace_manager,
            cleanup_workspaces=False,
            result_store=InMemoryResultStore(),
            python_env_manager=FakePythonEnvManager(python_env, cache_hit=True),
        )
        job = SandboxJob(
            source=SandboxJobSource.DEBUG,
            command=["python3", "-c", "print('ok')"],
            python_packages=["requests==2.32.3"],
            python_package_index_url=" https://mirror.example.com/simple/ ",
        )

        from app.services.sandbox.models import SandboxExecutionMetadata

        execution_metadata = SandboxExecutionMetadata()
        env = manager._build_command_env(job, workspace, execution_metadata)

        assert env["VIRTUAL_ENV"] == str(python_env)
        assert str(python_env / "bin") in env["PATH"]
        assert "/backend/.venv/bin" not in env["PATH"]
        assert execution_metadata.cache_hit_python is True
        assert manager.python_env_manager.calls == [
            (["requests==2.32.3"], "standard", "https://mirror.example.com/simple")
        ]

    async def test_build_command_env_injects_node_env(self, tmp_path: Path):
        workspace_manager = SandboxWorkspaceManager(root=str(tmp_path / "jobs"))
        workspace = workspace_manager.prepare("job-node")
        node_env = tmp_path / "cache" / "node-env"
        (node_env / "node_modules" / ".bin").mkdir(parents=True, exist_ok=True)

        manager = SandboxManager(
            workspace_manager=workspace_manager,
            cleanup_workspaces=False,
            result_store=InMemoryResultStore(),
            node_env_manager=FakeNodeEnvManager(node_env, cache_hit=False),
        )
        job = SandboxJob(
            source=SandboxJobSource.DEBUG,
            command=["node", "-e", "console.log('ok')"],
            js_packages=["eslint@9.25.1"],
            node_package_registry_url=" https://registry.example.com/npm/ ",
        )

        from app.services.sandbox.models import SandboxExecutionMetadata

        execution_metadata = SandboxExecutionMetadata()
        env = manager._build_command_env(job, workspace, execution_metadata)

        assert env["NODE_PATH"] == str(node_env / "node_modules")
        assert str(node_env / "node_modules" / ".bin") in env["PATH"]
        assert execution_metadata.cache_hit_node is False
        assert manager.node_env_manager.calls == [
            (["eslint@9.25.1"], "standard", "https://registry.example.com/npm")
        ]

    async def test_build_command_env_injects_default_node_binary_without_js_packages(
        self, tmp_path: Path
    ):
        workspace_manager = SandboxWorkspaceManager(root=str(tmp_path / "jobs"))
        workspace = workspace_manager.prepare("job-node-default")
        node_env = tmp_path / "cache" / "node-env"

        manager = SandboxManager(
            workspace_manager=workspace_manager,
            cleanup_workspaces=False,
            result_store=InMemoryResultStore(),
            node_env_manager=FakeNodeEnvManager(node_env, cache_hit=False),
        )
        job = SandboxJob(
            source=SandboxJobSource.DEBUG,
            language="javascript",
            command=["javascript"],
        )

        from app.services.sandbox.models import SandboxExecutionMetadata

        execution_metadata = SandboxExecutionMetadata()
        env = manager._build_command_env(job, workspace, execution_metadata)

        assert "/backend/.venv/bin" not in env["PATH"]
        assert env["SANDBOX_NODE_BINARY"] == "/usr/bin/node"
        assert env["PATH"].split(":", 1)[0] == "/usr/bin"
        assert manager.node_env_manager.calls == []

    async def test_resolve_command_prefers_sandbox_path(self, tmp_path: Path):
        workspace_manager = SandboxWorkspaceManager(root=str(tmp_path / "jobs"))
        sandbox_bin = tmp_path / "sandbox-bin"
        sandbox_bin.mkdir(parents=True, exist_ok=True)
        tool_path = sandbox_bin / "my-tool"
        tool_path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        tool_path.chmod(0o755)

        manager = SandboxManager(
            workspace_manager=workspace_manager,
            cleanup_workspaces=False,
            result_store=InMemoryResultStore(),
        )

        resolved = manager._resolve_command(
            ["my-tool", "--flag"], {"PATH": str(sandbox_bin)}
        )

        assert resolved == [str(tool_path), "--flag"]

    def test_node_env_manager_caches_node_exec_probe(self, tmp_path: Path):
        manager = NodeEnvironmentManager(tmp_path)

        with patch(
            "app.services.sandbox.node_env.subprocess.check_output",
            return_value="/usr/local/bin/node\n",
        ) as mock_check_output:
            first = manager.build_env_vars(tmp_path / "env")
            second = manager.build_env_vars(tmp_path / "env")

        assert first["SANDBOX_NODE_BINARY"] == "/usr/local/bin/node"
        assert second["SANDBOX_NODE_BINARY"] == "/usr/local/bin/node"
        assert mock_check_output.call_count == 1

    def test_python_executable_prefers_virtualenv_when_python_packages_are_installed(
        self, tmp_path: Path
    ):
        manager = SandboxManager(
            workspace_manager=SandboxWorkspaceManager(root=str(tmp_path / "jobs")),
            cleanup_workspaces=False,
            result_store=InMemoryResultStore(),
        )
        env_dir = tmp_path / "cache" / "py-env"
        env = {"VIRTUAL_ENV": str(env_dir), "PATH": f"{env_dir / 'bin'}:/usr/bin"}

        assert manager._python_executable(env) == str(env_dir / "bin" / "python")

    def test_python_runtime_path_excludes_backend_venv(self, tmp_path: Path):
        manager = SandboxManager(
            workspace_manager=SandboxWorkspaceManager(root=str(tmp_path / "jobs")),
            cleanup_workspaces=False,
            result_store=InMemoryResultStore(),
        )

        from unittest.mock import patch

        with (
            patch.dict(
                "app.services.sandbox.python_env.os.environ",
                {"PATH": "/app/backend/.venv/bin:/usr/local/bin:/usr/bin:/bin"},
                clear=False,
            ),
            patch(
                "app.services.sandbox.python_env.Path.exists",
                return_value=True,
            ),
        ):
            runtime_path = manager.python_env_manager.runtime_path()

        assert runtime_path.startswith("/usr/local/bin")
        assert "/backend/.venv/bin" not in runtime_path

    def test_python_env_key_includes_package_index_url(self, tmp_path: Path):
        manager = SandboxManager(
            workspace_manager=SandboxWorkspaceManager(root=str(tmp_path / "jobs")),
            cleanup_workspaces=False,
            result_store=InMemoryResultStore(),
        )

        first = manager.python_env_manager.build_env_key(
            "3.13.0",
            ["requests==2.32.3"],
            "standard",
            "https://mirror-a.example.com/simple/",
        )
        second = manager.python_env_manager.build_env_key(
            "3.13.0",
            ["requests==2.32.3"],
            "standard",
            "https://mirror-b.example.com/simple/",
        )

        assert first != second

    def test_node_env_key_includes_registry_url(self, tmp_path: Path):
        manager = NodeEnvironmentManager(tmp_path)

        first = manager.build_env_key(
            "v22.0.0",
            ["eslint@9.25.1"],
            "standard",
            "https://registry-a.example.com/npm/",
        )
        second = manager.build_env_key(
            "v22.0.0",
            ["eslint@9.25.1"],
            "standard",
            "https://registry-b.example.com/npm/",
        )

        assert first != second
