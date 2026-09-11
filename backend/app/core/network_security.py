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
