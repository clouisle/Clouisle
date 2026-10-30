import socket
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiohttp import web
from yarl import URL

from app.core.network_security import validate_external_http_url
from app.schemas.response import BusinessError
from app.services import kb_external_images as external_module
from app.services.kb_external_images import (
    _PinnedResolver,
    _address_records,
    _normalize_destination,
    _resolve_and_validate,
    fetch_external_image,
)


def _dns_result(ip: str, host: str = "images.example") -> list[tuple]:
    address = (ip, 443) if ":" not in ip else (ip, 443, 0, 0)
    family = socket.AF_INET if ":" not in ip else socket.AF_INET6
    return [(family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", address)]


def test_normalize_destination_rejects_credentials_and_non_http_urls():
    with pytest.raises(ValueError):
        _normalize_destination("https://user:password@images.example/a.png")
    with pytest.raises(ValueError):
        _normalize_destination("file:///etc/passwd")


@pytest.mark.anyio
async def test_private_dns_target_is_rejected_before_transport(monkeypatch):
    resolved = _dns_result("127.0.0.1")
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: resolved)
    destination = _normalize_destination("http://images.example/redirect")

    with pytest.raises(BusinessError, match="http_tool_url_host_not_allowed"):
        await _resolve_and_validate(destination, [])

    with pytest.raises(BusinessError, match="http_tool_url_host_not_allowed"):
        validate_external_http_url(
            "http://images.example/private",
            getaddrinfo=lambda *args, **kwargs: _dns_result("127.0.0.1"),
            allowlist=[],
        )


@pytest.mark.anyio
async def test_external_fetch_is_opt_in(monkeypatch):
    monkeypatch.setattr(
        "app.services.kb_external_images.SiteSetting.get_value",
        AsyncMock(return_value=False),
    )
    with pytest.raises(PermissionError, match="disabled"):
        await fetch_external_image("https://images.example/a.png")


@pytest.mark.anyio
async def test_fetch_pins_validated_dns_and_returns_mime(monkeypatch):
    from PIL import Image
    import io

    image_buffer = io.BytesIO()
    Image.new("RGB", (1, 1), color="red").save(image_buffer, format="PNG")
    png_data = image_buffer.getvalue()

    async def image_handler(_request):
        return web.Response(body=png_data, content_type="image/png")

    app = web.Application()
    app.router.add_get("/image.png", image_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]

    async def get_setting(key, default=None):
        return key == "kb_image_understanding_allow_external"

    async def get_allowlist():
        return ["images.example"]

    def dns_lookup(host, requested_port, **kwargs):
        assert host == "images.example"
        assert requested_port == port
        return [
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                ("127.0.0.1", port),
            )
        ]

    monkeypatch.setattr(
        "app.services.kb_external_images.SiteSetting.get_value", get_setting
    )
    monkeypatch.setattr(
        "app.services.kb_external_images.get_ssrf_allowed_targets", get_allowlist
    )
    monkeypatch.setattr(socket, "getaddrinfo", dns_lookup)

    try:
        content, mime = await fetch_external_image(
            f"http://images.example:{port}/image.png", max_image_bytes=len(png_data)
        )
        assert content == png_data
        assert mime == "image/png"
    finally:
        await runner.cleanup()


@pytest.mark.anyio
async def test_redirect_to_private_ip_is_rejected_before_second_request(monkeypatch):
    async def public_handler(_request):
        raise web.HTTPFound("http://127.0.0.1/private")

    app = web.Application()
    app.router.add_get("/start", public_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]

    async def get_setting(_key, _default=None):
        return True

    async def get_allowlist():
        return ["images.example"]

    def dns_lookup(host, requested_port, **kwargs):
        if host == "images.example":
            return [
                (
                    socket.AF_INET,
                    socket.SOCK_STREAM,
                    socket.IPPROTO_TCP,
                    "",
                    ("127.0.0.1", port),
                )
            ]
        return [
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                ("127.0.0.1", 80),
            )
        ]

    monkeypatch.setattr(
        "app.services.kb_external_images.SiteSetting.get_value", get_setting
    )
    monkeypatch.setattr(
        "app.services.kb_external_images.get_ssrf_allowed_targets", get_allowlist
    )
    monkeypatch.setattr(socket, "getaddrinfo", dns_lookup)

    try:
        with pytest.raises(Exception):
            await fetch_external_image(f"http://images.example:{port}/start")
    finally:
        await runner.cleanup()


@pytest.mark.anyio
async def test_image_pixel_limit_is_enforced(monkeypatch):
    from PIL import Image
    import io

    image_buffer = io.BytesIO()
    Image.new("RGB", (4, 4), color="blue").save(image_buffer, format="PNG")
    png_data = image_buffer.getvalue()

    async def image_handler(_request):
        return web.Response(body=png_data, content_type="image/png")

    app = web.Application()
    app.router.add_get("/image.png", image_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]

    async def get_setting(_key, _default=None):
        return True

    async def get_allowlist():
        return ["images.example"]

    def dns_lookup(host, requested_port, **kwargs):
        return [
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                ("127.0.0.1", port),
            )
        ]

    monkeypatch.setattr(
        "app.services.kb_external_images.SiteSetting.get_value", get_setting
    )
    monkeypatch.setattr(
        "app.services.kb_external_images.get_ssrf_allowed_targets", get_allowlist
    )
    monkeypatch.setattr(socket, "getaddrinfo", dns_lookup)

    try:
        with pytest.raises(ValueError, match="pixel limit"):
            await fetch_external_image(
                f"http://images.example:{port}/image.png", max_image_pixels=8
            )
    finally:
        await runner.cleanup()


@pytest.mark.anyio
async def test_streamed_size_limit_is_enforced(monkeypatch):
    from PIL import Image
    import io

    image_buffer = io.BytesIO()
    Image.new("RGB", (4, 4), color="blue").save(image_buffer, format="PNG")
    png_data = image_buffer.getvalue()

    async def image_handler(_request):
        return web.Response(body=png_data, content_type="image/png")

    app = web.Application()
    app.router.add_get("/image.png", image_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]

    async def get_setting(_key, _default=None):
        return True

    async def get_allowlist():
        return ["images.example"]

    def dns_lookup(host, requested_port, **kwargs):
        return [
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                ("127.0.0.1", port),
            )
        ]

    monkeypatch.setattr(
        "app.services.kb_external_images.SiteSetting.get_value", get_setting
    )
    monkeypatch.setattr(
        "app.services.kb_external_images.get_ssrf_allowed_targets", get_allowlist
    )
    monkeypatch.setattr(socket, "getaddrinfo", dns_lookup)

    try:
        with pytest.raises(ValueError, match="size limit"):
            await fetch_external_image(
                f"http://images.example:{port}/image.png", max_image_bytes=8
            )
    finally:
        await runner.cleanup()


def test_address_records_skip_unsupported_socket_records():
    resolved = [
        (socket.AF_UNIX, socket.SOCK_STREAM, 0, "", "/tmp/socket"),
        (socket.AF_INET, socket.SOCK_DGRAM, 0, "", ("127.0.0.1", 80)),
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 80)),
    ]
    assert _address_records("images.example", 80, resolved) == [
        {
            "hostname": "images.example",
            "host": "127.0.0.1",
            "port": 80,
            "family": socket.AF_INET,
            "proto": 6,
            "flags": 0,
        }
    ]


@pytest.mark.anyio
async def test_pinned_resolver_rejects_other_hosts_and_filters_family():
    record = {
        "hostname": "images.example",
        "host": "127.0.0.1",
        "port": 80,
        "family": socket.AF_INET,
        "proto": 6,
        "flags": 0,
    }
    resolver = _PinnedResolver("images.example.", 80, [record])
    with pytest.raises(OSError, match="different destination"):
        await resolver.resolve("other.example", 80)
    with pytest.raises(OSError, match="different destination"):
        await resolver.resolve("images.example", 81)
    assert await resolver.resolve("images.example", 80) == [record]
    with pytest.raises(OSError, match="No validated address"):
        await resolver.resolve("images.example", 80, socket.AF_INET6)
    await resolver.close()


@pytest.mark.anyio
async def test_resolve_and_validate_rejects_missing_host_empty_dns_and_empty_records(
    monkeypatch,
):
    with pytest.raises(ValueError, match="no hostname"):
        await _resolve_and_validate(SimpleNamespace(raw_host="", port=80), [])

    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [])
    with pytest.raises(BusinessError, match="cannot_be_resolved"):
        await _resolve_and_validate(URL("http://images.example/a.png"), [])

    resolved = [(socket.AF_UNIX, socket.SOCK_STREAM, 0, "", ("127.0.0.1", 80))]
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: resolved)
    monkeypatch.setattr(
        external_module, "validate_external_http_url", lambda *a, **k: None
    )
    with pytest.raises(BusinessError, match="cannot_be_resolved"):
        await _resolve_and_validate(URL("http://images.example/a.png"), [])


@pytest.mark.anyio
async def test_fetch_rejects_bad_limits_and_missing_ssrf_policy(monkeypatch):
    with pytest.raises(ValueError, match="byte limit"):
        await fetch_external_image("https://images.example/a.png", max_image_bytes=0)
    with pytest.raises(ValueError, match="pixel limit"):
        await fetch_external_image("https://images.example/a.png", max_image_pixels=0)

    monkeypatch.setattr(
        "app.services.kb_external_images.SiteSetting.get_value",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        "app.services.kb_external_images.get_ssrf_allowed_targets",
        AsyncMock(return_value=None),
    )
    with pytest.raises(PermissionError, match="requires SSRF"):
        await fetch_external_image("https://images.example/a.png")


class _FakeContent:
    def __init__(self, chunks):
        self._chunks = chunks

    async def iter_chunked(self, _size):
        for chunk in self._chunks:
            yield chunk


class _FakeResponse:
    def __init__(self, *, status=200, headers=None, chunks=()):
        self.status = status
        self.headers = headers or {}
        self.content = _FakeContent(list(chunks))

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False

    def raise_for_status(self):
        pass


class _FakeSession:
    responses = []

    def __init__(self, **_kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False

    def get(self, _url, **_kwargs):
        return _FakeSession.responses.pop(0)


def _patch_fetch(monkeypatch, responses):
    import io

    from PIL import Image

    monkeypatch.setattr(
        "app.services.kb_external_images.SiteSetting.get_value",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        "app.services.kb_external_images.get_ssrf_allowed_targets",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        external_module,
        "_resolve_and_validate",
        AsyncMock(return_value=("images.example", 80, [])),
    )
    monkeypatch.setattr(external_module.aiohttp, "ClientSession", _FakeSession)
    _FakeSession.responses = responses
    buffer = io.BytesIO()
    Image.new("RGB", (1, 1), "red").save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.mark.anyio
async def test_fetch_rejects_redirect_without_location(monkeypatch):
    _patch_fetch(monkeypatch, [_FakeResponse(status=302)])
    with pytest.raises(ValueError, match="no destination"):
        await fetch_external_image("https://images.example/a.png")


@pytest.mark.anyio
async def test_fetch_rejects_redirect_loop(monkeypatch):
    responses = [
        _FakeResponse(status=302, headers={"Location": "https://images.example/a.png"})
        for _ in range(6)
    ]
    _patch_fetch(monkeypatch, responses)
    with pytest.raises(ValueError, match="redirect limit"):
        await fetch_external_image("https://images.example/a.png")


@pytest.mark.anyio
async def test_fetch_rejects_bad_content_length_and_mime(monkeypatch):
    png = _patch_fetch(
        monkeypatch,
        [_FakeResponse(headers={"Content-Type": "image/png", "Content-Length": "abc"})],
    )
    with pytest.raises(ValueError, match="content length"):
        await fetch_external_image("https://images.example/a.png")

    _patch_fetch(
        monkeypatch,
        [_FakeResponse(headers={"Content-Type": "text/plain"}, chunks=[png])],
    )
    with pytest.raises(ValueError, match="supported image type"):
        await fetch_external_image("https://images.example/a.png")

    _patch_fetch(
        monkeypatch,
        [
            _FakeResponse(
                headers={"Content-Type": "image/gif", "Content-Length": str(len(png))},
                chunks=[png],
            )
        ],
    )
    with pytest.raises(ValueError, match="does not match"):
        await fetch_external_image("https://images.example/a.png")


@pytest.mark.anyio
async def test_fetch_streams_without_content_length_and_enforces_limit(monkeypatch):
    _patch_fetch(
        monkeypatch,
        [
            _FakeResponse(
                headers={"Content-Type": "image/png"}, chunks=[b"x" * 4, b"y" * 4]
            )
        ],
    )
    with pytest.raises(ValueError, match="size limit"):
        await fetch_external_image("https://images.example/a.png", max_image_bytes=4)
