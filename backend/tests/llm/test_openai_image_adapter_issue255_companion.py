import asyncio
from enum import Enum
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.llm.adapters.image.openai import OpenAIImageAdapter
from app.llm.errors import (
    AuthenticationError,
    ContentFilterError,
    InvalidRequestError,
    ProviderError,
    RateLimitError,
)
from app.llm.types import ImageGenerationRequest


class Provider(Enum):
    OPENAI = "openai"


def adapter(model_id="gpt-image-1", **overrides):
    values = {
        "provider": Provider.OPENAI,
        "model_id": model_id,
        "api_key": "test-key",
        "base_url": None,
        "config": {},
        "default_params": {},
    }
    values.update(overrides)
    return OpenAIImageAdapter(SimpleNamespace(**values))


def run_generate(instance, response_or_error):
    client = AsyncMock()
    client.__aenter__.return_value = client
    if isinstance(response_or_error, Exception):
        client.post.side_effect = response_or_error
    else:
        client.post.return_value = response_or_error

    with patch(
        "app.llm.adapters.image.openai.httpx.AsyncClient", return_value=client
    ) as factory:
        result = asyncio.run(
            instance.generate(ImageGenerationRequest(prompt="Draw a lighthouse"))
        )
    return result, client, factory


def test_constructor_validation_and_url_normalization():
    with pytest.raises(InvalidRequestError):
        adapter(provider="custom", base_url=None)

    instance = adapter(base_url="https://images.invalid/v1/")
    assert instance.provider == "openai"
    assert instance.base_url == "https://images.invalid/v1"
    assert instance._build_url("/v1/images/generations") == (
        "https://images.invalid/v1/images/generations"
    )
    assert instance._build_url("health") == "https://images.invalid/v1/health"
    assert adapter(provider="openai").base_url == "https://api.openai.com/v1"


def test_gpt_image_payload_precedence_and_passthrough():
    instance = adapter(
        default_params={
            "quality": "medium",
            "background": "opaque",
            "output_format": "png",
            "output_compression": 70,
        }
    )

    payload = instance._build_payload(
        ImageGenerationRequest(
            prompt="A lighthouse",
            negative_prompt="fog",
            width=1536,
            height=1024,
            extra_params={
                "quality": "high",
                "background": "transparent",
                "output_format": "webp",
                "output_compression": 85,
                "seed": 999,
                "style": "ignored",
                "user": "customer-1",
            },
        )
    )

    assert payload == {
        "model": "gpt-image-1",
        "prompt": "A lighthouse\n\nAvoid: fog",
        "n": 1,
        "size": "1536x1024",
        "quality": "high",
        "background": "transparent",
        "output_format": "webp",
        "output_compression": 85,
        "user": "customer-1",
    }

    explicit = instance._build_payload(
        ImageGenerationRequest(
            prompt="Square",
            quality="low",
            seed=0,
            extra_params={"quality": "high", "seed": 5},
        )
    )
    assert explicit["quality"] == "low"
    assert explicit["seed"] == 0


def test_dalle_payload_variants_and_size_defaults():
    dalle3 = adapter("dall-e-3", default_params={"style": "natural", "quality": "hd"})
    portrait = dalle3._build_payload(
        ImageGenerationRequest(prompt="Portrait", width=1024, height=1792)
    )
    landscape = dalle3._build_payload(
        ImageGenerationRequest(prompt="Landscape", width=1792, height=1024)
    )

    assert portrait["size"] == "1024x1792"
    assert landscape["size"] == "1792x1024"
    assert portrait["response_format"] == "url"
    assert portrait["style"] == "natural"
    assert portrait["quality"] == "hd"

    plain_dalle3 = adapter("dall-e-3")._build_payload(
        ImageGenerationRequest(prompt="Square")
    )
    assert plain_dalle3["size"] == "1024x1024"
    assert "style" not in plain_dalle3
    assert "quality" not in plain_dalle3
    assert adapter()._get_size(1024, 1536) == "1024x1536"

    dalle2 = adapter("dall-e-2")
    assert (
        dalle2._build_payload(
            ImageGenerationRequest(prompt="Small", width=256, height=1024)
        )["size"]
        == "256x256"
    )
    assert dalle2._get_size(512, 1024) == "512x512"
    assert dalle2._get_size(1024, 1024) == "1024x1024"
    assert dalle2._build_payload(ImageGenerationRequest(prompt="Plain")) == {
        "model": "dall-e-2",
        "prompt": "Plain",
        "n": 1,
        "size": "1024x1024",
        "response_format": "url",
    }


def test_generate_posts_payload_and_parses_response_formats():
    instance = adapter(base_url="https://images.invalid/v1", config={"timeout": 12})
    response = httpx.Response(
        200,
        json={
            "data": [
                {
                    "url": "https://cdn.invalid/image.png",
                    "revised_prompt": "A brighter lighthouse",
                },
                {"b64_json": "YmFzZTY0LTE="},
                {"base64": "YmFzZTY0LTI="},
            ]
        },
    )

    result, client, factory = run_generate(instance, response)

    factory.assert_called_once_with(timeout=12)
    call = client.post.await_args
    assert call.args == ("https://images.invalid/v1/images/generations",)
    assert call.kwargs["headers"]["Authorization"] == "Bearer test-key"
    assert call.kwargs["json"]["prompt"] == "Draw a lighthouse"
    assert result.model == "gpt-image-1"
    assert result.images[0].image.url == "https://cdn.invalid/image.png"
    assert result.images[0].revised_prompt == "A brighter lighthouse"
    assert result.images[1].image.base64 == "YmFzZTY0LTE="
    assert result.images[2].image.base64 == "YmFzZTY0LTI="


@pytest.mark.parametrize(
    ("response", "error_type", "message"),
    [
        (httpx.Response(401), AuthenticationError, None),
        (httpx.Response(429), RateLimitError, None),
        (
            httpx.Response(400, json={"error": {"message": "content_policy"}}),
            ContentFilterError,
            "content_policy",
        ),
        (
            httpx.Response(400, json={"error": {"message": "Safety rejection"}}),
            ContentFilterError,
            "Safety rejection",
        ),
        (httpx.Response(400, json={"error": {}}), InvalidRequestError, None),
        (httpx.Response(503, text="offline"), ProviderError, "Image API error"),
    ],
)
def test_generate_translates_http_errors(response, error_type, message):
    with pytest.raises(error_type, match=message):
        run_generate(adapter(), response)


@pytest.mark.parametrize(
    ("network_error", "message"),
    [
        (httpx.ReadTimeout("slow"), "request_timeout"),
        (httpx.ConnectError("offline"), "Request error: offline"),
    ],
)
def test_generate_translates_network_errors(network_error, message):
    with patch("app.llm.adapters.image.openai.t", side_effect=lambda key: key):
        with pytest.raises(ProviderError, match=message):
            run_generate(adapter(), network_error)
