from unittest.mock import AsyncMock

import httpx
import pytest

from app.integrations import feishu_content as content
from app.integrations.credentials import encrypt_secret
from app.integrations.feishu import FeishuAPIError, FeishuClient


@pytest.fixture
def transport_client(monkeypatch):
    original = httpx.AsyncClient
    monkeypatch.setattr(content, "_pace", AsyncMock())
    monkeypatch.setattr(content.SiteSetting, "get_value", AsyncMock(return_value=1))

    def install(handler):
        requests = []

        def dispatch(request):
            requests.append(request)
            assert request.url.host == "open.feishu.cn"
            if request.url.path.endswith("/auth/v3/tenant_access_token/internal"):
                return httpx.Response(
                    200, json={"code": 0, "tenant_access_token": "tenant-secret"}
                )
            assert request.headers["authorization"] == "Bearer tenant-secret"
            return handler(request)

        monkeypatch.setattr(
            content.httpx,
            "AsyncClient",
            lambda **kwargs: original(
                transport=httpx.MockTransport(dispatch), **kwargs
            ),
        )
        return FeishuClient("app", encrypt_secret("secret")), requests

    return install


@pytest.mark.asyncio
async def test_json_returns_full_envelope_and_preserves_api_error(transport_client):
    client, requests = transport_client(
        lambda request: (
            httpx.Response(403, json={"code": 1069902, "msg": "denied"})
            if request.url.params.get("deny")
            else httpx.Response(200, json={"code": 0, "data": {"value": "ok"}})
        )
    )
    assert await content.request_json(client, "GET", "/drive/v1/example") == {
        "code": 0,
        "data": {"value": "ok"},
    }
    with pytest.raises(FeishuAPIError) as raised:
        await content.request_json(
            client, "GET", "/drive/v1/example", params={"deny": True}
        )
    assert raised.value.code == 1069902
    assert raised.value.permission_denied
    assert all(request.url.host == "open.feishu.cn" for request in requests)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path", ["https://attacker.test/file", "//attacker.test/file", "file"]
)
async def test_json_rejects_absolute_paths_without_authentication(
    transport_client, path
):
    client, requests = transport_client(lambda _: pytest.fail("unexpected API call"))
    with pytest.raises(FeishuAPIError, match="relative API path"):
        await content.request_json(client, "GET", path)
    assert requests == []


@pytest.mark.asyncio
async def test_media_encodes_token_and_passes_permission_extra(transport_client):
    extra = '{"bitablePerm":{"tableId":"table","rev":90}}'

    def handler(request):
        assert request.url.raw_path.startswith(
            b"/open-apis/drive/v1/medias/token%2Fpart/download"
        )
        assert request.url.params["extra"] == extra
        return httpx.Response(
            200, content=b"image", headers={"content-type": "image/png; charset=binary"}
        )

    client, _ = transport_client(handler)
    assert await content.download_media(client, "token/part", extra=extra) == (
        b"image",
        "image/png",
    )


@pytest.mark.asyncio
async def test_media_never_follows_credentialed_redirect(transport_client):
    client, requests = transport_client(
        lambda _: httpx.Response(
            302, headers={"location": "https://attacker.test/stolen"}
        )
    )
    with pytest.raises(FeishuAPIError) as raised:
        await content.download_media(client, "token")
    assert raised.value.status_code == 302
    assert len(requests) == 2


class Chunks(httpx.AsyncByteStream):
    def __init__(self):
        self.read_count = 0

    async def __aiter__(self):
        for _ in range(30):
            self.read_count += 1
            yield b"x" * (64 * 1024)


@pytest.mark.asyncio
async def test_streaming_download_stops_at_configured_limit(transport_client):
    chunks = Chunks()
    client, _ = transport_client(lambda _: httpx.Response(200, stream=chunks))
    with pytest.raises(FeishuAPIError, match="size limit"):
        await content.download_media(client, "token")
    assert chunks.read_count == 17


@pytest.mark.asyncio
async def test_oversized_content_length_rejected_before_reading(transport_client):
    chunks = Chunks()
    client, _ = transport_client(
        lambda _: httpx.Response(
            200, stream=chunks, headers={"content-length": str(1024 * 1024 + 1)}
        )
    )
    with pytest.raises(FeishuAPIError, match="size limit"):
        await content.download_media(client, "token")
    assert chunks.read_count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,payload",
    [
        (403, {"code": 1770032, "msg": "no access"}),
        (200, {"code": 1770032, "msg": "no access"}),
    ],
)
async def test_binary_api_errors_are_not_imported_as_content(
    transport_client, status, payload
):
    client, _ = transport_client(lambda _: httpx.Response(status, json=payload))
    with pytest.raises(FeishuAPIError) as raised:
        await content.download_media(client, "token")
    assert raised.value.code == 1770032
    assert raised.value.permission_denied


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(206, content=b"partial"),
        httpx.Response(200, content=b"short", headers={"content-length": "100"}),
        httpx.Response(200, content=b""),
        httpx.Response(200, content=b"file", headers={"content-length": "invalid"}),
    ],
)
async def test_incomplete_or_invalid_downloads_fail(transport_client, response):
    client, _ = transport_client(lambda _: response)
    with pytest.raises(FeishuAPIError):
        await content.download_media(client, "token")


@pytest.mark.asyncio
async def test_file_uses_metadata_original_name_and_mime_extension(transport_client):
    def handler(request):
        if request.url.path.endswith("/metas/batch_query"):
            assert b'"doc_type":"file"' in request.content
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {
                        "metas": [
                            {
                                "doc_token": "file",
                                "doc_type": "file",
                                "title": "../quarterly",
                            }
                        ],
                        "failed_list": [],
                    },
                },
            )
        assert request.url.path == "/open-apis/drive/v1/files/file/download"
        return httpx.Response(
            200, content=b"%PDF-1.7", headers={"content-type": "application/pdf"}
        )

    client, _ = transport_client(handler)
    result = await content.download_file(client, "file", "Wiki title")
    assert result.filename == "quarterly.pdf"
    assert result.content == b"%PDF-1.7"
    assert result.warnings == []


@pytest.mark.asyncio
async def test_file_sanitizes_rfc5987_filename(transport_client):
    client, _ = transport_client(
        lambda _: httpx.Response(
            200,
            content=b"text",
            headers={
                "content-type": "text/plain",
                "content-disposition": "attachment; filename*=UTF-8''..%2F%E4%B8%AD%E6%96%87.txt",
            },
        )
    )
    result = await content.download_file(client, "token", "known.txt")
    assert result.filename == "中文.txt"


@pytest.mark.asyncio
async def test_file_rejects_unsupported_parser_extension(transport_client):
    client, _ = transport_client(lambda _: httpx.Response(200, content=b"archive"))
    with pytest.raises(content.UnsupportedContentError, match=".zip"):
        await content.download_file(client, "token", "archive.zip")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "data",
    [
        {"metas": [], "failed_list": []},
        {"metas": [{"doc_token": "other", "doc_type": "file", "title": "x.pdf"}]},
        {
            "metas": [{"doc_token": "token", "doc_type": "file", "title": "x.pdf"}],
            "failed_list": [{"code": 403}],
        },
        {"metas": [{"doc_token": "token", "doc_type": "file"}]},
    ],
)
async def test_invalid_file_metadata_fails_before_download(transport_client, data):
    client, requests = transport_client(
        lambda _: httpx.Response(200, json={"code": 0, "data": data})
    )
    with pytest.raises(FeishuAPIError, match="metadata"):
        await content.download_file(client, "token")
    assert not any(request.url.path.endswith("/download") for request in requests)


def export_result(**updates):
    return {
        "job_status": 0,
        "file_token": "export-token",
        "file_name": "Report",
        "file_extension": "docx",
        "type": "doc",
        "file_size": 4,
        **updates,
    }


@pytest.mark.asyncio
async def test_export_polls_supported_statuses_and_uses_export_download(
    transport_client, monkeypatch
):
    states = iter([{"job_status": 1}, {"job_status": 2}, export_result()])
    monkeypatch.setattr(content.asyncio, "sleep", AsyncMock())

    def handler(request):
        if request.method == "POST":
            assert request.url.path == "/open-apis/drive/v1/export_tasks"
            assert b'"file_extension":"docx"' in request.content
            return httpx.Response(200, json={"code": 0, "data": {"ticket": "ticket"}})
        if request.url.path.endswith("/ticket"):
            assert request.url.params["token"] == "doc-token"
            return httpx.Response(
                200, json={"code": 0, "data": {"result": next(states)}}
            )
        assert (
            request.url.path
            == "/open-apis/drive/v1/export_tasks/file/export-token/download"
        )
        return httpx.Response(200, content=b"docx")

    client, _ = transport_client(handler)
    result = await content.export_document(client, "doc-token", "doc", "docx")
    assert result.filename == "Report.docx"
    assert result.content == b"docx"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "result",
    [
        {"job_status": 3, "job_error_msg": "internal"},
        {"job_status": 109, "job_error_msg": "block without permission"},
        {"job_status": 999},
        {"job_status": False},
        {},
        export_result(file_token=""),
        export_result(file_size=-1),
        export_result(file_extension="pdf"),
        export_result(type="docx"),
        export_result(file_name=""),
    ],
)
async def test_failed_or_malformed_exports_never_download(transport_client, result):
    def handler(request):
        data = {"ticket": "ticket"} if request.method == "POST" else {"result": result}
        return httpx.Response(200, json={"code": 0, "data": data})

    client, requests = transport_client(handler)
    with pytest.raises(FeishuAPIError):
        await content.export_document(client, "doc-token", "doc", "docx")
    assert not any(request.url.path.endswith("/download") for request in requests)


@pytest.mark.asyncio
async def test_export_rejects_size_mismatch(transport_client):
    def handler(request):
        if request.url.path.endswith("/download"):
            return httpx.Response(200, content=b"partial")
        data = (
            {"ticket": "ticket"}
            if request.method == "POST"
            else {"result": export_result()}
        )
        return httpx.Response(200, json={"code": 0, "data": data})

    client, _ = transport_client(handler)
    with pytest.raises(FeishuAPIError, match="size does not match"):
        await content.export_document(client, "doc-token", "doc", "docx")


@pytest.mark.asyncio
async def test_export_deadline_is_a_failure(monkeypatch):
    import asyncio

    async def blocked(*_args, **_kwargs):
        await asyncio.Event().wait()

    monkeypatch.setattr(content, "request_json", blocked)
    monkeypatch.setattr(content, "EXPORT_TIMEOUT_SECONDS", 0.001)
    with pytest.raises(FeishuAPIError, match="deadline"):
        await content.export_document(object(), "token", "doc", "docx")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "obj_type,extension", [("mindnote", "pdf"), ("doc", "xlsx"), ("unknown", "docx")]
)
async def test_unsupported_export_format_is_explicit_without_api_call(
    transport_client, obj_type, extension
):
    client, requests = transport_client(lambda _: pytest.fail("unexpected request"))
    with pytest.raises(content.UnsupportedContentError):
        await content.export_document(client, "token", obj_type, extension)
    assert requests == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "value,expected", [(False, 50), (None, 50), (0, 1), (5000, 1024), (12, 12)]
)
async def test_content_limit_matches_upload_setting_bounds(
    monkeypatch, value, expected
):
    monkeypatch.setattr(content.SiteSetting, "get_value", AsyncMock(return_value=value))
    assert await content.content_limit_bytes() == expected * 1024 * 1024


@pytest.mark.asyncio
async def test_named_json_file_with_code_fields_is_not_api_error(transport_client):
    client, _ = transport_client(
        lambda _: httpx.Response(
            200,
            json={"code": 123, "msg": "real document content"},
            headers={"content-disposition": 'attachment; filename="record.json"'},
        )
    )
    result = await content.download_file(client, "token", "record.json")
    assert result.filename == "record.json"
    assert b"real document content" in result.content


@pytest.mark.asyncio
async def test_oversized_export_result_never_requests_download(transport_client):
    def handler(request):
        data = (
            {"ticket": "ticket"}
            if request.method == "POST"
            else {"result": export_result(file_size=1024 * 1024 + 1)}
        )
        return httpx.Response(200, json={"code": 0, "data": data})

    client, requests = transport_client(handler)
    with pytest.raises(FeishuAPIError, match="size limit"):
        await content.export_document(client, "doc-token", "doc", "docx")
    assert not any(request.url.path.endswith("/download") for request in requests)
