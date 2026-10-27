"""Behavioral tests for sandbox connection-credential handoff."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from app.core.config import settings
from app.services.sandbox.credentials import (
    CREDENTIALS_ENV_VAR,
    CREDENTIALS_METADATA_KEY,
    SandboxCredentialError,
    credential_file_path,
    decrypt_sandbox_credentials,
    encrypt_sandbox_credentials,
    write_credentials_file,
)
from app.services.sandbox.manager import SandboxManager
from app.services.sandbox.models import SandboxJob, SandboxJobSource, SandboxResult
from app.services.sandbox.process_launcher import SandboxProcessLauncher
from app.services.sandbox.snippet import (
    build_javascript_snippet_wrapper,
    build_python_snippet_wrapper,
)
from app.services.sandbox.workspace import SandboxWorkspaceManager


class InMemoryResultStore:
    async def update_status(self, job_id, status, *, metadata=None, **updates):
        result = SandboxResult(job_id=job_id, status=status, metadata=metadata)
        for key, value in updates.items():
            setattr(result, key, value)
        return result


class NoopPythonEnvManager:
    def build_workspace_env_vars(self, workspace_root: Path, tmp_dir: Path):
        return {}

    def build_env_vars(self, env_dir: Path):
        return {}


class LocalProcessLauncher(SandboxProcessLauncher):
    async def launch(self, command, **kwargs):
        kwargs.pop("network_proxy", None)
        return await super().launch(command, **kwargs)


def _parse_wrapper_output(stdout: str) -> dict:
    start = stdout.index("__RESULT__") + len("__RESULT__")
    end = stdout.index("__END__")
    return json.loads(stdout[start:end])


def _envelope_for(job: SandboxJob, credentials: dict[str, str]) -> SandboxJob:
    metadata = dict(job.metadata or {})
    metadata[CREDENTIALS_METADATA_KEY] = encrypt_sandbox_credentials(
        credentials, job_id=job.job_id
    )
    return job.model_copy(update={"metadata": metadata})


def _local_manager(tmp_path: Path, *, cleanup_workspaces: bool = False):
    workspace_manager = SandboxWorkspaceManager(root=str(tmp_path / "jobs"))
    return (
        SandboxManager(
            workspace_manager=workspace_manager,
            cleanup_workspaces=cleanup_workspaces,
            result_store=InMemoryResultStore(),
            python_env_manager=NoopPythonEnvManager(),
            process_launcher=LocalProcessLauncher(),
        ),
        workspace_manager,
    )


def test_envelope_is_ciphertext_bound_to_job():
    envelope = encrypt_sandbox_credentials(
        {"api_key": "s3cret-value", "region": "eu-west-1"}, job_id="job-1"
    )

    assert envelope.startswith("enc:tool:v1:")
    assert "s3cret-value" not in envelope
    assert decrypt_sandbox_credentials(envelope, job_id="job-1") == {
        "api_key": "s3cret-value",
        "region": "eu-west-1",
    }

    with pytest.raises(SandboxCredentialError):
        decrypt_sandbox_credentials(envelope, job_id="job-2")
    with pytest.raises(SandboxCredentialError):
        decrypt_sandbox_credentials("not-a-tool-envelope", job_id="job-1")


def test_envelope_rejects_non_string_values():
    with pytest.raises(SandboxCredentialError):
        encrypt_sandbox_credentials({"api_key": 123}, job_id="job-1")
    with pytest.raises(SandboxCredentialError):
        encrypt_sandbox_credentials({}, job_id="job-1")


def test_python_wrapper_reads_credentials_once_and_unsets_pointer(tmp_path: Path):
    credential_file = credential_file_path(tmp_path)
    write_credentials_file(credential_file, {"api_key": "s3cret-value"})
    assert credential_file.stat().st_mode & 0o777 == 0o600

    wrapper = build_python_snippet_wrapper(
        "\n".join(
            [
                "print('hello from python')",
                "return {",
                "    'key': credentials['api_key'],",
                "    'param': params['value'],",
                "    'pointer': os.environ.get('CLOUISLE_CREDENTIALS_FILE'),",
                "}",
            ]
        ),
        {"value": 41},
    )
    script = tmp_path / "snippet.py"
    script.write_text(wrapper, encoding="utf-8")

    completed = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        env={**os.environ, CREDENTIALS_ENV_VAR: str(credential_file)},
        timeout=30,
        check=False,
    )

    payload = _parse_wrapper_output(completed.stdout)
    assert payload["success"] is True
    assert payload["result"] == {
        "key": "s3cret-value",
        "param": 41,
        "pointer": None,
    }
    assert payload["logs"] == ["hello from python"]
    assert credential_file.exists() is False


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_javascript_wrapper_reads_credentials_once_and_unsets_pointer(
    tmp_path: Path,
):
    credential_file = credential_file_path(tmp_path)
    write_credentials_file(credential_file, {"api_key": "s3cret-value"})

    wrapper = build_javascript_snippet_wrapper(
        "\n".join(
            [
                "console.log('hello from js');",
                "return {",
                "  key: credentials.api_key,",
                "  param: params.value,",
                "  pointer: process.env.CLOUISLE_CREDENTIALS_FILE || null,",
                "};",
            ]
        ),
        {"value": 42},
    )
    script = tmp_path / "snippet.js"
    script.write_text(wrapper, encoding="utf-8")

    completed = subprocess.run(
        [shutil.which("node"), str(script)],
        capture_output=True,
        text=True,
        env={**os.environ, CREDENTIALS_ENV_VAR: str(credential_file)},
        timeout=30,
        check=False,
    )

    payload = _parse_wrapper_output(completed.stdout)
    assert payload["success"] is True
    assert payload["result"] == {
        "key": "s3cret-value",
        "param": 42,
        "pointer": None,
    }
    assert payload["logs"] == ["hello from js"]
    assert credential_file.exists() is False


@pytest.mark.anyio
async def test_manager_decrypts_envelope_and_removes_credential_file(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setattr(settings, "SANDBOX_FILESYSTEM_ISOLATION_ENABLED", False)
    monkeypatch.setattr(settings, "SANDBOX_DEFAULT_PYTHON_BINARIES", [sys.executable])
    manager, workspace_manager = _local_manager(tmp_path)

    job = SandboxJob(
        source=SandboxJobSource.TOOL,
        language="python",
        code=(
            "return {\n"
            "  'key': credentials['api_key'],\n"
            "  'param': params['value'],\n"
            "  'pointer': os.environ.get('CLOUISLE_CREDENTIALS_FILE'),\n"
            "}"
        ),
        metadata={"params": {"value": 7}},
        # A tool-definition env must not be able to spoof the reserved pointer.
        env={CREDENTIALS_ENV_VAR: "/tmp/spoofed-credentials.json"},
    )
    job = _envelope_for(job, {"api_key": "s3cret-value"})

    result = await manager.execute(job)

    assert result.success is True
    assert result.result == {"key": "s3cret-value", "param": 7, "pointer": None}
    workspace_root = workspace_manager.job_root(job.job_id)
    assert list((workspace_root / "tmp").glob(".clouisle-credentials-*")) == []


@pytest.mark.anyio
async def test_manager_rejects_credentials_for_command_only_jobs(tmp_path: Path):
    manager, _ = _local_manager(tmp_path)
    job = SandboxJob(
        source=SandboxJobSource.TOOL,
        command=["python", "script.py"],
    )
    job = _envelope_for(job, {"api_key": "s3cret-value"})

    with pytest.raises(SandboxCredentialError):
        await manager.execute(job)


@pytest.mark.anyio
async def test_manager_runs_snippet_without_credentials(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(settings, "SANDBOX_FILESYSTEM_ISOLATION_ENABLED", False)
    monkeypatch.setattr(settings, "SANDBOX_DEFAULT_PYTHON_BINARIES", [sys.executable])
    manager, _ = _local_manager(tmp_path)
    job = SandboxJob(
        source=SandboxJobSource.TOOL,
        language="python",
        code="return {'empty': credentials == {}, 'param': params['value']}",
        metadata={"params": {"value": 3}},
    )

    result = await manager.execute(job)

    assert result.success is True
    assert result.result == {"empty": True, "param": 3}


@pytest.mark.anyio
async def test_manager_fails_closed_on_malformed_envelope(tmp_path: Path):
    manager, _ = _local_manager(tmp_path)
    job = SandboxJob(
        source=SandboxJobSource.TOOL,
        language="python",
        code="return 1",
        metadata={CREDENTIALS_METADATA_KEY: "enc:tool:v1:key:broken"},
    )

    with pytest.raises(SandboxCredentialError):
        await manager.execute(job)


def test_code_tool_envelope_never_contains_plaintext():
    from app.services.tool import ToolExecutor

    job = SandboxJob(
        source=SandboxJobSource.TOOL,
        language="python",
        code="return credentials['api_key']",
        metadata={"params": {"value": 1}},
    )
    attached = ToolExecutor._attach_code_credentials(job, {"api_key": "s3cret-value"})

    dumped = attached.model_dump_json()
    assert "s3cret-value" not in dumped
    assert CREDENTIALS_METADATA_KEY in dumped
    assert decrypt_sandbox_credentials(
        attached.metadata[CREDENTIALS_METADATA_KEY], job_id=attached.job_id
    ) == {"api_key": "s3cret-value"}


def test_credentials_pointer_is_mapped_into_isolated_workspace(tmp_path: Path):
    launcher = SandboxProcessLauncher(filesystem_isolation_enabled=False)
    workspace = (tmp_path / "jobs" / "job-1").resolve()
    workspace.mkdir(parents=True)
    credential_file = workspace / "tmp" / ".clouisle-credentials-abc.json"

    mapped = launcher._map_workspace_value(
        str(credential_file), str(workspace), workspace
    )

    assert mapped == "/workspace/tmp/.clouisle-credentials-abc.json"


@pytest.mark.anyio
async def test_code_tool_uses_real_personal_and_team_connection_rows(
    tmp_path: Path, monkeypatch
):
    """Real SQLite connection rows flow through ToolExecutor into snippets."""
    from uuid import uuid4

    import app.services.tool as tool_service
    from tortoise import Tortoise

    from app.models.tool import Tool
    from app.models.tool_approval import ExecutionEntrypoint
    from app.models.user import Permission, Role, Team, TeamMember, User
    from app.schemas.tool_connection import ToolConnectionCreate
    from app.services.tool import ToolExecutor
    from app.services.tool_connections import ToolConnectionService
    from app.services.tool_execution import ToolCallContext

    monkeypatch.setattr(settings, "SANDBOX_FILESYSTEM_ISOLATION_ENABLED", False)
    monkeypatch.setattr(settings, "SANDBOX_DEFAULT_PYTHON_BINARIES", [sys.executable])

    manager, _ = _local_manager(tmp_path)

    class LocalGateway:
        async def submit_and_wait(self, job, **_kwargs):
            return await manager.execute(job)

    monkeypatch.setattr(tool_service, "sandbox_gateway", LocalGateway())

    await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["app.models"]})
    try:
        await Tortoise.generate_schemas()
        user = await User.create(
            username=f"code_creds_{uuid4().hex[:8]}",
            email=f"code-creds-{uuid4().hex[:8]}@test.invalid",
            hashed_password="x",
        )
        permission = await Permission.filter(code="team:read").first()
        if permission is None:
            permission = await Permission.create(
                id=uuid4(), scope="team", code="team:read"
            )
        role = await Role.create(id=uuid4(), name=f"Code creds {uuid4().hex[:6]}")
        await role.permissions.add(permission)
        await user.roles.add(role)
        team = await Team.create(name=f"Code creds {uuid4().hex[:6]}")
        await TeamMember.create(team=team, user=user, role="owner")
        tool = await Tool.create(
            name="code_connection_demo",
            display_name="Code Connection Demo",
            description="",
            team=team,
            created_by=user,
            type="custom",
            custom_type="code",
            code_config={
                "language": "python",
                "code": (
                    "return {\n"
                    "  'key': credentials['api_key'],\n"
                    "  'value': params['value'],\n"
                    "}"
                ),
            },
            identity_policy="selectable",
            connection_fields=[{"name": "api_key", "secret": True, "required": True}],
            approval_policy={"default_decision": "allow"},
            visibility="team",
        )
        await ToolConnectionService.create_connection(
            actor=user,
            payload=ToolConnectionCreate(
                team_id=team.id,
                tool_id=tool.id,
                scope="user",
                name="Personal account",
                config={"api_key": "personal-key"},
                is_default=True,
            ),
        )
        await ToolConnectionService.create_connection(
            actor=user,
            payload=ToolConnectionCreate(
                team_id=team.id,
                tool_id=tool.id,
                scope="team",
                name="Team account",
                config={"api_key": "team-key"},
                is_default=True,
            ),
        )
        other = await User.create(
            username=f"code_creds_other_{uuid4().hex[:8]}",
            email=f"code-creds-other-{uuid4().hex[:8]}@test.invalid",
            hashed_password="x",
        )
        other_role = await Role.create(
            id=uuid4(), name=f"Code creds other {uuid4().hex[:6]}"
        )
        await other_role.permissions.add(permission)
        await other.roles.add(other_role)
        await TeamMember.create(team=team, user=other, role="member")

        async def run(mode: str, actor=user):
            return await ToolExecutor().execute(
                tool,
                {"value": 9},
                context=ToolCallContext(
                    actor=actor,
                    team_id=team.id,
                    entrypoint=ExecutionEntrypoint.TOOL_TEST,
                    interactive=True,
                    connection_mode=mode,
                ),
                operation="code_connection_demo",
            )

        personal = await run("personal")
        team_result = await run("team")

        assert personal["result"] == {"key": "personal-key", "value": 9}
        assert team_result["result"] == {"key": "team-key", "value": 9}

        # Another member has no personal default for this tool and must not
        # inherit the first user's personal identity.
        from app.schemas.response import BusinessError

        with pytest.raises(BusinessError):
            await run("personal", actor=other)
    finally:
        await Tortoise.close_connections()
