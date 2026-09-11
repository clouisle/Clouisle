import ipaddress
import socket
from urllib.parse import urlparse

from app.schemas.response import BusinessError

_BLOCKED_HOSTS = {"localhost", "local", "metadata.google.internal"}


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


def validate_external_http_url(value: str, getaddrinfo=None) -> _ValidatedExternalUrl:
    """Validate an external HTTP/HTTPS URL against blocked hosts, private IPs, and metadata targets."""
    if getaddrinfo is None:
        getaddrinfo = socket.getaddrinfo
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise BusinessError(msg_key="http_tool_url_invalid")
    host = parsed.hostname.lower().rstrip(".")
    if host in _BLOCKED_HOSTS:
        raise BusinessError(msg_key="http_tool_url_host_not_allowed")
    try:
        port = parsed.port
    except ValueError:
        raise BusinessError(msg_key="http_tool_url_invalid")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip and _is_blocked_ip(ip):
        raise BusinessError(msg_key="http_tool_url_host_not_allowed")
    try:
        resolved = getaddrinfo(host, port or None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise BusinessError(msg_key="http_tool_url_host_cannot_be_resolved") from exc
    for *_, sockaddr in resolved:
        if _is_blocked_ip(ipaddress.ip_address(sockaddr[0])):
            raise BusinessError(msg_key="http_tool_url_host_not_allowed")
    return _ValidatedExternalUrl(value)


def validate_external_host(
    host: str,
    port: int | None = None,
    getaddrinfo=None,
    error_key: str = "database_host_not_allowed",
    invalid_key: str = "database_host_invalid",
    unresolvable_key: str = "database_host_cannot_be_resolved",
) -> str:
    """Validate a hostname or IP against blocked hosts, private IPs, and metadata targets."""
    if getaddrinfo is None:
        getaddrinfo = socket.getaddrinfo
    clean_host = (host or "").strip().lower().rstrip(".")
    if not clean_host:
        raise BusinessError(msg_key=invalid_key)
    if port is not None and not (1 <= port <= 65535):
        raise BusinessError(msg_key=invalid_key)
    if clean_host in _BLOCKED_HOSTS:
        raise BusinessError(msg_key=error_key)
    try:
        ip = ipaddress.ip_address(clean_host)
    except ValueError:
        ip = None
    if ip and _is_blocked_ip(ip):
        raise BusinessError(msg_key=error_key)
    try:
        resolved = getaddrinfo(clean_host, port or None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise BusinessError(msg_key=unresolvable_key) from exc
    for *_, sockaddr in resolved:
        if _is_blocked_ip(ipaddress.ip_address(sockaddr[0])):
            raise BusinessError(msg_key=error_key)
    return clean_host


def validate_database_config(db_config: dict, getaddrinfo=None) -> None:
    """Extract all network targets from a database configuration and validate against SSRF."""
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
        )
