import ipaddress
import socket
from unittest.mock import patch

import pytest

from app.core.network_security import (
    _is_blocked_ip,
    validate_external_host,
    validate_database_config,
    validate_external_http_url,
)
from app.schemas.response import BusinessError


def test_is_blocked_ip_covers_all_types():
    assert _is_blocked_ip(ipaddress.ip_address("127.0.0.1")) is True
    assert _is_blocked_ip(ipaddress.ip_address("10.0.0.1")) is True
    assert _is_blocked_ip(ipaddress.ip_address("169.254.1.1")) is True
    assert _is_blocked_ip(ipaddress.ip_address("224.0.0.1")) is True
    assert _is_blocked_ip(ipaddress.ip_address("0.0.0.0")) is True
    assert _is_blocked_ip(ipaddress.ip_address("240.0.0.1")) is True
    assert _is_blocked_ip(ipaddress.ip_address("8.8.8.8")) is False

    # IPv6
    assert _is_blocked_ip(ipaddress.ip_address("::1")) is True
    assert _is_blocked_ip(ipaddress.ip_address("fe80::1")) is True
    assert _is_blocked_ip(ipaddress.ip_address("2001:4860:4860::8888")) is False


@pytest.mark.parametrize(
    "url,error",
    [
        ("not_a_url", "http_tool_url_invalid"),
        ("ftp://example.com", "http_tool_url_invalid"),
        ("http://", "http_tool_url_invalid"),
        ("https://example.com:badport", "http_tool_url_invalid"),
        ("http://localhost", "http_tool_url_host_not_allowed"),
        ("http://local", "http_tool_url_host_not_allowed"),
        ("http://metadata.google.internal", "http_tool_url_host_not_allowed"),
        ("http://127.0.0.1", "http_tool_url_host_not_allowed"),
        ("http://169.254.169.254", "http_tool_url_host_not_allowed"),
        ("http://[::1]", "http_tool_url_host_not_allowed"),
    ],
)
def test_validate_external_http_url_rejections(url, error):
    with pytest.raises(BusinessError) as exc_info:
        validate_external_http_url(url)
    assert exc_info.value.msg_key == error


def test_validate_external_http_url_dns_resolution():
    with patch("socket.getaddrinfo", side_effect=socket.gaierror):
        with pytest.raises(BusinessError) as exc_info:
            validate_external_http_url("https://unresolvable.invalid")
        assert exc_info.value.msg_key == "http_tool_url_host_cannot_be_resolved"

    # Resolved to private IP
    private_sock = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.1", 443))]
    with patch("socket.getaddrinfo", return_value=private_sock):
        with pytest.raises(BusinessError) as exc_info:
            validate_external_http_url("https://public-site.com")
        assert exc_info.value.msg_key == "http_tool_url_host_not_allowed"

    # Resolved to public IP
    public_sock = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]
    with patch("socket.getaddrinfo", return_value=public_sock):
        assert (
            validate_external_http_url("https://public-site.com")
            == "https://public-site.com"
        )


@pytest.mark.parametrize(
    "host,port,error",
    [
        ("", None, "database_host_invalid"),
        ("   ", 5432, "database_host_invalid"),
        ("localhost", 5432, "database_host_not_allowed"),
        ("localhost.", 5432, "database_host_not_allowed"),
        ("local", 3306, "database_host_not_allowed"),
        ("metadata.google.internal", 80, "database_host_not_allowed"),
        ("127.0.0.1", 6379, "database_host_not_allowed"),
        ("10.0.0.1", 27017, "database_host_not_allowed"),
        ("192.168.1.100", 5432, "database_host_not_allowed"),
        ("172.16.0.1", 3306, "database_host_not_allowed"),
        ("169.254.169.254", 80, "database_host_not_allowed"),
        ("::1", 6379, "database_host_not_allowed"),
        ("fe80::1", 5432, "database_host_not_allowed"),
    ],
)
def test_validate_external_host_rejections(host, port, error):
    with pytest.raises(BusinessError) as exc_info:
        validate_external_host(host, port)
    assert exc_info.value.msg_key == error


def test_validate_external_host_dns_resolution():
    with patch("socket.getaddrinfo", side_effect=socket.gaierror):
        with pytest.raises(BusinessError) as exc_info:
            validate_external_host("unresolvable.database.internal", 5432)
        assert exc_info.value.msg_key == "database_host_cannot_be_resolved"

    # Resolved to private IP
    private_sock = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.1.5", 5432))]
    with patch("socket.getaddrinfo", return_value=private_sock):
        with pytest.raises(BusinessError) as exc_info:
            validate_external_host("db.corp.internal", 5432)
        assert exc_info.value.msg_key == "database_host_not_allowed"

    # Resolved to public IP
    public_sock = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 5432))]
    with patch("socket.getaddrinfo", return_value=public_sock):
        assert validate_external_host("db.public.com", 5432) == "db.public.com"


def test_validate_database_config_empty():
    with pytest.raises(BusinessError) as exc_info:
        validate_database_config({})
    assert exc_info.value.msg_key == "database_host_invalid"


def test_validate_database_config_host_and_port():
    # Blocked host
    with pytest.raises(BusinessError) as exc_info:
        validate_database_config({"host": "127.0.0.1", "port": 5432})
    assert exc_info.value.msg_key == "database_host_not_allowed"

    # Invalid port handled gracefully
    with pytest.raises(BusinessError) as exc_info:
        validate_database_config({"host": "127.0.0.1", "port": "invalid_port"})
    assert exc_info.value.msg_key == "database_host_not_allowed"

    # Public host allowed
    public_sock = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 5432))]
    with patch("socket.getaddrinfo", return_value=public_sock):
        validate_database_config({"host": "db.public.com", "port": 5432})


def test_validate_database_config_urls():
    # MongoDB multi-host URL with one private host
    with pytest.raises(BusinessError) as exc_info:
        validate_database_config(
            {"url": "mongodb://user:pass@93.184.216.34:27017,10.0.0.1:27018/db"}
        )
    assert exc_info.value.msg_key == "database_host_not_allowed"

    # Redis URL with loopback
    with pytest.raises(BusinessError) as exc_info:
        validate_database_config({"url": "redis://:secret@localhost:6379/0"})
    assert exc_info.value.msg_key == "database_host_not_allowed"

    # MongoDB srv URI
    public_sock = [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 27017))
    ]
    with patch("socket.getaddrinfo", return_value=public_sock):
        validate_database_config({"url": "mongodb+srv://cluster0.example.com/test"})

    # Empty URL targets
    with pytest.raises(BusinessError) as exc_info:
        validate_database_config({"url": "mongodb://"})
    assert exc_info.value.msg_key == "database_host_invalid"
