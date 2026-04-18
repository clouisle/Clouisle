"""Sandbox policy validation."""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from app.core.config import settings

from .models import SandboxJob

_PINNED_PYTHON_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+==[^=].+$")
_PINNED_JS_PATTERN = re.compile(r"^[^\s@][^\s]*@[^\s].+$")


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
        if job.shell:
            raise SandboxPolicyError("Shell execution is disabled for sandbox jobs")

        if not job.command and not job.code:
            raise SandboxPolicyError("Sandbox jobs must provide either command or code")

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


sandbox_policy_engine = SandboxPolicyEngine()
