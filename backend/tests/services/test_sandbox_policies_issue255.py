"""Branch coverage for the isolated sandbox policy validator (#255)."""

import pytest

from app.services.sandbox.models import SandboxArtifactSpec, SandboxJob, SandboxLimits
from app.services.sandbox.policies import SandboxPolicyEngine, SandboxPolicyError


def test_policy_accepts_pinned_packages_workspace_artifacts_and_shell_commands():
    job = SandboxJob(
        shell=True,
        command=["unrestricted-shell-command", "-c", "echo ok"],
        python_packages=["requests==2.32.3"],
        js_packages=["eslint@9.25.1"],
        python_package_index_url="https://packages.example.com/simple",
        node_package_registry_url="https://registry.example.com/npm",
        artifacts=[SandboxArtifactSpec(path="/workspace/output.txt")],
    )

    SandboxPolicyEngine().validate(job)


def test_policy_accepts_empty_package_sources_and_absolute_allowed_command():
    job = SandboxJob(code="print('ok')", command=["/usr/bin/python3"])

    SandboxPolicyEngine().validate(job)


@pytest.mark.parametrize(
    ("job", "message"),
    [
        (SandboxJob(shell=True, code="print('ok')"), "Shell mode requires a command"),
        (SandboxJob(), "must provide either command or code"),
        (SandboxJob(command=["bash"]), "Command not in whitelist"),
        (SandboxJob(command=["python", "-c", "print('ok')"]), "Inline command"),
        (
            SandboxJob(code="ok", python_packages=["requests>=2"]),
            "must use an exact pinned version",
        ),
        (
            SandboxJob(code="ok", js_packages=["eslint"]),
            "must use an exact pinned version",
        ),
        (
            SandboxJob(
                code="ok", python_package_index_url="ftp://packages.example.com"
            ),
            r"must be an absolute http\(s\) URL",
        ),
        (
            SandboxJob(
                code="ok", node_package_registry_url="https://user:pass@example.com"
            ),
            "must not include embedded credentials",
        ),
        (
            SandboxJob(
                code="ok",
                artifacts=[SandboxArtifactSpec(path="/tmp/output.txt")],
            ),
            "Artifacts must stay inside /workspace",
        ),
    ],
)
def test_policy_rejects_invalid_jobs(job, message):
    with pytest.raises(SandboxPolicyError, match=message):
        SandboxPolicyEngine().validate(job)


def test_policy_rejects_disk_request_above_configured_capacity(monkeypatch):
    monkeypatch.setattr("app.services.sandbox.policies.settings.SANDBOX_MAX_DISK_MB", 1)
    job = SandboxJob(code="ok", limits=SandboxLimits(disk_mb=2))

    with pytest.raises(
        SandboxPolicyError, match="Requested disk exceeds sandbox capacity"
    ):
        SandboxPolicyEngine().validate(job)


def test_command_validator_ignores_empty_command_and_empty_executable():
    engine = SandboxPolicyEngine()

    engine._validate_command([])
    engine._validate_command([""])
