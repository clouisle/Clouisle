import ipaddress
import socket
from collections.abc import Iterable
from urllib.parse import urlparse

from app.schemas.response import BusinessError

SSRF_ALLOWED_TARGETS_SETTING = "ssrf_allowed_targets"
SSRF_ALLOWED_TARGETS_MAX_ENTRIES = 200

_BLOCKED_HOSTS = {"localhost", "local", "metadata.google.internal"}
_CRITICAL_BLOCKED_HOSTS = {"metadata.google.internal"}
_CRITICAL_BLOCKED_NETWORKS = (
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("224.0.0.0/4"),
    ipaddress.ip_network("0.0.0.0/32"),
)
_FAKE_IP_NETWORK = ipaddress.ip_network("198.18.0.0/15")


class _ValidatedExternalUrl(str):
    """Marker string type representing a validated external URL."""

    pass


def _is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Check whether the provided IP address is in a reserved, private, or local range."""
    return any(
        (
            ip.is_private,
            ip.is_loopback,
            ip.is_link_local,
            ip.is_reserved,
            ip.is_multicast,
            ip.is_unspecified,
        )
    )


def _is_fake_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Check whether the provided IP address belongs to the transparent proxy Fake-IP benchmark pool (198.18.0.0/15)."""
    return isinstance(ip, ipaddress.IPv4Address) and ip in _FAKE_IP_NETWORK


def _is_critical_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Check whether the provided IP address is in a non-bypassable critical network range (cloud metadata, multicast, unspecified)."""
    return any(ip in net for net in _CRITICAL_BLOCKED_NETWORKS)


def normalize_ssrf_allowlist_entry(value: str) -> str:
    """Validate and normalize a single SSRF allowlist entry (IP, CIDR, or hostname/pattern)."""
    if not isinstance(value, str):
        raise BusinessError(msg_key="ssrf_allowlist_entry_invalid")
    clean = value.strip().lower()
    if not clean or any(c in clean for c in "/?#@ \t\r\n"):
        # Allow single slash only if it is a valid CIDR
        if "/" in clean:
            try:
                net = ipaddress.ip_network(clean, strict=False)
                # Forbid universal wildcards like 0.0.0.0/0 or ::/0
                if net.prefixlen == 0:
                    raise BusinessError(msg_key="ssrf_allowlist_entry_forbidden")
                # Forbid cloud metadata CIDR
                if any(net.overlaps(crit) for crit in _CRITICAL_BLOCKED_NETWORKS):
                    raise BusinessError(msg_key="ssrf_allowlist_entry_forbidden")
                return str(net)
            except (ValueError, TypeError) as exc:
                raise BusinessError(msg_key="ssrf_allowlist_entry_invalid") from exc
        raise BusinessError(msg_key="ssrf_allowlist_entry_invalid")

    # Check forbidden entries
    if clean in {"169.254.169.254", "0.0.0.0", "::", "metadata.google.internal", "*"}:
        raise BusinessError(msg_key="ssrf_allowlist_entry_forbidden")

    # Single IP address
    try:
        ip = ipaddress.ip_address(clean)
        if _is_critical_blocked_ip(ip):
            raise BusinessError(msg_key="ssrf_allowlist_entry_forbidden")
        return str(ip)
    except ValueError:
        pass

    # Hostname or wildcard pattern like *.corp.internal or oa.company.local
    pattern = clean.lstrip(".")
    if pattern.startswith("*."):
        base_domain = pattern[2:]
        if (
            not base_domain
            or "." not in base_domain
            or "*" in base_domain
            or any(c in base_domain for c in ":/")
        ):
            raise BusinessError(msg_key="ssrf_allowlist_entry_invalid")
        return f"*.{base_domain}"

    if "*" in pattern or ":" in pattern:
        raise BusinessError(msg_key="ssrf_allowlist_entry_invalid")

    # Hostname must contain at least one dot or be a recognized internal hostname
    if "." not in pattern or pattern.startswith(".") or pattern.endswith("."):
        raise BusinessError(msg_key="ssrf_allowlist_entry_invalid")

    return pattern


def normalize_ssrf_allowlist(value: object) -> list[str]:
    """Normalize a full SSRF allowlist configuration value."""
    if not isinstance(value, list) or len(value) > SSRF_ALLOWED_TARGETS_MAX_ENTRIES:
        raise BusinessError(msg_key="ssrf_allowlist_invalid")

    normalized: list[str] = []
    seen: set[str] = set()
    for entry in value:
        norm = normalize_ssrf_allowlist_entry(str(entry))
        if norm not in seen:
            seen.add(norm)
            normalized.append(norm)
    return normalized


def is_target_allowlisted(
    host: str,
    resolved_ips: list[ipaddress.IPv4Address | ipaddress.IPv6Address],
    allowlist: Iterable[str],
) -> bool:
    """Check whether a host or its resolved IPs match the SSRF exemption allowlist."""
    clean_host = host.lower().rstrip(".")

    for rule in allowlist:
        rule = rule.strip().lower()
        if not rule:
            continue

        # Try CIDR / IP match
        try:
            net = ipaddress.ip_network(rule, strict=False)
            if any(ip in net for ip in resolved_ips):
                return True
            continue
        except ValueError:
            pass

        # Wildcard host match (*.corp.internal)
        if rule.startswith("*."):
            domain = rule[2:]
            if clean_host == domain or clean_host.endswith(f".{domain}"):
                return True
        elif clean_host == rule:
            return True

    return False


async def get_ssrf_allowed_targets() -> list[str]:
    """Retrieve the administrator-approved SSRF exemption targets from SiteSetting."""
    try:
        from app.models.site_setting import SiteSetting

        value = await SiteSetting.get_value(
            SSRF_ALLOWED_TARGETS_SETTING,
            [],
        )
        return normalize_ssrf_allowlist(value)
    except Exception:
        return []


def validate_external_http_url(
    value: str,
    getaddrinfo=None,
    allowlist: Iterable[str] | None = None,
) -> _ValidatedExternalUrl:
    """Validate an external HTTP/HTTPS URL against blocked hosts, private IPs, and metadata targets."""
    if getaddrinfo is None:
        getaddrinfo = socket.getaddrinfo
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise BusinessError(msg_key="http_tool_url_invalid")
    host = parsed.hostname.lower().rstrip(".")
    if host in _BLOCKED_HOSTS and not (
        allowlist and is_target_allowlisted(host, [], allowlist)
    ):
        reason = (
            "loopback address"
            if host in {"localhost", "local"}
            else "cloud metadata address"
        )
        raise BusinessError(
            msg_key="http_tool_url_host_not_allowed",
            host=host,
            reason=reason,
        )
    try:
        port = parsed.port
    except ValueError:
        raise BusinessError(msg_key="http_tool_url_invalid")

    try:
        resolved = getaddrinfo(host, port or None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise BusinessError(msg_key="http_tool_url_host_cannot_be_resolved") from exc

    resolved_ips = [ipaddress.ip_address(sockaddr[0]) for *_, sockaddr in resolved]

    # Critical non-bypassable blocked IPs (metadata, broadcast, etc.)
    for ip in resolved_ips:
        if _is_critical_blocked_ip(ip):
            raise BusinessError(
                msg_key="http_tool_url_host_not_allowed",
                host=host,
                ip=str(ip),
                reason="cloud metadata address",
            )

    # Check each resolved IP: must either be public, fake-IP, or explicitly allowlisted
    for ip in resolved_ips:
        if _is_fake_ip(ip):
            continue
        is_ip_blocked = ip.is_loopback or _is_blocked_ip(ip)
        if is_ip_blocked:
            ip_exempt = bool(allowlist and is_target_allowlisted(host, [ip], allowlist))
            if not ip_exempt:
                reason = (
                    "loopback address" if ip.is_loopback else f"private address {ip}"
                )
                raise BusinessError(
                    msg_key="http_tool_url_host_not_allowed",
                    host=host,
                    ip=str(ip),
                    reason=reason,
                )

    return _ValidatedExternalUrl(value)


async def ensure_external_http_url_allowed(
    value: str,
    getaddrinfo=None,
) -> _ValidatedExternalUrl:
    """Async helper that loads current SSRF allowlist from SiteSetting and validates the URL."""
    allowlist = await get_ssrf_allowed_targets()
    import asyncio

    return await asyncio.to_thread(
        validate_external_http_url,
        value,
        getaddrinfo=getaddrinfo,
        allowlist=allowlist,
    )


def validate_external_host(
    host: str,
    port: int | None = None,
    getaddrinfo=None,
    error_key: str = "database_host_not_allowed",
    invalid_key: str = "database_host_invalid",
    unresolvable_key: str = "database_host_cannot_be_resolved",
    allowlist: Iterable[str] | None = None,
) -> str:
    """Validate a hostname or IP against blocked hosts, private IPs, and metadata targets."""
    if getaddrinfo is None:
        getaddrinfo = socket.getaddrinfo
    clean_host = (host or "").strip().lower().rstrip(".")
    if not clean_host:
        raise BusinessError(msg_key=invalid_key)
    if port is not None and not (1 <= port <= 65535):
        raise BusinessError(msg_key=invalid_key)
    if clean_host in _BLOCKED_HOSTS and not (
        allowlist and is_target_allowlisted(clean_host, [], allowlist)
    ):
        raise BusinessError(msg_key=error_key)

    try:
        resolved = getaddrinfo(clean_host, port or None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise BusinessError(msg_key=unresolvable_key) from exc

    resolved_ips = [ipaddress.ip_address(sockaddr[0]) for *_, sockaddr in resolved]

    for ip in resolved_ips:
        if _is_critical_blocked_ip(ip):
            raise BusinessError(msg_key=error_key)

    if any(_is_fake_ip(ip) for ip in resolved_ips):
        return clean_host

    if allowlist and is_target_allowlisted(clean_host, resolved_ips, allowlist):
        return clean_host

    for ip in resolved_ips:
        if _is_blocked_ip(ip):
            raise BusinessError(msg_key=error_key)
    return clean_host


def validate_database_config(
    db_config: dict,
    getaddrinfo=None,
    allowlist: Iterable[str] | None = None,
) -> None:
    targets: list[tuple[str, int | None]] = []
    raw_host = db_config.get("host")
    if raw_host:
        raw_port = db_config.get("port")
        port = None
        if raw_port is not None:
            try:
                port = int(raw_port)
            except (ValueError, TypeError) as exc:
                raise BusinessError(msg_key="database_host_invalid") from exc
            if not (1 <= port <= 65535):
                raise BusinessError(msg_key="database_host_invalid")
        targets.append((str(raw_host).strip(), port))

    raw_url = db_config.get("url") or db_config.get("uri")
    if raw_url:
        try:
            parsed = urlparse(str(raw_url).strip())
            netloc = parsed.netloc
            if "@" in netloc:
                netloc = netloc.split("@", 1)[1]
            for host_spec in netloc.split(","):
                host_spec = host_spec.strip()
                if not host_spec:
                    continue
                p = urlparse("//" + host_spec)
                port_val = p.port
                if port_val is not None and not (1 <= port_val <= 65535):
                    raise BusinessError(msg_key="database_host_invalid")
                if p.hostname:
                    targets.append((p.hostname, port_val))
        except (ValueError, TypeError) as exc:
            raise BusinessError(msg_key="database_host_invalid") from exc
    if not targets:
        # If neither host nor url is provided, check if default host would be used or raise invalid
        raise BusinessError(msg_key="database_host_invalid")

    for host, port in targets:
        validate_external_host(
            host=host,
            port=port,
            getaddrinfo=getaddrinfo,
            error_key="database_host_not_allowed",
            invalid_key="database_host_invalid",
            unresolvable_key="database_host_cannot_be_resolved",
            allowlist=allowlist,
        )
