from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.llm.adapters.image.siliconflow import SiliconFlowImageAdapter
from app.llm.errors import (
    AuthenticationError,
    ContentFilterError,
    InvalidRequestError,
    ProviderError,
    RateLimitError,
)
from app.llm.types import ImageContent, ImageGenerationRequest


def build_adapter(**overrides):
    values = {
        "api_key": "fake-key",
        "base_url": "https://images.example/v1/",
        "model_id": "fake-image-model",
        "config": {},
        "default_params": {},
    }
    values.update(overrides)
    return SiliconFlowImageAdapter(SimpleNamespace(**values))


def response(status_code=200, *, json_data=None, text=""):
    request = httpx.Request("POST", "https://images.example/v1/images/generations")
    if json_data is not None:
        return httpx.Response(status_code, json=json_data, request=request)
    return httpx.Response(status_code, text=text, request=request)


def mock_client(*, result=None, error=None):
    client = MagicMock()
    client.post = AsyncMock(return_value=result, side_effect=error)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    return client


def test_initialization_and_url_normalization():
    default = build_adapter(base_url=None)
    custom = build_adapter(base_url="https://images.example/v1/")

    assert default.base_url == "https://api.siliconflow.cn/v1"
    assert default._build_url("images/generations").endswith("/images/generations")
    assert custom.base_url == "https://images.example/v1"
    assert custom._build_url("/v1/images/generations") == (
        "https://images.example/v1/images/generations"
    )


def test_payload_uses_defaults_legacy_references_and_filters_managed_fields():
    adapter = build_adapter(
        default_params={
            "negative_prompt": "default blur",
            "seed": 12,
            "image": "https://images.example/reference.png",
            "image2": "",
            "num_inference_steps": 20,
        }
    )

    payload = adapter._build_payload(
        ImageGenerationRequest(
            prompt="A fake landscape",
            negative_prompt="",
            extra_params={
                "model": "wrong",
                "prompt": "wrong",
                "seed": "not-an-int",
                "guidance_scale": 6.5,
                "custom": "kept",
            },
        )
    )

    assert payload == {
        "model": "fake-image-model",
        "prompt": "A fake landscape",
        "image_size": "1024x1024",
        "batch_size": 1,
        "negative_prompt": "default blur",
        "image": "https://images.example/reference.png",
        "num_inference_steps": 20,
        "guidance_scale": 6.5,
        "custom": "kept",
    }
    assert (
        adapter._build_payload(ImageGenerationRequest(prompt="Seeded fake", seed=7))[
            "seed"
        ]
        == 7
    )


def test_payload_converts_three_explicit_reference_images():
    adapter = build_adapter()

    payload = adapter._build_payload(
        ImageGenerationRequest(
            prompt="Edit fake images",
            images=[
                ImageContent(url="https://images.example/one.png"),
                ImageContent(base64="ZmFrZQ==", format="jpeg"),
                ImageContent(base64="cG5n"),
            ],
            extra_params={"image": "ignored", "image3": "ignored"},
        )
    )

    assert payload["image"] == "https://images.example/one.png"
    assert payload["image2"] == "data:image/png;base64,ZmFrZQ=="
    assert payload["image3"] == "data:image/png;base64,cG5n"

    with pytest.raises(InvalidRequestError, match="up to 3"):
        adapter._build_reference_image_fields(
            ImageGenerationRequest(
                prompt="Too many fakes",
                images=[ImageContent(base64="Zg==")] * 4,
            )
        )


@pytest.mark.anyio
async def test_generate_posts_payload_and_parses_data_response():
    provider_response = response(
        json_data={
            "data": [
                {
                    "b64_json": "ZmFrZS1pbWFnZQ==",
                    "revised_prompt": "A revised fake prompt",
                }
            ],
            "seed": "42",
        }
    )
    client = mock_client(result=provider_response)

    with patch(
        "app.llm.adapters.image.siliconflow.httpx.AsyncClient",
        return_value=client,
    ) as client_class:
        result = await build_adapter(config={"timeout": 9}).generate(
            ImageGenerationRequest(prompt="A fake prompt")
        )

    client_class.assert_called_once_with(timeout=9.0)
    client.post.assert_awaited_once()
    (url,) = client.post.await_args.args
    assert url == "https://images.example/v1/images/generations"
    assert (
        client.post.await_args.kwargs["headers"]["Authorization"] == "Bearer fake-key"
    )
    assert client.post.await_args.kwargs["json"]["prompt"] == "A fake prompt"
    assert result.images[0].image.base64 == "ZmFrZS1pbWFnZQ=="
    assert result.images[0].image.format == "png"
    assert result.images[0].revised_prompt == "A revised fake prompt"
    assert result.images[0].seed == 42


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("error", "message"),
    [
        (httpx.ReadTimeout("slow"), "timeout"),
        (
            httpx.RequestError(
                "offline", request=httpx.Request("POST", "https://images.example")
            ),
            "request failed",
        ),
    ],
)
async def test_generate_maps_transport_errors(error, message):
    client = mock_client(error=error)

    with (
        patch(
            "app.llm.adapters.image.siliconflow.httpx.AsyncClient",
            return_value=client,
        ),
        pytest.raises(ProviderError, match=message),
    ):
        await build_adapter().generate(ImageGenerationRequest(prompt="Fake"))


@pytest.mark.anyio
async def test_generate_rejects_non_json_success_response():
    client = mock_client(result=response(text="not json"))

    with (
        patch(
            "app.llm.adapters.image.siliconflow.httpx.AsyncClient",
            return_value=client,
        ),
        pytest.raises(ProviderError),
    ):
        await build_adapter().generate(ImageGenerationRequest(prompt="Fake"))


@pytest.mark.parametrize(
    ("status_code", "body", "error_type", "message"),
    [
        (
            401,
            {"error": {"message": "bad fake key"}},
            AuthenticationError,
            "bad fake key",
        ),
        (
            404,
            {"error": "missing fake model"},
            InvalidRequestError,
            "missing fake model",
        ),
        (429, {"message": "fake quota"}, RateLimitError, "fake quota"),
        (
            422,
            {"detail": "unsafe fake prompt"},
            ContentFilterError,
            "unsafe fake prompt",
        ),
        (400, {}, InvalidRequestError, None),
        (503, {"errors": [{"detail": "down"}, "retry"]}, ProviderError, "down; retry"),
    ],
)
def test_raise_for_status_maps_provider_failures(
    status_code, body, error_type, message
):
    adapter = build_adapter()

    with pytest.raises(error_type, match=message):
        adapter._raise_for_status(response(status_code, json_data=body))

    adapter._raise_for_status(response())


@pytest.mark.parametrize(
    ("body", "text", "expected"),
    [
        ({"errors": [{"message": "one"}, {"code": 2}, 3]}, "", "one; {'code': 2}; 3"),
        ({"error": {"detail": " fake detail "}}, "", "fake detail"),
        ({"error": {"type": "fake_type"}}, "", "fake_type"),
        ({"error": " fake string "}, "", "fake string"),
        ({"detail": " top detail "}, "", "top detail"),
        (["unexpected"], "", '["unexpected"]'),
        (None, "plain failure", "plain failure"),
    ],
)
def test_extract_error_message_variants(body, text, expected):
    provider_response = (
        response(500, json_data=body) if body is not None else response(500, text=text)
    )
    if body is not None and text:
        provider_response = httpx.Response(
            500,
            json=body,
            request=httpx.Request("POST", "https://images.example"),
        )

    assert build_adapter()._extract_error_message(provider_response) == expected


@pytest.mark.parametrize(
    ("data", "expected"),
    [({"seed": 7}, 7), ({"seed": "008"}, 8), ({"seed": "bad"}, None), ({}, None)],
)
def test_extract_seed(data, expected):
    assert build_adapter()._extract_seed(data) == expected


def test_parse_response_skips_invalid_items_and_accepts_base64_alias():
    result = build_adapter()._parse_response_data(
        {
            "images": [
                "invalid",
                {"url": 12, "base64": 34},
                {"url": "https://images.example/fake.jpg", "b64_json": 5},
                {"url": None, "base64": "ZmFrZQ=="},
            ],
            "seed": False,
        }
    )

    assert [image.image.format for image in result.images] == ["jpg", "png"]
    assert result.images[0].image.url == "https://images.example/fake.jpg"
    assert result.images[1].image.base64 == "ZmFrZQ=="
    assert all(image.seed == 0 for image in result.images)


@pytest.mark.parametrize("data", [{}, {"images": None}, {"images": [None, {}]}])
def test_parse_response_requires_at_least_one_image(data):
    with pytest.raises(ProviderError, match="missing generated images"):
        build_adapter()._parse_response_data(data)


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("CONTENT_POLICY", True),
        ("Safety block", True),
        ("moderation", True),
        ("unsafe", True),
        ("quota", False),
    ],
)
def test_content_filter_detection(message, expected):
    assert build_adapter()._is_content_filter_error(message) is expected
