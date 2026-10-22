"""ClawBot iLink transport behavior: URL policy, request/response mapping, media crypto.

The HTTP boundary is an ``httpx.MockTransport`` and outbound SSRF validation is
disabled explicitly, so every assertion is about this client's own decisions.
"""

import base64
import json
import logging

import httpx
import pytest
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from app.integrations import wechat


def make_client(
    handler, *, token="tok", base_url=wechat.API_BASE
) -> wechat.WeChatClient:
    client = wechat.WeChatClient(base_url, token)
    client.http = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), follow_redirects=False
    )
    return client


@pytest.fixture(autouse=True)
def _no_ssrf_lookup(monkeypatch):
    # The client must still call the validator; the network lookup is not what
    # these tests exercise.
    calls: list[str] = []
    monkeypatch.setattr(
        wechat, "validate_external_http_url", lambda url: calls.append(url)
    )
    return calls


def json_response(payload, status=200, headers=None) -> httpx.Response:
    return httpx.Response(
        status, content=json.dumps(payload).encode(), headers=headers or {}
    )


def recorded_json(request: httpx.Request):
    return json.loads(request.content.decode())


@pytest.mark.parametrize(
    "value",
    [
        "http://ilinkai.weixin.qq.com",
        "https://evil.example.com",
        "https://user:pw@ilinkai.weixin.qq.com",
        "https://ilinkai.weixin.qq.com:8443",
        "https://ilinkai.weixin.qq.com/#frag",
        "https://ilinkai.weixin.qq.com/path",
        "https://ilinkai.weixin.qq.com/?a=1",
    ],
)
def test_official_url_rejects_non_bot_endpoints(value):
    with pytest.raises(wechat.WeChatAPIError) as error:
        wechat.official_url(value)
    assert error.value.code == "invalid_host"


def test_official_url_normalizes_bot_base_and_allows_media_query():
    assert wechat.official_url("https://ilinkai.weixin.qq.com/") == wechat.API_BASE
    media = "https://novac2c.cdn.weixin.qq.com/c2c/download?encrypted_query_param=abc"
    assert wechat.official_url(media, media=True) == media

    with pytest.raises(wechat.WeChatAPIError):
        wechat.official_url(
            "https://novac2c.cdn.weixin.qq.com.evil.example/c2c", media=True
        )


def test_transport_filter_redacts_only_parsed_wechat_hosts():
    filt = wechat._RedactWeChatTransport()

    for message in (
        "HTTP Request: GET https://ilinkai.weixin.qq.com/ilink/bot/getupdates?cursor=secret",
        "HTTP Request: GET https://novac2c.cdn.weixin.qq.com/c2c/download?x=1",
    ):
        record = logging.LogRecord(
            "httpx", logging.INFO, __file__, 1, message, (), None
        )
        assert filt.filter(record) is True
        assert record.getMessage() == "WeChat transport request (URL redacted)"

    # A look-alike host must not be treated as WeChat: the previous substring
    # test would have redacted it (and CodeQL flagged the reverse case).
    for message in (
        "HTTP Request: GET https://weixin.qq.com.evil.example/c2c",
        "HTTP Request: GET https://api.example.com",
    ):
        record = logging.LogRecord(
            "httpx", logging.INFO, __file__, 1, message, (), None
        )
        assert filt.filter(record) is True
        assert record.getMessage() == message


def test_transport_filter_redacts_wechat_request_urls():
    filt = wechat._RedactWeChatTransport()
    record = logging.LogRecord(
        "httpx",
        logging.INFO,
        __file__,
        1,
        'HTTP Request: GET https://ilinkai.weixin.qq.com/ilink/bot/getupdates?cursor=secret "HTTP/1.1 200 OK"',
        (),
        None,
    )
    assert filt.filter(record) is True
    assert record.getMessage() == "WeChat transport request (URL redacted)"

    unrelated = logging.LogRecord(
        "httpx",
        logging.INFO,
        __file__,
        1,
        "HTTP Request: GET https://api.example.com",
        (),
        None,
    )
    assert filt.filter(unrelated) is True
    assert unrelated.getMessage() == "HTTP Request: GET https://api.example.com"


@pytest.mark.asyncio
async def test_request_authenticates_only_when_a_token_body_is_sent(_no_ssrf_lookup):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return json_response({"ret": 0, "value": "ok"})

    client = make_client(handler)
    assert await client.get_qrcode() == {"ret": 0, "value": "ok"}
    await client.send_text("user-1", "hello", "ctx", client_id="cid")

    anonymous, authenticated = seen[0], seen[1]
    assert anonymous.headers["ilink-app-id"] == "bot"
    # An unauthenticated body still carries the bot client headers, but never a
    # bearer token and never the authorization base_info block.
    assert "authorization" not in anonymous.headers
    assert anonymous.headers["authorizationtype"] == "ilink_bot_token"
    assert base64.b64decode(anonymous.headers["x-wechat-uin"]).decode().isdigit()
    assert "base_info" not in recorded_json(anonymous)

    assert authenticated.headers["authorization"] == "Bearer tok"
    assert authenticated.headers["authorizationtype"] == "ilink_bot_token"
    assert base64.b64decode(authenticated.headers["x-wechat-uin"]).decode().isdigit()
    body = recorded_json(authenticated)
    assert body["base_info"] == wechat.BASE_INFO
    assert body["msg"]["client_id"] == "cid"
    assert body["msg"]["item_list"][0]["text_item"]["text"] == "hello"
    assert _no_ssrf_lookup == [
        f"{wechat.API_BASE}/ilink/bot/get_bot_qrcode?bot_type=3",
        f"{wechat.API_BASE}/ilink/bot/sendmessage",
    ]
    await client.http.aclose()


@pytest.mark.asyncio
async def test_request_maps_api_codes_and_transport_failures():
    async def call_with(handler):
        client = make_client(handler)
        try:
            return await client._request("ilink/bot/getupdates", {})
        finally:
            await client.http.aclose()

    with pytest.raises(wechat.WeChatAPIError) as ret_error:
        await call_with(lambda request: json_response({"ret": 40001}))
    assert ret_error.value.code == 40001

    with pytest.raises(wechat.WeChatAPIError) as errcode_error:
        await call_with(lambda request: json_response({"errcode": "invalid"}))
    assert errcode_error.value.code == "invalid"

    with pytest.raises(wechat.WeChatAPIError) as shape_error:
        await call_with(lambda request: json_response([1, 2, 3]))
    assert shape_error.value.code == "response"

    with pytest.raises(wechat.WeChatAPIError) as size_error:
        await call_with(
            lambda request: httpx.Response(200, content=b"x" * (4 * 1024 * 1024 + 1))
        )
    assert size_error.value.code == "response_size"

    with pytest.raises(wechat.WeChatAPIError) as status_error:
        await call_with(lambda request: httpx.Response(500, content=b"{}"))
    assert status_error.value.code == "connection"
    assert isinstance(status_error.value.__cause__, httpx.HTTPError)

    with pytest.raises(wechat.WeChatAPIError) as json_error:
        await call_with(lambda request: httpx.Response(200, content=b"not json"))
    assert json_error.value.code == "connection"


@pytest.mark.asyncio
async def test_qrcode_status_waits_on_verification_code_timeout(monkeypatch):
    client = make_client(lambda request: json_response({"status": "confirmed"}))
    assert await client.get_qrcode_status("qr-1", "1234") == {"status": "confirmed"}
    assert client.http is not None

    calls: list[str] = []

    async def timeout(endpoint, body=None, **kwargs):
        calls.append(endpoint)
        raise TimeoutError

    monkeypatch.setattr(client, "_request", timeout)
    assert await client.get_qrcode_status("qr-1") == {"status": "wait"}
    assert calls == ["ilink/bot/get_qrcode_status?qrcode=qr-1"]
    await client.http.aclose()


@pytest.mark.asyncio
async def test_get_updates_bounds_the_poll_and_tolerates_read_timeouts(monkeypatch):
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(recorded_json(request))
        return json_response({"msgs": [{"message_id": "1"}], "get_updates_buf": "next"})

    client = make_client(handler)
    assert await client.get_updates("cursor-0", wait_seconds=5) == {
        "msgs": [{"message_id": "1"}],
        "get_updates_buf": "next",
    }
    assert seen[0] == {"get_updates_buf": "cursor-0", "base_info": wechat.BASE_INFO}

    async def slow(endpoint, body=None, **kwargs):
        raise TimeoutError

    monkeypatch.setattr(client, "_request", slow)
    # A bounded poll reports "nothing new" instead of failing the scheduled task.
    assert await client.get_updates("cursor-1", wait_seconds=0.01) == {
        "msgs": [],
        "get_updates_buf": "cursor-1",
    }

    async def read_timeout(endpoint, body=None, **kwargs):
        error = wechat.WeChatAPIError()
        error.__cause__ = httpx.ReadTimeout("slow")
        raise error

    monkeypatch.setattr(client, "_request", read_timeout)
    assert await client.get_updates("cursor-2") == {
        "msgs": [],
        "get_updates_buf": "cursor-2",
    }

    async def hard_failure(endpoint, body=None, **kwargs):
        raise wechat.WeChatAPIError(41001)

    monkeypatch.setattr(client, "_request", hard_failure)
    with pytest.raises(wechat.WeChatAPIError) as error:
        await client.get_updates("cursor-3")
    assert error.value.code == 41001
    await client.http.aclose()


@pytest.mark.asyncio
async def test_send_text_and_media_require_a_context_token():
    client = make_client(lambda request: json_response({"ret": 0}))
    with pytest.raises(wechat.WeChatAPIError) as text_error:
        await client.send_text("user-1", "hi", "")
    assert text_error.value.code == "missing_context"

    with pytest.raises(wechat.WeChatAPIError) as media_error:
        await client.send_media("user-1", "", item={"type": 1})
    assert media_error.value.code == "missing_context"

    sent = make_client(
        lambda request: (
            seen.append(recorded_json(request)),
            json_response({"ret": 0}),
        )[1]
    )
    seen: list[dict] = []
    await sent.send_media("user-1", "ctx", item={"type": 3, "file_item": {}})
    message = seen[0]["msg"]
    assert message["item_list"] == [{"type": 3, "file_item": {}}]
    assert message["message_type"] == 2
    assert message["client_id"]
    await sent.http.aclose()
    await client.http.aclose()


@pytest.mark.asyncio
async def test_upload_slot_requires_a_reserved_url_or_param():
    async def call(payload):
        client = make_client(lambda request: json_response(payload))
        try:
            return await client.get_upload_url(
                filekey="fk",
                media_type=3,
                to_user_id="user",
                raw_size=1,
                raw_file_md5="md5",
                file_size=16,
                aeskey="00" * 16,
            )
        finally:
            await client.http.aclose()

    assert await call({"upload_full_url": " https://novac2c.cdn.weixin.qq.com/x "}) == (
        "https://novac2c.cdn.weixin.qq.com/x",
        "",
    )
    url, param = await call({"upload_param": "reserved"})
    assert url == (
        f"{wechat.CDN_BASE}/upload?encrypted_query_param=reserved&filekey=fk"
    )
    assert param == "reserved"

    with pytest.raises(wechat.WeChatAPIError) as missing:
        await call({})
    assert missing.value.code == "upload_url"


@pytest.mark.asyncio
async def test_upload_media_returns_the_download_parameter():
    async def upload(response):
        client = make_client(lambda request: response)
        try:
            return await client.upload_media(f"{wechat.CDN_BASE}/upload?x=1", b"cipher")
        finally:
            await client.http.aclose()

    assert (
        await upload(
            httpx.Response(200, headers={"x-encrypted-param": "download-param"})
        )
        == "download-param"
    )

    with pytest.raises(wechat.WeChatAPIError) as no_param:
        await upload(httpx.Response(200))
    assert no_param.value.code == "upload_param"

    with pytest.raises(wechat.WeChatAPIError) as http_failure:
        await upload(httpx.Response(500))
    assert http_failure.value.code == "media_upload"

    client = make_client(lambda request: json_response({}))
    with pytest.raises(wechat.WeChatAPIError) as rejected_host:
        await client.upload_media("https://evil.example.com/upload", b"cipher")
    assert rejected_host.value.code == "invalid_host"
    await client.http.aclose()


def _encrypt(plaintext: bytes) -> tuple[bytes, str]:
    key = bytes(range(16))
    padder = padding.PKCS7(128).padder()
    padded = padder.update(plaintext) + padder.finalize()
    # Mirrors the iLink CDN media format (AES-128-ECB + PKCS7) under test.
    encryptor = Cipher(algorithms.AES(key), modes.ECB()).encryptor()
    return encryptor.update(padded) + encryptor.finalize(), key.hex()


@pytest.mark.asyncio
async def test_media_download_follows_one_redirect_and_decrypts_ciphertext():
    ciphertext, key_hex = _encrypt(b"hello media")
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if len(calls) == 1:
            return httpx.Response(302, headers={"location": "/c2c/download?again=1"})
        return httpx.Response(
            200, content=ciphertext, headers={"content-length": str(len(ciphertext))}
        )

    client = make_client(handler)
    item = {
        "type": 2,
        "image_item": {"media": {"encrypt_query_param": "abc"}, "aeskey": key_hex},
    }
    raw, name, mime = await client.download_media(item, 1024)
    assert raw == b"hello media"
    assert (name, mime) == ("image.jpg", "image/jpeg")
    assert calls[1].endswith("/c2c/download?again=1")
    await client.http.aclose()


@pytest.mark.asyncio
async def test_media_download_validates_items_names_sizes_and_keys():
    decryption_key = base64.b64encode(bytes(range(16))).decode()
    encrypted_body, hex_key = _encrypt(b"file body")

    def file_item(name: str, *, key: str | None = decryption_key) -> dict:
        media: dict = {"encrypt_query_param": "x"}
        if key is not None:
            media["aes_key"] = key
        return {"type": 4, "file_item": {"file_name": name, "media": media}}

    async def download(item, max_bytes=1024, handler=None):
        client = make_client(
            handler or (lambda request: httpx.Response(200, content=b"payload"))
        )
        try:
            return await client.download_media(item, max_bytes)
        finally:
            await client.http.aclose()

    with pytest.raises(wechat.WeChatAPIError) as missing_media:
        await download({"type": 4, "file_item": {}})
    assert missing_media.value.code == "missing_media"

    # A non-image item without a decryption key can never be read.
    with pytest.raises(wechat.WeChatAPIError) as missing_key:
        await download(
            {"type": 3, "voice_item": {"media": {"encrypt_query_param": "x"}}}
        )
    assert missing_key.value.code == "missing_media"

    def oversized(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"x" * 64, headers={"content-length": "64"})

    with pytest.raises(wechat.WeChatAPIError) as too_large:
        await download(file_item("note.txt"), max_bytes=8, handler=oversized)
    assert too_large.value.code == "file_too_large"

    with pytest.raises(wechat.WeChatAPIError) as empty:
        await download(
            {"type": 2, "image_item": {"media": {"encrypt_query_param": "x"}}},
            handler=lambda request: httpx.Response(200, content=b""),
        )
    assert empty.value.code == "empty_media"

    # An image without any negotiated key is returned as-is, from an absolute
    # CDN URL rather than the composed download endpoint.
    image_urls: list[str] = []

    def image_handler(request: httpx.Request) -> httpx.Response:
        image_urls.append(str(request.url))
        return httpx.Response(200, content=b"image-bytes")

    raw, name, mime = await download(
        {
            "type": 2,
            "image_item": {"media": {"full_url": f"{wechat.CDN_BASE}/direct?token=1"}},
        },
        handler=image_handler,
    )
    assert (raw, name, mime) == (b"image-bytes", "image.jpg", "image/jpeg")
    assert image_urls == [f"{wechat.CDN_BASE}/direct?token=1"]

    # An unprintable filename is rejected instead of escaping the collection.
    with pytest.raises(wechat.WeChatAPIError) as bad_name:
        await download(file_item("."))
    assert bad_name.value.code == "filename"

    # Image items carry their key in a dedicated hex field.
    image_ciphertext, image_key_hex = _encrypt(b"image body")
    raw, _, _ = await download(
        {
            "type": 2,
            "image_item": {
                "media": {"encrypt_query_param": "x"},
                "aeskey": image_key_hex,
            },
        },
        handler=lambda request: httpx.Response(200, content=image_ciphertext),
    )
    assert raw == b"image body"

    # Escaping filenames are reduced to their basename; bytes are decrypted and
    # typed by extension.
    raw, name, mime = await download(
        file_item("../../../etc/report.pdf"),
        handler=lambda request: httpx.Response(200, content=encrypted_body),
    )
    assert (raw, name, mime) == (b"file body", "report.pdf", "application/pdf")

    # A malformed base64 key is a protocol error, not a silent passthrough.
    with pytest.raises(wechat.WeChatAPIError) as bad_key:
        await download(file_item("note.txt", key="!!!"))
    assert bad_key.value.code == "media_download"

    # A 32-byte hex key (base64-encoded) is decoded to its 16 raw bytes.
    raw, _, _ = await download(
        file_item("note.txt", key=base64.b64encode(hex_key.encode()).decode()),
        handler=lambda request: httpx.Response(200, content=encrypted_body),
    )
    assert raw == b"file body"

    # A wrong-length decoded key is rejected before decryption.
    with pytest.raises(wechat.WeChatAPIError) as wrong_key:
        await download(
            file_item("note.txt", key=base64.b64encode(b"123456789").decode())
        )
    assert wrong_key.value.code == "media_key"


@pytest.mark.asyncio
async def test_client_context_manager_closes_the_transport():
    async with wechat.WeChatClient() as client:
        assert client.base_url == wechat.API_BASE
        assert client.token == ""
        assert client.http.is_closed is False

    assert client.http.is_closed is True


@pytest.mark.asyncio
async def test_client_with_borrowed_transport_does_not_close_it():
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={}))
    shared = httpx.AsyncClient(transport=transport)
    async with wechat.WeChatClient(token="account-token", http=shared) as client:
        assert client.http is shared
    assert not shared.is_closed
    await shared.aclose()


@pytest.mark.asyncio
async def test_shared_transport_never_reuses_account_auth_or_cookies():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={})

    shared = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        headers={"Authorization": "Bearer shared-default"},
        cookies={"session": "shared-cookie"},
    )
    try:
        async with wechat.WeChatClient(token="first-secret", http=shared) as first:
            await first._request("test", {})
        async with wechat.WeChatClient(token="second-secret", http=shared) as second:
            await second._request("test", {})
        assert requests[0].headers["Authorization"] == "Bearer first-secret"
        assert requests[1].headers["Authorization"] == "Bearer second-secret"
        assert requests[0].headers.get("cookie", "") == ""
        assert requests[1].headers.get("cookie", "") == ""
    finally:
        await shared.aclose()


@pytest.mark.asyncio
async def test_media_download_gives_up_after_repeated_redirects():
    client = make_client(
        lambda request: httpx.Response(302, headers={"location": "/c2c/download"})
    )
    with pytest.raises(wechat.WeChatAPIError) as redirects:
        await client.download_media(
            {
                "type": 4,
                "file_item": {
                    "file_name": "note.txt",
                    "media": {
                        "encrypt_query_param": "x",
                        "aes_key": base64.b64encode(bytes(16)).decode(),
                    },
                },
            },
            1024,
        )
    assert redirects.value.code == "redirects"
    await client.http.aclose()


@pytest.mark.asyncio
async def test_media_download_wraps_transport_failures():
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route")

    client = make_client(boom)
    with pytest.raises(wechat.WeChatAPIError) as failure:
        await client.download_media(
            {
                "type": 4,
                "file_item": {
                    "file_name": "note.txt",
                    "media": {
                        "encrypt_query_param": "x",
                        "aes_key": base64.b64encode(bytes(16)).decode(),
                    },
                },
            },
            1024,
        )
    assert failure.value.code == "media_download"
    await client.http.aclose()
