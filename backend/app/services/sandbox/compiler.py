"""Sandbox compiler helpers."""

from __future__ import annotations

from typing import Any

from .cache import normalize_package_source_url
from .models import SandboxArtifactSpec, SandboxJob, SandboxJobSource


def normalize_code_config(code_config: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(code_config)

    language = normalized.get("language", "python")
    python_packages = list(normalized.get("python_packages") or [])
    js_packages = list(normalized.get("js_packages") or [])
    legacy_packages = list(normalized.get("dependencies") or [])

    if language == "python" and not python_packages:
        python_packages = legacy_packages
    elif language == "javascript" and not js_packages:
        js_packages = legacy_packages

    normalized["python_packages"] = python_packages
    normalized["js_packages"] = js_packages
    normalized["python_package_index_url"] = normalize_package_source_url(
        normalized.get("python_package_index_url")
    )
    normalized["node_package_registry_url"] = normalize_package_source_url(
        normalized.get("node_package_registry_url")
    )
    normalized.pop("dependencies", None)
    normalized.pop("runtime_profile", None)
    normalized.pop("shell", None)
    return normalized


def compile_legacy_code_job(
    *,
    language: str,
    code: str,
    params: dict[str, Any] | None = None,
    timeout: float = 30.0,
    source: SandboxJobSource = SandboxJobSource.LEGACY_SNIPPET,
) -> SandboxJob:
    return SandboxJob(
        source=source,
        language=language,
        code=code,
        command=[language],
        limits={"timeout_seconds": timeout},
        metadata={"params": params or {}},
    )


def compile_code_config_job(
    *,
    code_config: dict[str, Any],
    params: dict[str, Any] | None = None,
    timeout: float = 30.0,
    source: SandboxJobSource = SandboxJobSource.TOOL,
) -> SandboxJob:
    normalized_code_config = normalize_code_config(code_config)
    limits = dict(normalized_code_config.get("limits") or {})
    limits.setdefault("timeout_seconds", timeout)

    artifacts = [
        artifact
        if isinstance(artifact, SandboxArtifactSpec)
        else SandboxArtifactSpec.model_validate(artifact)
        for artifact in (normalized_code_config.get("artifacts") or [])
    ]

    language = normalized_code_config.get("language", "python")
    code = normalized_code_config.get("code", "")
    command = list(normalized_code_config.get("command") or [])
    python_packages = list(normalized_code_config.get("python_packages") or [])
    js_packages = list(normalized_code_config.get("js_packages") or [])
    python_package_index_url = normalized_code_config.get("python_package_index_url")
    node_package_registry_url = normalized_code_config.get("node_package_registry_url")

    if not command:
        command = [language]

    return SandboxJob(
        source=source,
        language=language,
        code=code,
        command=command,
        python_packages=python_packages,
        js_packages=js_packages,
        python_package_index_url=python_package_index_url,
        node_package_registry_url=node_package_registry_url,
        artifacts=artifacts,
        limits=limits,
        metadata={"params": params or {}},
    )
