import asyncio
from unittest.mock import AsyncMock, call

import pytest

from app.core.sandbox_network_policy import (
    DEFAULT_SANDBOX_NETWORK_ALLOWLIST,
    SANDBOX_NETWORK_ALLOWLIST_ENABLED_SETTING,
    SANDBOX_NETWORK_ALLOWLIST_SETTING,
    SandboxNetworkPolicyError,
    get_sandbox_network_allowlist,
    normalize_sandbox_network_allowlist,
    normalize_sandbox_package_source,
    sandbox_network_host_is_allowed,
)
from app.models.site_setting import SiteSetting
from app.services.sandbox.egress_proxy import SandboxEgressProxy


def _patch_site_settings(monkeypatch, *, enabled, allowlist):
    """Fake SiteSetting.get_value with the given switch value and allowlist."""

    async def read_value(key: str, default: object) -> object:
        if key == SANDBOX_NETWORK_ALLOWLIST_ENABLED_SETTING:
            return enabled
        assert key == SANDBOX_NETWORK_ALLOWLIST_SETTING
        return allowlist

    get_value = AsyncMock(side_effect=read_value)
    monkeypatch.setattr(SiteSetting, "get_value", get_value)
    return get_value


def test_network_allowlist_normalizes_exact_dns_hosts_and_rejects_invalid_entries():
    assert normalize_sandbox_network_allowlist([" PyPI.org. ", "pypi.org"]) == [
        "pypi.org"
    ]
    assert sandbox_network_host_is_allowed(
        "pypi.org", DEFAULT_SANDBOX_NETWORK_ALLOWLIST
    )
    assert not sandbox_network_host_is_allowed(
        "attacker.pypi.org", DEFAULT_SANDBOX_NETWORK_ALLOWLIST
    )
    assert not sandbox_network_host_is_allowed(
        "127.0.0.1", DEFAULT_SANDBOX_NETWORK_ALLOWLIST
    )

    with pytest.raises(SandboxNetworkPolicyError):
        normalize_sandbox_network_allowlist(["*.example.com"])
    with pytest.raises(SandboxNetworkPolicyError):
        normalize_sandbox_network_allowlist("pypi.org")
    with pytest.raises(SandboxNetworkPolicyError):
        normalize_sandbox_network_allowlist(
            [f"host-{index}.example" for index in range(201)]
        )


@pytest.mark.asyncio
async def test_sandbox_allowlist_is_reloaded_from_site_settings_for_each_job(
    monkeypatch,
):
    pending = [[" PyPI.org. "], ["registry.npmjs.org"]]

    async def read_value(key: str, default: object) -> object:
        if key == SANDBOX_NETWORK_ALLOWLIST_ENABLED_SETTING:
            return True
        assert key == SANDBOX_NETWORK_ALLOWLIST_SETTING
        return pending.pop(0)

    get_value = AsyncMock(side_effect=read_value)
    monkeypatch.setattr(SiteSetting, "get_value", get_value)

    assert await get_sandbox_network_allowlist() == ["pypi.org"]
    assert await get_sandbox_network_allowlist() == ["registry.npmjs.org"]
    assert [call.args[0] for call in get_value.await_args_list] == [
        SANDBOX_NETWORK_ALLOWLIST_ENABLED_SETTING,
        SANDBOX_NETWORK_ALLOWLIST_SETTING,
        SANDBOX_NETWORK_ALLOWLIST_ENABLED_SETTING,
        SANDBOX_NETWORK_ALLOWLIST_SETTING,
    ]


def test_package_source_requires_https_and_an_allowlisted_host():
    assert (
        normalize_sandbox_package_source(
            "https://PYPI.org/simple/", DEFAULT_SANDBOX_NETWORK_ALLOWLIST
        )
        == "https://pypi.org/simple"
    )

    for url in (
        "http://pypi.org/simple",
        "https://user:pass@pypi.org/simple",
        "https://pypi.org:8443/simple",
        "https://attacker.example/simple",
    ):
        with pytest.raises(SandboxNetworkPolicyError):
            normalize_sandbox_package_source(url, DEFAULT_SANDBOX_NETWORK_ALLOWLIST)


@pytest.mark.asyncio
async def test_proxy_blocks_unlisted_host_and_reports_diagnostic():
    proxy = SandboxEgressProxy(job_id="job-1", allowed_hosts=["pypi.org"])

    async with proxy:
        reader, writer = await asyncio.open_unix_connection(str(proxy.socket_path))
        writer.write(
            b"CONNECT attacker.example:443 HTTP/1.1\r\n"
            b"Host: attacker.example:443\r\n\r\n"
        )
        await writer.drain()
        response = await reader.read()
        writer.close()
        await writer.wait_closed()

        assert response.startswith(b"HTTP/1.1 403 Forbidden\r\n")
        assert b"host=attacker.example" in response
        assert proxy.blocked_diagnostics == [
            "[sandbox-network] blocked host=attacker.example port=443 reason=not_allowlisted"
        ]


@pytest.mark.asyncio
@pytest.mark.parametrize("authority", ["[::1", "pypi.org:not-a-port"])
async def test_proxy_denies_malformed_connect_authorities(authority: str):
    proxy = SandboxEgressProxy(job_id="job-malformed", allowed_hosts=["pypi.org"])

    async with proxy:
        reader, writer = await asyncio.open_unix_connection(str(proxy.socket_path))
        writer.write(f"CONNECT {authority} HTTP/1.1\r\n\r\n".encode())
        await writer.drain()
        response = await reader.read()
        writer.close()
        await writer.wait_closed()

        assert response.startswith(b"HTTP/1.1 403 Forbidden\r\n")
        assert proxy.blocked_diagnostics == [
            "[sandbox-network] blocked host=unknown port=0 reason=invalid_destination"
        ]


@pytest.mark.asyncio
async def test_proxy_connects_allowlisted_host_only_via_configured_upstream(
    monkeypatch,
):
    async def echo(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        payload = await reader.read(4)
        writer.write(payload)
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    upstream = await asyncio.start_server(echo, "127.0.0.1", 0)
    upstream_port = upstream.sockets[0].getsockname()[1]
    proxy = SandboxEgressProxy(job_id="job-2", allowed_hosts=["pypi.org"])

    async def connect_public(host: str, port: int):
        assert host == "pypi.org"
        assert port == 443
        return await asyncio.open_connection("127.0.0.1", upstream_port)

    monkeypatch.setattr(proxy, "_connect_public", connect_public)
    try:
        async with proxy:
            reader, writer = await asyncio.open_unix_connection(str(proxy.socket_path))
            writer.write(b"CONNECT pypi.org:443 HTTP/1.1\r\nHost: pypi.org:443\r\n\r\n")
            await writer.drain()
            response = await reader.readuntil(b"\r\n\r\n")
            assert response.startswith(b"HTTP/1.1 200 Connection Established")

            writer.write(b"ping")
            await writer.drain()
            assert await reader.readexactly(4) == b"ping"
            writer.close()
            await writer.wait_closed()
    finally:
        upstream.close()
        await upstream.wait_closed()


@pytest.mark.asyncio
async def test_missing_site_setting_uses_seeded_default(monkeypatch):
    async def read_default(key: str, default: object) -> object:
        assert key in {
            SANDBOX_NETWORK_ALLOWLIST_ENABLED_SETTING,
            SANDBOX_NETWORK_ALLOWLIST_SETTING,
        }
        return default

    get_value = AsyncMock(side_effect=read_default)
    monkeypatch.setattr(SiteSetting, "get_value", get_value)

    assert await get_sandbox_network_allowlist() == DEFAULT_SANDBOX_NETWORK_ALLOWLIST
    assert get_value.await_args_list == [
        call(SANDBOX_NETWORK_ALLOWLIST_ENABLED_SETTING, True),
        call(
            SANDBOX_NETWORK_ALLOWLIST_SETTING,
            DEFAULT_SANDBOX_NETWORK_ALLOWLIST,
        ),
    ]


@pytest.mark.asyncio
async def test_disabled_switch_is_unrestricted_and_reenabling_restores_restrictions(
    monkeypatch,
):
    state = {"enabled": False, "allowlist": ["pypi.org"]}

    async def read_value(key: str, default: object) -> object:
        if key == SANDBOX_NETWORK_ALLOWLIST_ENABLED_SETTING:
            return state["enabled"]
        assert key == SANDBOX_NETWORK_ALLOWLIST_SETTING
        return state["allowlist"]

    get_value = AsyncMock(side_effect=read_value)
    monkeypatch.setattr(SiteSetting, "get_value", get_value)

    assert await get_sandbox_network_allowlist() is None
    # A disabled restriction does not even read (or discard) the allowlist.
    assert get_value.await_args_list == [
        call(SANDBOX_NETWORK_ALLOWLIST_ENABLED_SETTING, True)
    ]

    state["enabled"] = True
    assert await get_sandbox_network_allowlist() == ["pypi.org"]

    state["enabled"] = False
    assert await get_sandbox_network_allowlist() is None
    state["enabled"] = True
    assert await get_sandbox_network_allowlist() == ["pypi.org"]


@pytest.mark.asyncio
@pytest.mark.parametrize("enabled", [None, "false", "False", 0, 1, "true", {}, []])
async def test_non_literal_false_switch_values_keep_restrictions(
    monkeypatch, enabled: object
):
    _patch_site_settings(monkeypatch, enabled=enabled, allowlist=["pypi.org"])

    assert await get_sandbox_network_allowlist() == ["pypi.org"]


@pytest.mark.asyncio
async def test_allowlist_read_failure_blocks_all_egress_while_enabled(monkeypatch):
    async def read_value(key: str, default: object) -> object:
        if key == SANDBOX_NETWORK_ALLOWLIST_ENABLED_SETTING:
            return True
        raise RuntimeError("database unavailable")

    get_value = AsyncMock(side_effect=read_value)
    monkeypatch.setattr(SiteSetting, "get_value", get_value)

    assert await get_sandbox_network_allowlist() == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "allowlist", [None, "pypi.org", ["*.example.com"], ["pypi.org", None]]
)
async def test_malformed_allowlist_fails_closed(monkeypatch, allowlist: object):
    _patch_site_settings(monkeypatch, enabled=True, allowlist=allowlist)

    assert await get_sandbox_network_allowlist() == []


@pytest.mark.asyncio
async def test_site_setting_read_failure_blocks_all_sandbox_egress(monkeypatch):
    get_value = AsyncMock(side_effect=RuntimeError("database unavailable"))
    monkeypatch.setattr(SiteSetting, "get_value", get_value)

    assert await get_sandbox_network_allowlist() == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("wire_request", "reason"),
    [
        (b"broken\r\n\r\n", "invalid_request"),
        (b"GET http://pypi.org/simple HTTP/1.1\r\n\r\n", "https_required"),
        (b"CONNECT pypi.org:80 HTTP/1.1\r\n\r\n", "port_not_allowed"),
        (b"CONNECT 127.0.0.1:443 HTTP/1.1\r\n\r\n", "invalid_host"),
        (b"CONNECT pypi.org:443/path HTTP/1.1\r\n\r\n", "invalid_destination"),
    ],
)
async def test_proxy_rejects_unsafe_requests_before_opening_upstream(
    monkeypatch, wire_request, reason
):
    proxy = SandboxEgressProxy(job_id="unsafe-request", allowed_hosts=["pypi.org"])
    upstream = AsyncMock(
        side_effect=AssertionError("unsafe destination reached upstream")
    )
    monkeypatch.setattr(proxy, "_connect_public", upstream)
    async with proxy:
        reader, writer = await asyncio.open_unix_connection(str(proxy.socket_path))
        try:
            writer.write(wire_request)
            await writer.drain()
            response = await asyncio.wait_for(reader.read(), 2)
            assert response.startswith(b"HTTP/1.1 403 Forbidden")
            assert reason.encode() in response
            assert any(
                f"reason={reason}" in entry for entry in proxy.blocked_diagnostics
            )
            upstream.assert_not_awaited()
        finally:
            writer.close()
            await writer.wait_closed()


@pytest.mark.asyncio
async def test_proxy_returns_bad_gateway_when_allowed_upstream_is_unreachable(
    monkeypatch,
):
    proxy = SandboxEgressProxy(job_id="unreachable", allowed_hosts=["pypi.org"])
    monkeypatch.setattr(
        proxy, "_connect_public", AsyncMock(side_effect=OSError("unreachable"))
    )
    async with proxy:
        reader, writer = await asyncio.open_unix_connection(str(proxy.socket_path))
        try:
            writer.write(b"CONNECT pypi.org:443 HTTP/1.1\r\n\r\n")
            await writer.drain()
            response = await asyncio.wait_for(reader.read(), 2)
            assert response.startswith(b"HTTP/1.1 502 Bad Gateway")
            assert b"host pypi.org" in response
            assert proxy.blocked_diagnostics == []
        finally:
            writer.close()
            await writer.wait_closed()


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        " ",
        "https://pypi.org:invalid/simple",
        "https://pypi.org/simple?token=secret",
        "https://pypi.org/simple#fragment",
    ],
)
def test_package_sources_reject_ambiguous_or_secret_bearing_urls(value):
    with pytest.raises(SandboxNetworkPolicyError):
        normalize_sandbox_package_source(value, DEFAULT_SANDBOX_NETWORK_ALLOWLIST)


def test_unrestricted_package_sources_accept_http_and_custom_hosts_and_ports():
    assert (
        normalize_sandbox_package_source("https://unlisted.example/simple/", None)
        == "https://unlisted.example/simple"
    )
    assert (
        normalize_sandbox_package_source("http://localhost:8080/simple/", None)
        == "http://localhost:8080/simple"
    )
    assert (
        normalize_sandbox_package_source("https://10.0.0.5:8443/simple", None)
        == "https://10.0.0.5:8443/simple"
    )
    assert (
        normalize_sandbox_package_source("https://[::1]:8443/simple", None)
        == "https://[::1]:8443/simple"
    )

    for url in (
        "ftp://unlisted.example/simple",
        "https://user:pass@unlisted.example/simple",
        "https://unlisted.example/simple?token=secret",
        "https://unlisted.example/simple#fragment",
        "https://unlisted.example:invalid/simple",
        "https://unlisted.example:0/simple",
        "",
    ):
        with pytest.raises(SandboxNetworkPolicyError):
            normalize_sandbox_package_source(url, None)


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "white space.example",
        "\ud800.example",
        "-bad.example",
        "localhost",
        "x" * 64 + ".example",
    ],
)
def test_invalid_network_hosts_fail_closed(value):
    assert (
        sandbox_network_host_is_allowed(value, DEFAULT_SANDBOX_NETWORK_ALLOWLIST)
        is False
    )


def test_nonstring_allowlist_entry_fails_closed():
    with pytest.raises(SandboxNetworkPolicyError):
        normalize_sandbox_network_allowlist(["pypi.org", None])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "address", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "::1", "fc00::1"]
)
async def test_allowlisted_host_cannot_resolve_to_private_network(monkeypatch, address):
    import socket

    proxy = SandboxEgressProxy(job_id="dns-rebinding", allowed_hosts=["pypi.org"])
    loop = asyncio.get_running_loop()
    family = socket.AF_INET6 if ":" in address else socket.AF_INET
    endpoint = (address, 443, 0, 0) if family == socket.AF_INET6 else (address, 443)
    monkeypatch.setattr(
        loop,
        "getaddrinfo",
        AsyncMock(return_value=[(family, socket.SOCK_STREAM, 6, "", endpoint)]),
    )
    connect = AsyncMock(side_effect=AssertionError("private endpoint was contacted"))
    monkeypatch.setattr(loop, "sock_connect", connect)
    with pytest.raises(ValueError, match="No public address"):
        await proxy._connect_public("pypi.org", 443)
    connect.assert_not_awaited()
