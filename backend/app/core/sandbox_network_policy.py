"""Allowlist rules for sandbox egress and package sources."""

from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlsplit

DEFAULT_SANDBOX_NETWORK_ALLOWLIST = [
    "pypi.org",
    "files.pythonhosted.org",
    "pypi.python.org",
    "registry.npmjs.org",
]
SANDBOX_NETWORK_ALLOWLIST_MAX_ENTRIES = 200
SANDBOX_NETWORK_ALLOWLIST_SETTING = "sandbox_network_allowlist"
_DOMAIN_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


class SandboxNetworkPolicyError(ValueError):
    def __init__(self, message: str, *, host: str | None = None) -> None:
        self.host = host
        super().__init__(message)


def normalize_sandbox_network_host(value: str) -> str:
    if not isinstance(value, str):
        raise SandboxNetworkPolicyError("Sandbox network host must be a string")

    host = value.strip().rstrip(".")
    if not host or any(character.isspace() for character in host):
        raise SandboxNetworkPolicyError("Sandbox network host is invalid", host=value)

    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise SandboxNetworkPolicyError(
            "Sandbox network allowlist entries must be DNS names", host=host
        )

    try:
        normalized = host.encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise SandboxNetworkPolicyError(
            "Sandbox network host is invalid", host=host
        ) from exc

    labels = normalized.split(".")
    if (
        len(normalized) > 253
        or len(labels) < 2
        or any(not _DOMAIN_LABEL.fullmatch(label) for label in labels)
    ):
        raise SandboxNetworkPolicyError("Sandbox network host is invalid", host=host)
    return normalized


def normalize_sandbox_network_allowlist(value: object) -> list[str]:
    if not isinstance(value, (list, tuple)):
        raise SandboxNetworkPolicyError("Sandbox network allowlist must be a list")
    entries = list(value)

    if len(entries) > SANDBOX_NETWORK_ALLOWLIST_MAX_ENTRIES:
        raise SandboxNetworkPolicyError("Sandbox network allowlist is too large")

    normalized: list[str] = []
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, str):
            raise SandboxNetworkPolicyError("Sandbox network allowlist is invalid")
        host = normalize_sandbox_network_host(entry)
        if host not in seen:
            seen.add(host)
            normalized.append(host)
    return normalized


def normalize_sandbox_package_source(
    value: str,
    allowlist: list[str] | tuple[str, ...],
) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SandboxNetworkPolicyError("Package source URL is invalid")

    parsed = urlsplit(value.strip())
    try:
        port = parsed.port
    except ValueError as exc:
        raise SandboxNetworkPolicyError(
            "Package source URL is invalid", host=parsed.hostname
        ) from exc

    if (
        parsed.scheme.lower() != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or port not in {None, 443}
    ):
        raise SandboxNetworkPolicyError(
            "Package source URL must use HTTPS without credentials or a custom port",
            host=parsed.hostname,
        )

    host = normalize_sandbox_network_host(parsed.hostname)
    allowed = set(normalize_sandbox_network_allowlist(allowlist))
    if host not in allowed:
        raise SandboxNetworkPolicyError(
            f"Sandbox network blocked package source host: {host}", host=host
        )

    path = parsed.path.rstrip("/")
    return f"https://{host}{path}"


def sandbox_network_host_is_allowed(
    host: str, allowlist: list[str] | tuple[str, ...]
) -> bool:
    try:
        normalized = normalize_sandbox_network_host(host)
        allowed = normalize_sandbox_network_allowlist(allowlist)
    except SandboxNetworkPolicyError:
        return False
    return normalized in allowed


async def get_sandbox_network_allowlist() -> list[str]:
    """Load the current sandbox egress policy from security site settings."""
    from app.models.site_setting import SiteSetting

    try:
        value = await SiteSetting.get_value(
            SANDBOX_NETWORK_ALLOWLIST_SETTING,
            list(DEFAULT_SANDBOX_NETWORK_ALLOWLIST),
        )
        return normalize_sandbox_network_allowlist(value)
    except Exception:
        return []
