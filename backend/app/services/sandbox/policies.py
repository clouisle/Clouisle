"""Sandbox policy validation."""

from __future__ import annotations

import os
import re
from urllib.parse import urlsplit

from app.core.config import settings

from .models import SandboxJob

_PINNED_PYTHON_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+==[^=].+$")
_PINNED_JS_PATTERN = re.compile(r"^[^\s@][^\s]*@[^\s].+$")

ALLOWED_EXECUTABLES = frozenset({
    "python",
    "python3",
    "javascript",
    "node",
    "nodejs",
})
def _validate_package_source_url(url: str | None, *, label: str) -> None:
    if not url:
        return

    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise SandboxPolicyError(f"{label} must be an absolute http(s) URL")
    if parsed.username is not None or parsed.password is not None:
        raise SandboxPolicyError(f"{label} must not include embedded credentials")


class SandboxPolicyError(ValueError):
    """Raised when a sandbox job violates policy."""


class SandboxPolicyEngine:
    def validate(self, job: SandboxJob) -> None:
        if job.shell and not job.command:
            raise SandboxPolicyError("Shell mode requires a command")

        if not job.command and not job.code:
            raise SandboxPolicyError("Sandbox jobs must provide either command or code")

        if job.command and not job.shell:
            self._validate_command(job.command)

        for package in job.python_packages:
            if not _PINNED_PYTHON_PATTERN.match(package):
                raise SandboxPolicyError(
                    f"Python package '{package}' must use an exact pinned version"
                )

        for package in job.js_packages:
            if not _PINNED_JS_PATTERN.match(package):
                raise SandboxPolicyError(
                    f"JavaScript package '{package}' must use an exact pinned version"
                )

        _validate_package_source_url(
            job.python_package_index_url,
            label="Python package index URL",
        )
        _validate_package_source_url(
            job.node_package_registry_url,
            label="Node package registry URL",
        )

        if job.limits.disk_mb > settings.SANDBOX_MAX_DISK_MB:
            raise SandboxPolicyError(
                f"Requested disk exceeds sandbox capacity ({settings.SANDBOX_MAX_DISK_MB} MB)"
            )

        if any(not artifact.path.startswith("/workspace") for artifact in job.artifacts):
            raise SandboxPolicyError("Artifacts must stay inside /workspace")

    def _validate_command(self, command: list[str]) -> None:
        if not command:
            return

        executable = command[0]
        if not executable:
            return

        basename = os.path.basename(executable) if os.path.isabs(executable) else executable
        if basename not in ALLOWED_EXECUTABLES:
            raise SandboxPolicyError(
                f"Command not in whitelist: {basename}. "
                f"Allowed: {', '.join(sorted(ALLOWED_EXECUTABLES))}"
            )

        if any(arg == "-c" for arg in command[1:]):
            raise SandboxPolicyError("Inline command execution is not allowed")


sandbox_policy_engine = SandboxPolicyEngine()
