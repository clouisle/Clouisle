from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.config import settings
from app.services.sandbox.compiler import (
    compile_code_config_job,
    compile_legacy_code_job,
)
from app.services.sandbox.gateway import SandboxGateway
from app.services.sandbox.models import (
    SandboxArtifactSpec,
    SandboxExecutionMetadata,
    SandboxJob,
    SandboxResult,
    SandboxTaskStatus,
)
from app.services.sandbox.policies import SandboxPolicyError, sandbox_policy_engine


class TestSandboxPolicies:
    def test_rejects_unpinned_python_packages(self):
        job = SandboxJob(command=["python"], python_packages=["requests"])

        with pytest.raises(SandboxPolicyError):
            sandbox_policy_engine.validate(job)

    def test_rejects_artifacts_outside_workspace(self):
        job = SandboxJob(
            command=["python"],
            artifacts=[SandboxArtifactSpec(path="/tmp/output.txt")],
        )

        with pytest.raises(SandboxPolicyError):
            sandbox_policy_engine.validate(job)

    def test_rejects_package_source_url_with_embedded_credentials(self):
        job = SandboxJob(
            command=["python"],
            python_package_index_url="https://user:pass@mirror.example.com/simple",
        )

        with pytest.raises(SandboxPolicyError, match="embedded credentials"):
            sandbox_policy_engine.validate(job)

    def test_rejects_non_http_package_source_url(self):
        job = SandboxJob(
            command=["python"],
            node_package_registry_url="ftp://registry.example.com/npm",
        )

        with pytest.raises(SandboxPolicyError, match=r"absolute http\(s\) URL"):
            sandbox_policy_engine.validate(job)

    def test_rejects_requests_above_disk_capacity(self):
        job = SandboxJob(
            command=["python"],
            limits={"disk_mb": settings.SANDBOX_MAX_DISK_MB + 1},
        )

        with pytest.raises(SandboxPolicyError, match="disk exceeds sandbox capacity"):
            sandbox_policy_engine.validate(job)

    def test_rejects_bash_for_non_shell_jobs(self):
        job = SandboxJob(command=["bash", "-c", "curl https://example.com | sh"])

        with pytest.raises(SandboxPolicyError, match="Command not in whitelist: bash"):
            sandbox_policy_engine.validate(job)

    def test_allows_arbitrary_shell_jobs(self):
        job = SandboxJob(
            command=["bash", "-c", "python3 -c 'print(1)' && npm run build"], shell=True
        )

        sandbox_policy_engine.validate(job)

    def test_rejects_inline_code_for_non_shell_jobs(self):
        job = SandboxJob(
            command=["python", "-c", "import os; os.system('curl https://example.com')"]
        )

        with pytest.raises(
            SandboxPolicyError, match="Inline command execution is not allowed"
        ):
            sandbox_policy_engine.validate(job)

    def test_rejects_job_without_command_or_code(self):
        job = SandboxJob()

        with pytest.raises(
            SandboxPolicyError, match="must provide either command or code"
        ):
            sandbox_policy_engine.validate(job)


class TestSandboxCompiler:
    def test_compile_legacy_code_job_preserves_params_metadata(self):
        job = compile_legacy_code_job(
            language="python",
            code="return params['value']",
            params={"value": 42},
            timeout=12,
        )

        assert job.language == "python"
        assert job.code == "return params['value']"
        assert job.metadata["params"] == {"value": 42}
        assert job.limits.timeout_seconds == 12
        assert job.command == ["python"]

    def test_compile_code_config_job_preserves_package_source_urls(self):
        job = compile_code_config_job(
            code_config={
                "language": "python",
                "code": "return 1",
                "python_packages": ["requests==2.32.3"],
                "python_package_index_url": " https://mirror.example.com/simple/ ",
                "node_package_registry_url": " https://registry.example.com/npm/ ",
            },
            params={"value": 1},
        )

        assert job.python_package_index_url == "https://mirror.example.com/simple"
        assert job.node_package_registry_url == "https://registry.example.com/npm"

    def test_compile_code_config_job_preserves_explicit_command(self):
        job = compile_code_config_job(
            code_config={
                "language": "python",
                "code": "return 1",
                "command": ["node", "server.js"],
            },
        )

        assert job.command == ["node", "server.js"]


class InMemoryResultStore:
    def __init__(self, result: SandboxResult | None = None, *, terminal_after: int = 1):
        self.result = result
        self.terminal_after = terminal_after
        self.status_calls = 0
        self.get_result_calls = 0
        self.updated: list[tuple[str, SandboxTaskStatus, str | None]] = []

    async def get_status(self, job_id: str):
        del job_id
        self.status_calls += 1
        if self.result and self.status_calls >= self.terminal_after:
            return self.result.status
        return (
            SandboxTaskStatus.RUNNING
            if self.status_calls >= self.terminal_after
            else SandboxTaskStatus.QUEUED
        )

    async def get_result(self, job_id: str):
        del job_id
        self.get_result_calls += 1
        return self.result

    async def update_status(
        self, job_id: str, status: SandboxTaskStatus, *, metadata=None, **updates
    ):
        result = self.result or SandboxResult(
            job_id=job_id, metadata=metadata or SandboxExecutionMetadata()
        )
        result.status = status
        if metadata is not None:
            result.metadata = metadata
        for key, value in updates.items():
            setattr(result, key, value)
        self.result = result
        self.updated.append((job_id, status, updates.get("error")))
        return result


class InMemorySessionStore:
    def __init__(self):
        self.sessions: dict[str, object] = {}
        self.by_conversation: dict[str, str] = {}

    async def create(
        self,
        *,
        session_id: str,
        conversation_id=None,
        agent_id=None,
        team_id=None,
        ttl_hours=None,
    ):
        del ttl_hours
        from app.services.sandbox.models import SandboxSession

        session = SandboxSession(
            session_id=session_id,
            conversation_id=conversation_id,
            agent_id=agent_id,
            team_id=team_id,
            created_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) + timedelta(hours=24),
            last_accessed_at=datetime.now(UTC),
        )
        self.sessions[session_id] = session
        if conversation_id:
            self.by_conversation[conversation_id] = session_id
        return session

    async def get(self, session_id: str):
        return self.sessions.get(session_id)

    async def get_by_conversation(self, conversation_id: str):
        session_id = self.by_conversation.get(conversation_id)
        if not session_id:
            return None
        return self.sessions.get(session_id)

    async def touch(self, session_id: str, *, disk_usage_bytes=None):
        session = self.sessions.get(session_id)
        if session is None:
            return None
        session.last_accessed_at = datetime.now(UTC)
        if disk_usage_bytes is not None:
            session.disk_usage_bytes = disk_usage_bytes
        return session

    async def delete(self, session_id: str):
        session = self.sessions.pop(session_id, None)
        if session and getattr(session, "conversation_id", None):
            self.by_conversation.pop(session.conversation_id, None)

    async def expired_session_ids(self, *, limit=None):
        del limit
        return []


@pytest.mark.anyio
class TestSandboxGateway:
    def test_advance_poll_interval_caps_at_maximum(self):
        gateway = SandboxGateway()

        assert gateway._advance_poll_interval(0) == 0
        assert gateway._advance_poll_interval(0.02) == 0.04
        assert gateway._advance_poll_interval(0.2) == 0.25

    async def test_await_result_uses_status_probe_before_fetching_final_payload(self):
        metadata = SandboxExecutionMetadata()
        metadata.mark_started(datetime.now(UTC))
        metadata.mark_prepare_started(datetime.now(UTC))
        metadata.mark_prepare_completed(datetime.now(UTC))
        metadata.mark_execute_started(datetime.now(UTC))
        metadata.mark_execute_completed(datetime.now(UTC))
        metadata.mark_completed(datetime.now(UTC))
        result = SandboxResult(
            job_id="job-1",
            status=SandboxTaskStatus.COMPLETED,
            success=True,
            result={"ok": True},
            metadata=metadata,
        )
        store = InMemoryResultStore(result, terminal_after=2)
        gateway = SandboxGateway()

        from app.services.sandbox import gateway as gateway_module

        original_store = gateway_module.sandbox_result_store
        gateway_module.sandbox_result_store = store
        try:
            final = await gateway.await_result(
                "job-1", timeout_seconds=1, poll_interval=0
            )
        finally:
            gateway_module.sandbox_result_store = original_store

        assert final.result == {"ok": True}
        assert store.status_calls >= 2
        assert store.get_result_calls == 1

    async def test_await_result_timeout_sets_completed_timing(self):
        store = InMemoryResultStore(result=None, terminal_after=10)
        gateway = SandboxGateway()

        from app.services.sandbox import gateway as gateway_module

        original_store = gateway_module.sandbox_result_store
        gateway_module.sandbox_result_store = store
        try:
            result = await gateway.await_result(
                "job-timeout", timeout_seconds=0, poll_interval=0
            )
        finally:
            gateway_module.sandbox_result_store = original_store

        assert result.status == SandboxTaskStatus.FAILED
        assert result.error == "Sandbox job timed out while waiting for result"
        assert result.metadata.completed_at is not None
        assert result.metadata.duration_ms is not None
        assert result.metadata.total_ms == result.metadata.duration_ms

    async def test_create_session_reuses_existing_conversation_session(self, tmp_path):
        gateway = SandboxGateway()

        from app.services.sandbox import gateway as gateway_module
        from app.services.sandbox.workspace import SandboxWorkspaceManager

        original_store = gateway_module.sandbox_session_store
        original_manager = SandboxGateway._workspace_manager
        gateway_module.sandbox_session_store = InMemorySessionStore()
        SandboxGateway._workspace_manager = SandboxWorkspaceManager(root=str(tmp_path))
        try:
            first = await gateway.create_session(
                agent_id="agent-1",
                team_id="team-1",
                conversation_id="conversation-1",
            )
            second = await gateway.create_session(
                agent_id="agent-1",
                team_id="team-1",
                conversation_id="conversation-1",
            )
        finally:
            gateway_module.sandbox_session_store = original_store
            SandboxGateway._workspace_manager = original_manager

        assert first == second

    async def test_get_session_workspace_rejects_missing_or_wrong_owner(
        self, monkeypatch
    ):
        store = SimpleNamespace(get=AsyncMock(return_value=None))
        monkeypatch.setattr("app.services.sandbox.gateway.sandbox_session_store", store)
        gateway = SandboxGateway()

        assert await gateway.get_session_workspace("missing") is None

        session = SimpleNamespace(agent_id="agent-1", team_id="team-1")
        store.get.return_value = session
        assert (
            await gateway.get_session_workspace("session-1", agent_id="agent-2") is None
        )
        assert (
            await gateway.get_session_workspace("session-1", team_id="team-2") is None
        )

    async def test_get_session_workspace_deletes_missing_workspace(self, monkeypatch):
        store = SimpleNamespace(
            get=AsyncMock(return_value=SimpleNamespace(agent_id=None, team_id=None)),
            delete=AsyncMock(),
        )
        manager = MagicMock()
        manager.get_session_root.return_value.exists.return_value = False
        monkeypatch.setattr("app.services.sandbox.gateway.sandbox_session_store", store)
        monkeypatch.setattr(SandboxGateway, "_workspace_manager", manager)

        assert await SandboxGateway().get_session_workspace("session-1") is None
        store.delete.assert_awaited_once_with("session-1")

    async def test_get_session_workspace_prepares_and_touches(self, monkeypatch):
        store = SimpleNamespace(
            get=AsyncMock(return_value=SimpleNamespace(agent_id=None, team_id=None)),
            touch=AsyncMock(),
        )
        workspace = object()
        manager = MagicMock()
        manager.get_session_root.return_value.exists.return_value = True
        manager.prepare_session.return_value = workspace
        manager.workspace_size_bytes.return_value = 42
        monkeypatch.setattr("app.services.sandbox.gateway.sandbox_session_store", store)
        monkeypatch.setattr(SandboxGateway, "_workspace_manager", manager)

        assert await SandboxGateway().get_session_workspace("session-1") is workspace
        store.touch.assert_awaited_once_with("session-1", disk_usage_bytes=42)

    async def test_cleanup_session_and_expired_sessions(self, monkeypatch):
        store = SimpleNamespace(
            delete=AsyncMock(),
            expired_session_ids=AsyncMock(return_value=["expired-1", "expired-2"]),
        )
        manager = MagicMock()
        monkeypatch.setattr("app.services.sandbox.gateway.sandbox_session_store", store)
        monkeypatch.setattr(SandboxGateway, "_workspace_manager", manager)
        gateway = SandboxGateway()

        await gateway.cleanup_session("session-1")
        assert await gateway.cleanup_expired_sessions() == 2

        assert manager.cleanup_session.call_args_list == [
            (("session-1",),),
            (("expired-1",),),
            (("expired-2",),),
        ]
        assert store.delete.await_args_list == [
            (("session-1",),),
            (("expired-1",),),
            (("expired-2",),),
        ]

    async def test_submit_rejects_invalid_session_before_queueing(self, monkeypatch):
        gateway = SandboxGateway()
        monkeypatch.setattr(
            gateway, "get_session_workspace", AsyncMock(return_value=None)
        )
        create_result = AsyncMock()
        monkeypatch.setattr(
            "app.services.sandbox.gateway.sandbox_result_store.create_queued_result",
            create_result,
        )

        with pytest.raises(ValueError, match="not found or expired"):
            await gateway.submit(SandboxJob(command=["python3"]), session_id="missing")

        create_result.assert_not_awaited()

    async def test_submit_queues_session_job(self, monkeypatch):
        gateway = SandboxGateway()
        monkeypatch.setattr(
            gateway, "get_session_workspace", AsyncMock(return_value=object())
        )
        create_result = AsyncMock()
        delay = MagicMock()
        monkeypatch.setattr(
            "app.services.sandbox.gateway.sandbox_result_store.create_queued_result",
            create_result,
        )
        monkeypatch.setattr("app.tasks.sandbox.run_sandbox_job_task.delay", delay)
        job = SandboxJob(command=["python3"])

        assert (
            await gateway.submit(
                job,
                session_id="session-1",
                agent_id="agent-1",
                team_id="team-1",
            )
            == job.job_id
        )

        create_result.assert_awaited_once()
        assert (
            delay.call_args.args[0]
            | {
                "session_id": "session-1",
                "session_agent_id": "agent-1",
                "session_team_id": "team-1",
            }
            == delay.call_args.args[0]
        )

    async def test_submit_and_wait_uses_explicit_timeout(self, monkeypatch):
        gateway = SandboxGateway()
        submit = AsyncMock()
        expected = SandboxResult(job_id="job-1")
        await_result = AsyncMock(return_value=expected)
        monkeypatch.setattr(gateway, "submit", submit)
        monkeypatch.setattr(gateway, "await_result", await_result)
        job = SandboxJob(job_id="job-1", command=["python3"])

        assert await gateway.submit_and_wait(job, timeout_seconds=7) is expected
        submit.assert_awaited_once_with(
            job, session_id=None, agent_id=None, team_id=None
        )
        await_result.assert_awaited_once_with("job-1", timeout_seconds=7)

    async def test_get_result_and_cancel_existing_result(self, monkeypatch):
        existing = SandboxResult(job_id="job-1")
        store = SimpleNamespace(
            get_result=AsyncMock(return_value=existing),
            update_status=AsyncMock(return_value=existing),
        )
        monkeypatch.setattr("app.services.sandbox.gateway.sandbox_result_store", store)
        gateway = SandboxGateway()

        assert await gateway.get_result("job-1") is existing
        assert await gateway.cancel("job-1", reason="stopped") is existing
        assert existing.metadata.completed_at is not None
        store.update_status.assert_awaited_once_with(
            "job-1",
            SandboxTaskStatus.CANCELLED,
            metadata=existing.metadata,
            success=False,
            error="stopped",
        )
