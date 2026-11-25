"""Tests for the OCR adapters, factory, manager routing and admin probe."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from pydantic import ValidationError

from app.llm.adapters.ocr import (
    MistralOCRAdapter,
    OpenAICompatibleOCRAdapter,
    create_ocr_adapter,
)
from app.llm.errors import (
    AuthenticationError,
    InsufficientQuotaError,
    InvalidRequestError,
    ProviderError,
    RateLimitError,
)
from app.llm.errors import TimeoutError as LLMTimeoutError
from app.llm.manager import ModelManager
from app.llm.types import MediaContent, OCRPage, OCRRequest, OCRResponse, Usage
from app.models.model import ModelProvider

PNG_BASE64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="


@pytest.fixture(autouse=True)
def allow_model_endpoints(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ModelManager, "_ensure_model_endpoint_allowed", AsyncMock())


def build_config(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "provider": ModelProvider.MISTRAL,
        "model_id": "mistral-ocr-latest",
        "api_key": "secret",
        "base_url": None,
        "default_params": None,
        "config": None,
        "max_output_tokens": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def build_request(**overrides: object) -> OCRRequest:
    values: dict[str, object] = {
        "source": MediaContent(base64=PNG_BASE64, mime_type="image/png"),
    }
    values.update(overrides)
    return OCRRequest(**values)


def text_response(payload: dict[str, object]) -> httpx.Response:
    return httpx.Response(
        200,
        json=payload,
        request=httpx.Request("POST", "https://example.test/ocr"),
    )


def error_response(status: int, body: object) -> httpx.Response:
    request = httpx.Request("POST", "https://example.test/ocr")
    if isinstance(body, dict):
        return httpx.Response(status, json=body, request=request)
    return httpx.Response(status, content=body, request=request)


# ---------------------------------------------------------------- factory


def test_factory_selects_mistral_adapter() -> None:
    adapter = create_ocr_adapter(build_config(provider=ModelProvider.MISTRAL))
    assert isinstance(adapter, MistralOCRAdapter)


@pytest.mark.parametrize("provider", [ModelProvider.QWEN, ModelProvider.CUSTOM])
def test_factory_selects_openai_compatible_adapter(provider: ModelProvider) -> None:
    adapter = create_ocr_adapter(build_config(provider=provider))
    assert isinstance(adapter, OpenAICompatibleOCRAdapter)


def test_factory_accepts_plain_string_provider() -> None:
    adapter = create_ocr_adapter(build_config(provider="mistral"))
    assert isinstance(adapter, MistralOCRAdapter)


def test_factory_rejects_unsupported_provider() -> None:
    with pytest.raises(ValueError, match="Unsupported provider for OCR models"):
        create_ocr_adapter(build_config(provider=ModelProvider.OPENAI))


def test_factory_rejects_config_without_provider() -> None:
    with pytest.raises(ValueError, match="Unsupported provider for OCR models"):
        create_ocr_adapter(build_config(provider=None))


# ---------------------------------------------------------------- request


def test_request_requires_source_content() -> None:
    with pytest.raises(ValueError, match="source must carry"):
        OCRRequest(source=MediaContent())


def test_response_text_joins_pages_and_skips_blanks() -> None:
    from app.llm.types import OCRPage, OCRResponse

    response = OCRResponse(
        model="m",
        pages=[
            OCRPage(index=0, markdown="first"),
            OCRPage(index=1, markdown="   "),
            OCRPage(index=2, markdown=" second "),
        ],
    )
    assert response.text == "first\n\nsecond"


# ---------------------------------------------------------------- mistral


def test_mistral_endpoint_uses_configured_base_url() -> None:
    adapter = MistralOCRAdapter(build_config(base_url="https://proxy.test/v1/"))
    assert adapter._get_endpoint() == "https://proxy.test/v1/ocr"


def test_mistral_endpoint_requires_base_url() -> None:
    adapter = MistralOCRAdapter(build_config(base_url=None))
    with patch(
        "app.llm.adapters.ocr.mistral_adapter.get_effective_model_base_url",
        return_value=None,
    ):
        with pytest.raises(ValueError, match="base_url"):
            adapter._get_endpoint()


def test_mistral_headers_include_bearer_token() -> None:
    adapter = MistralOCRAdapter(build_config(api_key="secret"))
    assert adapter._build_headers()["Authorization"] == "Bearer secret"


def test_mistral_headers_omit_missing_token() -> None:
    adapter = MistralOCRAdapter(build_config(api_key=None))
    assert "Authorization" not in adapter._build_headers()


def test_mistral_payload_inlines_image_and_options() -> None:
    adapter = MistralOCRAdapter(build_config())
    request = build_request(pages="0-2", include_blocks=True)
    payload = adapter._build_payload(request)

    assert payload["model"] == "mistral-ocr-latest"
    assert payload["document"]["type"] == "image_url"
    assert payload["document"]["image_url"].startswith("data:image/png;base64,")
    assert payload["pages"] == "0-2"
    assert payload["include_blocks"] is True


def test_mistral_payload_omits_optional_fields() -> None:
    adapter = MistralOCRAdapter(build_config())
    payload = adapter._build_payload(build_request())

    assert "pages" not in payload
    assert "include_blocks" not in payload


def test_mistral_payload_sends_pdf_as_document_url() -> None:
    adapter = MistralOCRAdapter(build_config())
    request = build_request(
        source=MediaContent(
            url="https://files.test/doc.pdf", mime_type="application/pdf"
        )
    )
    payload = adapter._build_payload(request)

    assert payload["document"] == {
        "type": "document_url",
        "document_url": "https://files.test/doc.pdf",
        "document_name": None,
    }


def test_ocr_request_rejects_a_local_file_path() -> None:
    # Adapters post the document over HTTP, so a local path can never be sent.
    with pytest.raises(ValidationError, match="url or a base64 payload"):
        OCRRequest(
            source=MediaContent(file_path="/tmp/page.png", mime_type="image/png")
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "kwargs"),
    [("pages", {"pages": "0-2"}), ("include_blocks", {"include_blocks": True})],
)
async def test_chat_adapter_rejects_unsupported_request_fields(field, kwargs) -> None:
    adapter = OpenAICompatibleOCRAdapter(build_config(provider=ModelProvider.QWEN))
    with patch("httpx.AsyncClient") as client_cls:
        with pytest.raises(InvalidRequestError) as error:
            await adapter.recognize(build_request(**kwargs))

    assert error.value.field == field
    assert field in error.value.message
    assert error.value.details["field"] == field
    # Rejected before any request leaves the process.
    client_cls.assert_not_called()


@pytest.mark.asyncio
async def test_mistral_adapter_accepts_page_selection_and_blocks() -> None:
    adapter = MistralOCRAdapter(build_config())
    client = AsyncMock()
    client.post = AsyncMock(
        return_value=text_response({"pages": [{"index": 0, "markdown": "hi"}]})
    )

    with patch("app.llm.adapters.ocr.mistral_adapter.httpx.AsyncClient") as client_cls:
        client_cls.return_value.__aenter__ = AsyncMock(return_value=client)
        client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        result = await adapter.recognize(
            build_request(pages="0-2", include_blocks=True)
        )

    assert result.text == "hi"


def test_mistral_parses_pages_blocks_and_dimensions() -> None:
    adapter = MistralOCRAdapter(build_config())
    response = adapter._parse_response(
        {
            "model": "mistral-ocr-latest",
            "pages": [
                {
                    "index": 0,
                    "markdown": "# Title\n\nBody",
                    "dimensions": {"width": 612, "height": 792},
                    "blocks": [
                        {
                            "type": "title",
                            "text": "Title",
                            "bbox": [0, 0, 100, 20],
                            "confidence": 0.97,
                        },
                        {
                            "content": "Body",
                            "bounding_box": {
                                "top_left_x": 0,
                                "top_left_y": 30,
                                "bottom_right_x": 100,
                                "bottom_right_y": 50,
                            },
                        },
                    ],
                }
            ],
        },
        build_request(),
    )

    assert response.model == "mistral-ocr-latest"
    page = response.pages[0]
    assert page.index == 0
    assert page.markdown == "# Title\n\nBody"
    assert (page.width, page.height) == (612.0, 792.0)
    assert [block.type for block in page.blocks] == ["title", "text"]
    assert page.blocks[0].bbox == (0.0, 0.0, 100.0, 20.0)
    assert page.blocks[0].confidence == 0.97
    assert page.blocks[1].bbox == (0.0, 30.0, 100.0, 50.0)


def test_mistral_parse_tolerates_malformed_blocks() -> None:
    adapter = MistralOCRAdapter(build_config())
    response = adapter._parse_response(
        {
            "pages": [
                {
                    "markdown": "",
                    "blocks": [
                        "not-a-block",
                        {"bbox": [1, 2, 3]},
                        {"bbox": {"top_left_x": "bad"}},
                        {"confidence": 5},
                        {"type": 7, "text": 9},
                    ],
                }
            ]
        },
        build_request(),
    )

    blocks = response.pages[0].blocks
    assert blocks[0].bbox is None
    assert blocks[0].confidence is None
    assert blocks[-1].type == "text"
    assert blocks[-1].text == "9"


def test_mistral_normalizes_out_of_range_confidence() -> None:
    from app.llm.adapters.ocr.mistral_adapter import _as_confidence

    assert _as_confidence(1.5) is None
    assert _as_confidence(-0.1) is None
    assert _as_confidence("x") is None
    assert _as_confidence(None) is None
    assert _as_confidence(0.5) == 0.5


def test_mistral_parse_falls_back_to_requested_model() -> None:
    adapter = MistralOCRAdapter(build_config(model_id="configured"))
    response = adapter._parse_response(
        {"pages": [{"markdown": ""}], "usage_info": {"pages_processed": 3}},
        build_request(model="override"),
    )
    assert response.model == "override"
    assert response.pages == [OCRPage(index=0, markdown="")]
    assert response.pages_processed == 3
    assert response.usage == Usage()


@pytest.mark.asyncio
async def test_mistral_recognize_posts_and_returns_response() -> None:
    adapter = MistralOCRAdapter(build_config())
    client = AsyncMock()
    client.post = AsyncMock(
        return_value=text_response(
            {"model": "mistral-ocr-latest", "pages": [{"index": 0, "markdown": "hi"}]}
        )
    )

    with patch("app.llm.adapters.ocr.mistral_adapter.httpx.AsyncClient") as client_cls:
        client_cls.return_value.__aenter__ = AsyncMock(return_value=client)
        client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        result = await adapter.recognize(build_request())

    assert result.text == "hi"
    assert result.usage == Usage()


@pytest.mark.asyncio
async def test_mistral_recognize_rejects_non_mapping_body() -> None:
    adapter = MistralOCRAdapter(build_config())
    client = AsyncMock()
    client.post = AsyncMock(
        return_value=httpx.Response(
            200, json=[1, 2], request=httpx.Request("POST", "https://x.test/ocr")
        )
    )

    with patch("app.llm.adapters.ocr.mistral_adapter.httpx.AsyncClient") as client_cls:
        client_cls.return_value.__aenter__ = AsyncMock(return_value=client)
        client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        with pytest.raises(ProviderError, match="Invalid OCR provider response"):
            await adapter.recognize(build_request())


@pytest.mark.asyncio
async def test_mistral_recognize_maps_timeout() -> None:
    adapter = MistralOCRAdapter(build_config())
    client = AsyncMock()
    client.post = AsyncMock(side_effect=httpx.ConnectTimeout("slow"))

    with patch("app.llm.adapters.ocr.mistral_adapter.httpx.AsyncClient") as client_cls:
        client_cls.return_value.__aenter__ = AsyncMock(return_value=client)
        client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        with pytest.raises(LLMTimeoutError):
            await adapter.recognize(build_request())


@pytest.mark.asyncio
async def test_mistral_recognize_maps_request_error() -> None:
    adapter = MistralOCRAdapter(build_config())
    client = AsyncMock()
    client.post = AsyncMock(side_effect=httpx.ConnectError("boom"))

    with patch("app.llm.adapters.ocr.mistral_adapter.httpx.AsyncClient") as client_cls:
        client_cls.return_value.__aenter__ = AsyncMock(return_value=client)
        client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        with pytest.raises(ProviderError, match="request failed"):
            await adapter.recognize(build_request())


# ------------------------------------------------- openai-compatible


def test_chat_endpoint_appends_completions_path() -> None:
    adapter = OpenAICompatibleOCRAdapter(build_config(provider=ModelProvider.QWEN))
    assert adapter._get_endpoint().endswith("/chat/completions")


def test_chat_endpoint_requires_base_url() -> None:
    adapter = OpenAICompatibleOCRAdapter(build_config(provider=ModelProvider.QWEN))
    with patch(
        "app.llm.adapters.ocr.openai_compatible_adapter.get_effective_model_base_url",
        return_value=None,
    ):
        with pytest.raises(ValueError, match="base_url"):
            adapter._get_endpoint()


def test_chat_payload_omits_text_part_without_instruction() -> None:
    adapter = OpenAICompatibleOCRAdapter(build_config(provider=ModelProvider.QWEN))
    payload = adapter._build_payload(build_request())

    content = payload["messages"][0]["content"]
    assert [part["type"] for part in content] == ["image_url"]
    assert payload["stream"] is False


def test_chat_payload_sends_the_image_alone() -> None:
    # An OCR model is never addressed as a conversation, so no text part is sent
    # and the provider's own transcription prompt applies.
    adapter = OpenAICompatibleOCRAdapter(build_config(provider=ModelProvider.QWEN))
    content = adapter._build_payload(build_request())["messages"][0]["content"]

    assert [part["type"] for part in content] == ["image_url"]


def test_chat_payload_forwards_generation_caps() -> None:
    adapter = OpenAICompatibleOCRAdapter(
        build_config(
            provider=ModelProvider.QWEN,
            default_params={"temperature": 0, "max_tokens": 512},
            max_output_tokens=256,
        )
    )
    payload = adapter._build_payload(build_request())

    assert payload["temperature"] == 0
    assert payload["max_tokens"] == 512


def test_chat_payload_falls_back_to_max_output_tokens() -> None:
    adapter = OpenAICompatibleOCRAdapter(
        build_config(provider=ModelProvider.QWEN, max_output_tokens=256)
    )
    assert adapter._build_payload(build_request())["max_tokens"] == 256


def test_request_requires_a_transmittable_source() -> None:
    from app.llm.adapters.ocr.openai_compatible_adapter import _as_data_uri

    # Nothing to send: the request type rejects it before any adapter sees it.
    with pytest.raises(ValidationError, match="url or a base64 payload"):
        OCRRequest(source=MediaContent(mime_type="image/png"))

    # A url still passes straight through to the wire format.
    assert (
        _as_data_uri(MediaContent(url="https://x.test/a.png")) == "https://x.test/a.png"
    )


def test_chat_data_uri_passthroughs_url() -> None:
    from app.llm.adapters.ocr.openai_compatible_adapter import _as_data_uri

    assert (
        _as_data_uri(MediaContent(url="https://x.test/a.png")) == "https://x.test/a.png"
    )


def test_chat_data_uri_defaults_mime_type() -> None:
    from app.llm.adapters.ocr.openai_compatible_adapter import _as_data_uri

    assert _as_data_uri(MediaContent(base64="abc")).startswith(
        "data:image/jpeg;base64,"
    )


def test_chat_parse_reads_usage() -> None:
    adapter = OpenAICompatibleOCRAdapter(build_config(provider=ModelProvider.QWEN))
    response = adapter._parse_response(
        {
            "model": "qwen-vl-ocr",
            "choices": [{"message": {"content": "recognized"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 4},
        },
        build_request(),
    )

    assert response.text == "recognized"
    assert response.usage.total_tokens == 14
    assert response.usage.total_input_tokens == 10


def test_chat_parse_flattens_content_parts() -> None:
    adapter = OpenAICompatibleOCRAdapter(build_config(provider=ModelProvider.QWEN))
    response = adapter._parse_response(
        {
            "choices": [
                {"message": {"content": [{"type": "text", "text": "a"}, {"text": "b"}]}}
            ]
        },
        build_request(),
    )
    assert response.text == "ab"


def test_chat_parse_accepts_blank_transcription() -> None:
    adapter = OpenAICompatibleOCRAdapter(build_config(provider=ModelProvider.QWEN))
    response = adapter._parse_response(
        {"choices": [{"message": {"content": ""}}]}, build_request(model="override")
    )
    assert response.model == "override"
    assert response.pages == [OCRPage(index=0, markdown="")]
    assert response.usage == Usage()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider", "body"),
    [
        (ModelProvider.QWEN, b"not JSON"),
        (ModelProvider.MISTRAL, b"not JSON"),
        (ModelProvider.QWEN, {}),
        (ModelProvider.QWEN, {"choices": []}),
        (ModelProvider.QWEN, {"choices": ["nope"]}),
        (ModelProvider.QWEN, {"choices": [{}]}),
        (ModelProvider.QWEN, {"choices": [{"message": {}}]}),
        (ModelProvider.QWEN, {"choices": [{"message": {"content": [{"text": 3}]}}]}),
        (
            ModelProvider.QWEN,
            {
                "choices": [{"message": {"content": "text"}}],
                "usage": {"total_tokens": "bad"},
            },
        ),
        (ModelProvider.MISTRAL, {}),
        (ModelProvider.MISTRAL, {"pages": []}),
        (ModelProvider.MISTRAL, {"pages": [None]}),
        (ModelProvider.MISTRAL, {"pages": [{}]}),
        (ModelProvider.MISTRAL, {"pages": [{"markdown": "", "blocks": 5}]}),
    ],
)
async def test_recognize_rejects_invalid_success_response(provider, body) -> None:
    adapter = create_ocr_adapter(build_config(provider=provider))
    response = httpx.Response(
        200,
        content=body if isinstance(body, bytes) else None,
        json=body if isinstance(body, dict) else None,
        request=httpx.Request("POST", "https://x.test/ocr"),
    )
    with patch("httpx.AsyncClient") as client_cls:
        client_cls.return_value.__aenter__ = AsyncMock(
            return_value=SimpleNamespace(post=AsyncMock(return_value=response))
        )
        with pytest.raises(
            ProviderError, match="Invalid OCR provider response"
        ) as error:
            await adapter.recognize(build_request(model="override"))
    assert error.value.provider == provider.value
    assert error.value.model == "override"


@pytest.mark.asyncio
async def test_chat_recognize_posts_and_returns_response() -> None:
    adapter = OpenAICompatibleOCRAdapter(build_config(provider=ModelProvider.QWEN))
    client = AsyncMock()
    client.post = AsyncMock(
        return_value=text_response({"choices": [{"message": {"content": "hello"}}]})
    )

    with patch(
        "app.llm.adapters.ocr.openai_compatible_adapter.httpx.AsyncClient"
    ) as client_cls:
        client_cls.return_value.__aenter__ = AsyncMock(return_value=client)
        client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        result = await adapter.recognize(build_request(), timeout=5)

    assert result.text == "hello"


@pytest.mark.asyncio
async def test_chat_recognize_rejects_non_mapping_body() -> None:
    adapter = OpenAICompatibleOCRAdapter(build_config(provider=ModelProvider.QWEN))
    client = AsyncMock()
    client.post = AsyncMock(
        return_value=httpx.Response(
            200,
            json=[1],
            request=httpx.Request("POST", "https://x.test/chat/completions"),
        )
    )

    with patch(
        "app.llm.adapters.ocr.openai_compatible_adapter.httpx.AsyncClient"
    ) as client_cls:
        client_cls.return_value.__aenter__ = AsyncMock(return_value=client)
        client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        with pytest.raises(ProviderError, match="Invalid OCR provider response"):
            await adapter.recognize(build_request())


@pytest.mark.asyncio
async def test_chat_recognize_maps_request_error() -> None:
    adapter = OpenAICompatibleOCRAdapter(build_config(provider=ModelProvider.QWEN))
    client = AsyncMock()
    client.post = AsyncMock(side_effect=httpx.ConnectError("boom"))

    with patch(
        "app.llm.adapters.ocr.openai_compatible_adapter.httpx.AsyncClient"
    ) as client_cls:
        client_cls.return_value.__aenter__ = AsyncMock(return_value=client)
        client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        with pytest.raises(ProviderError, match="request failed"):
            await adapter.recognize(build_request())


# --------------------------------------------------------- error mapping


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (401, AuthenticationError),
        (402, InsufficientQuotaError),
        (429, RateLimitError),
        (400, InvalidRequestError),
        (422, InvalidRequestError),
        (500, ProviderError),
    ],
)
@pytest.mark.asyncio
async def test_mistral_maps_http_status_to_error(
    status: int, expected: type[Exception]
) -> None:
    adapter = MistralOCRAdapter(build_config())
    client = AsyncMock()
    client.post = AsyncMock(return_value=error_response(status, {"detail": "nope"}))

    with patch("app.llm.adapters.ocr.mistral_adapter.httpx.AsyncClient") as client_cls:
        client_cls.return_value.__aenter__ = AsyncMock(return_value=client)
        client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        with pytest.raises(expected) as exc_info:
            await adapter.recognize(build_request())

    assert "nope" in str(exc_info.value)


def test_error_message_handles_message_and_nested_error() -> None:
    from app.llm.adapters.ocr.base import error_message

    assert error_message(error_response(400, {"message": "m"}), "X") == "m"
    assert "{'code': 1}" in error_message(
        error_response(400, {"error": {"code": 1}}), "X"
    )


def test_error_message_handles_unparseable_body() -> None:
    from app.llm.adapters.ocr.base import error_message

    assert error_message(error_response(500, b"<html>"), "Mistral") == (
        "Mistral request failed with status 500"
    )


def test_error_message_ignores_blank_detail() -> None:
    from app.llm.adapters.ocr.base import error_message

    assert error_message(error_response(400, {"detail": "  "}), "Mistral") == (
        "Mistral request failed with status 400"
    )


def test_error_message_defaults_label() -> None:
    from app.llm.adapters.ocr.base import error_message

    assert error_message(error_response(500, {"detail": "x"}), "") == "x"
    assert error_message(error_response(500, b"x"), "") == (
        " request failed with status 500"
    )


def test_provider_value_reads_enum_and_string() -> None:
    from app.llm.adapters.ocr.base import provider_value

    assert provider_value(build_config(provider=ModelProvider.MISTRAL)) == "mistral"
    assert provider_value(build_config(provider="qwen")) == "qwen"
    assert provider_value(SimpleNamespace()) == ""


# ------------------------------------------------------------- team_ocr


def build_team_model_config() -> SimpleNamespace:
    return SimpleNamespace(
        id="m-1", model_id="mistral-ocr-latest", provider=ModelProvider.MISTRAL
    )


@pytest.mark.parametrize(
    ("tokens", "pages_processed", "returned_pages", "expected"),
    [(320, 3, 2, 320), (0, 3, 2, 3000), (0, None, 2, 2000), (0, 0, 0, 1000)],
)
def test_team_ocr_records_tokens_or_estimates_from_pages(
    tokens, pages_processed, returned_pages, expected
) -> None:
    manager = ModelManager()
    adapter = SimpleNamespace(
        recognize=AsyncMock(
            return_value=OCRResponse(
                model="mistral-ocr-latest",
                usage=Usage(total_tokens=tokens),
                pages_processed=pages_processed,
                pages=[
                    OCRPage(index=i, markdown="# Invoice")
                    for i in range(returned_pages)
                ],
            )
        )
    )
    record = AsyncMock()

    with (
        patch.object(
            ModelManager,
            "_get_team_model",
            AsyncMock(
                return_value=(build_team_model_config(), SimpleNamespace(id="tm-1"))
            ),
        ),
        patch("app.llm.manager.usage_tracker.check_quota_with_model", AsyncMock()),
        patch("app.llm.manager.create_ocr_adapter", return_value=adapter),
        patch.object(ModelManager, "_check_and_record_usage", record),
    ):
        result = asyncio.run(manager.team_ocr("team-1", build_request()))

    assert result.usage.total_tokens == tokens
    record.assert_awaited_once_with(
        team_id="team-1", model_id="m-1", tokens_used=expected
    )


def test_team_ocr_accepts_payload_dicts_and_preserves_llm_errors() -> None:
    manager = ModelManager()
    adapter = SimpleNamespace(
        recognize=AsyncMock(side_effect=ProviderError(message="provider down"))
    )

    with (
        patch.object(
            ModelManager,
            "_get_team_model",
            AsyncMock(
                return_value=(build_team_model_config(), SimpleNamespace(id="tm-1"))
            ),
        ),
        patch("app.llm.manager.usage_tracker.check_quota_with_model", AsyncMock()),
        patch("app.llm.manager.create_ocr_adapter", return_value=adapter),
    ):
        with pytest.raises(ProviderError):
            asyncio.run(
                manager.team_ocr(
                    "team-1",
                    {"source": MediaContent(base64=PNG_BASE64, mime_type="image/png")},
                )
            )

    assert isinstance(adapter.recognize.await_args.args[0], OCRRequest)


def test_team_ocr_wraps_unexpected_errors() -> None:
    manager = ModelManager()
    adapter = SimpleNamespace(
        recognize=AsyncMock(side_effect=RuntimeError("rate limit exceeded"))
    )

    with (
        patch.object(
            ModelManager,
            "_get_team_model",
            AsyncMock(
                return_value=(build_team_model_config(), SimpleNamespace(id="tm-1"))
            ),
        ),
        patch("app.llm.manager.usage_tracker.check_quota_with_model", AsyncMock()),
        patch("app.llm.manager.create_ocr_adapter", return_value=adapter),
    ):
        with pytest.raises(RateLimitError):
            asyncio.run(manager.team_ocr("team-1", build_request()))


def test_team_ocr_reports_quota_exceeded() -> None:
    manager = ModelManager()
    from app.llm.errors import QuotaExceededError as LLMQuotaExceededError
    from app.services.usage_tracker import QuotaExceededError

    with (
        patch.object(
            ModelManager,
            "_get_team_model",
            AsyncMock(
                return_value=(build_team_model_config(), SimpleNamespace(id="tm-1"))
            ),
        ),
        patch(
            "app.llm.manager.usage_tracker.check_quota_with_model",
            AsyncMock(
                side_effect=QuotaExceededError(
                    "daily token quota exceeded", "daily_tokens"
                )
            ),
        ),
    ):
        with pytest.raises(LLMQuotaExceededError) as exc_info:
            asyncio.run(manager.team_ocr("team-1", build_request()))

    assert exc_info.value.quota_type == "daily_tokens"


# -------------------------------------------------------- admin probe


class TestAdminOCRProbe:
    def test_probe_reports_empty_pages(self) -> None:
        from app.api.v1.admin.endpoints.models import _test_ocr_model
        from app.schemas.response import BusinessError

        adapter = SimpleNamespace(
            recognize=AsyncMock(
                return_value=SimpleNamespace(model="mistral-ocr-latest", pages=[])
            )
        )

        with patch("app.llm.adapters.ocr.create_ocr_adapter", return_value=adapter):
            with pytest.raises(BusinessError) as exc_info:
                asyncio.run(
                    _test_ocr_model(
                        ModelProvider.MISTRAL, "mistral-ocr-latest", "key", None, {}
                    )
                )

        assert exc_info.value.msg_key == "model_test_empty_ocr_result"

    def test_probe_accepts_recognized_pages(self) -> None:
        from app.api.v1.admin.endpoints.models import _test_ocr_model

        adapter = SimpleNamespace(
            recognize=AsyncMock(
                return_value=SimpleNamespace(
                    model="mistral-ocr-latest",
                    pages=[SimpleNamespace(index=0, markdown="hello")],
                )
            )
        )

        with patch("app.llm.adapters.ocr.create_ocr_adapter", return_value=adapter):
            asyncio.run(
                _test_ocr_model(
                    ModelProvider.MISTRAL, "mistral-ocr-latest", "key", None, {}
                )
            )

        sent_request = adapter.recognize.await_args.args[0]
        assert isinstance(sent_request, OCRRequest)
        assert sent_request.source.mime_type == "image/png"
