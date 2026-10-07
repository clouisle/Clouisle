import asyncio
from unittest.mock import AsyncMock

import pytest

from app.core.sandbox_network_policy import (
    DEFAULT_SANDBOX_NETWORK_ALLOWLIST,
    SANDBOX_NETWORK_ALLOWLIST_SETTING,
    SandboxNetworkPolicyError,
    get_sandbox_network_allowlist,
    normalize_sandbox_network_allowlist,
    normalize_sandbox_package_source,
    sandbox_network_host_is_allowed,
)
from app.models.site_setting import SiteSetting
from app.services.sandbox.egress_proxy import SandboxEgressProxy


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
    get_value = AsyncMock(side_effect=[[" PyPI.org. "], ["registry.npmjs.org"]])
    monkeypatch.setattr(SiteSetting, "get_value", get_value)

    assert await get_sandbox_network_allowlist() == ["pypi.org"]
    assert await get_sandbox_network_allowlist() == ["registry.npmjs.org"]
    assert get_value.await_count == 2
    assert all(
        call.args[0] == SANDBOX_NETWORK_ALLOWLIST_SETTING
        for call in get_value.await_args_list
    )


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
        assert key == SANDBOX_NETWORK_ALLOWLIST_SETTING
        return default

    get_value = AsyncMock(side_effect=read_default)
    monkeypatch.setattr(SiteSetting, "get_value", get_value)

    assert await get_sandbox_network_allowlist() == DEFAULT_SANDBOX_NETWORK_ALLOWLIST
    get_value.assert_awaited_once_with(
        SANDBOX_NETWORK_ALLOWLIST_SETTING,
        DEFAULT_SANDBOX_NETWORK_ALLOWLIST,
    )


@pytest.mark.asyncio
async def test_site_setting_read_failure_blocks_all_sandbox_egress(monkeypatch):
    get_value = AsyncMock(side_effect=RuntimeError("database unavailable"))
    monkeypatch.setattr(SiteSetting, "get_value", get_value)

    assert await get_sandbox_network_allowlist() == []
