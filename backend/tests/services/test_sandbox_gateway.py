from datetime import UTC, datetime

import pytest

from app.core.config import settings
from app.services.sandbox.compiler import compile_code_config_job, compile_legacy_code_job
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

        with pytest.raises(SandboxPolicyError, match="absolute http\(s\) URL"):
            sandbox_policy_engine.validate(job)

    def test_rejects_requests_above_disk_capacity(self):
        job = SandboxJob(
            command=["python"],
            limits={"disk_mb": settings.SANDBOX_MAX_DISK_MB + 1},
        )

        with pytest.raises(SandboxPolicyError, match="disk exceeds sandbox capacity"):
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
        return SandboxTaskStatus.RUNNING if self.status_calls >= self.terminal_after else SandboxTaskStatus.QUEUED

    async def get_result(self, job_id: str):
        del job_id
        self.get_result_calls += 1
        return self.result

    async def update_status(self, job_id: str, status: SandboxTaskStatus, *, metadata=None, **updates):
        result = self.result or SandboxResult(job_id=job_id, metadata=metadata or SandboxExecutionMetadata())
        result.status = status
        if metadata is not None:
            result.metadata = metadata
        for key, value in updates.items():
            setattr(result, key, value)
        self.result = result
        self.updated.append((job_id, status, updates.get("error")))
        return result


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
            final = await gateway.await_result("job-1", timeout_seconds=1, poll_interval=0)
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
            result = await gateway.await_result("job-timeout", timeout_seconds=0, poll_interval=0)
        finally:
            gateway_module.sandbox_result_store = original_store

        assert result.status == SandboxTaskStatus.FAILED
        assert result.error == "Sandbox job timed out while waiting for result"
        assert result.metadata.completed_at is not None
        assert result.metadata.duration_ms is not None
        assert result.metadata.total_ms == result.metadata.duration_ms
