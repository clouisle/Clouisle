import socket
from unittest.mock import AsyncMock

import pytest
from aiohttp import web

from app.core.network_security import validate_external_http_url
from app.schemas.response import BusinessError
from app.services.kb_external_images import (
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
