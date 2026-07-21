import asyncio
import base64
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.llm.adapters.image.stability import StabilityImageAdapter
from app.llm.errors import (
    AuthenticationError,
    ContentFilterError,
    InvalidRequestError,
    ProviderError,
    RateLimitError,
)
from app.llm.types import ImageGenerationRequest


def build_adapter(
    model_id="sd3.5-large",
    *,
    base_url="https://api.stability.ai/v1/",
    provider="stability",
    config=None,
    default_params=None,
):
    return StabilityImageAdapter(
        SimpleNamespace(
            provider=provider,
            model_id=model_id,
            api_key="fake-key",
            base_url=base_url,
            config=config or {},
            default_params=default_params or {},
        )
    )


def response(status=200, *, content=b"", headers=None, json=None, text=None):
    request = httpx.Request("POST", "https://api.stability.ai/fake")
    if json is not None:
        return httpx.Response(status, json=json, headers=headers, request=request)
    return httpx.Response(
        status,
        content=content if text is None else text.encode(),
        headers=headers,
        request=request,
    )


class FakeAsyncClient:
    instances = []
    responses = []

    def __init__(self, *, timeout):
        self.timeout = timeout
        self.post = AsyncMock(side_effect=self.responses)
        self.instances.append(self)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None


def test_generate_posts_each_image_and_parses_binary_responses():
    adapter = build_adapter(model_id="stable-image-core", config={"timeout": 12})
    FakeAsyncClient.instances = []
    FakeAsyncClient.responses = [
        response(
            200, content=b"first", headers={"content-type": "image/jpeg", "seed": "7"}
        ),
        response(
            200,
            content=b"second",
            headers={"content-type": "image/webp", "x-seed": "8"},
        ),
    ]

    with patch("app.llm.adapters.image.stability.httpx.AsyncClient", FakeAsyncClient):
        result = asyncio.run(
            adapter.generate(
                ImageGenerationRequest(
                    prompt="fake prompt",
                    negative_prompt="fake negative prompt",
                    num_images=2,
                    quality="jpeg",
                    seed=7,
                )
            )
        )

    client = FakeAsyncClient.instances[0]
    assert client.timeout == 12
    assert client.post.await_count == 2
    assert result.model == "stable-image-core"
    assert [image.image.base64 for image in result.images] == [
        base64.b64encode(b"first").decode(),
        base64.b64encode(b"second").decode(),
    ]
    assert [image.image.format for image in result.images] == ["jpeg", "webp"]
    assert [image.seed for image in result.images] == [7, 8]
    first_call, second_call = client.post.await_args_list
    assert first_call.args == (
        "https://api.stability.ai/v2beta/stable-image/generate/core",
    )
    assert first_call.kwargs["headers"] == {
        "Authorization": "Bearer fake-key",
        "Accept": "image/*",
    }
    assert first_call.kwargs["files"] == {"none": ("", b"")}
    assert first_call.kwargs["data"]["seed"] == 7
    assert second_call.kwargs["data"]["seed"] == 8


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (httpx.TimeoutException("late"), None),
        (httpx.RequestError("offline"), "Request error: offline"),
    ],
)
def test_submit_generation_translates_transport_errors(error, message):
    adapter = build_adapter()
    client = SimpleNamespace(post=AsyncMock(side_effect=error))

    with pytest.raises(ProviderError) as caught:
        asyncio.run(
            adapter._submit_generation(client=client, payload={"prompt": "fake"})
        )

    if message:
        assert message in str(caught.value)


@pytest.mark.parametrize(
    ("model_id", "path"),
    [
        ("STABLE-IMAGE-ULTRA", "/v2beta/stable-image/generate/ultra"),
        ("stable-image-core", "/v2beta/stable-image/generate/core"),
        ("sd3.5-large", "/v2beta/stable-image/generate/sd3"),
    ],
)
def test_model_paths_and_url_normalization(model_id, path):
    adapter = build_adapter(model_id=model_id, base_url="https://fake.example")

    assert adapter._build_path() == path
    assert adapter._build_url(path.removeprefix("/")) == f"https://fake.example{path}"


def test_provider_value_default_url_and_form_payload_branches():
    provider = SimpleNamespace(value="stability-enum")
    adapter = build_adapter(
        provider=provider,
        base_url=None,
        default_params={"style_preset": "cinematic"},
    )
    request = ImageGenerationRequest.model_construct(
        prompt="fake",
        negative_prompt=None,
        width=0,
        height=0,
        num_images=1,
        style=None,
        quality=None,
        seed=-1,
        images=None,
        extra_params={
            "style_preset": "ignored",
            "output_format": "ignored",
            "seed": 99,
            "aspect_ratio": "ignored",
            "model": "ignored",
            "cfg_scale": 5,
        },
    )

    payload = adapter._build_form_data(request, output_format="png", seed_offset=3)

    assert adapter.provider == "stability-enum"
    assert adapter.base_url == "https://api.stability.ai"
    assert payload == {
        "prompt": "fake",
        "output_format": "png",
        "style_preset": "ignored",
        "model": "sd3.5-large",
        "cfg_scale": 5,
    }


@pytest.mark.parametrize(
    ("data", "expected_image", "expected_seed"),
    [
        ({"image": "one", "seed": 1}, "one", 1),
        ({"base64": "two"}, "two", None),
        ({"b64_json": "three"}, "three", None),
        ({"artifacts": [None, {"base64": "four", "seed": 4}]}, "four", 4),
        ({"artifacts": [{"b64_json": "five"}]}, "five", None),
    ],
)
def test_parse_json_response_shapes(data, expected_image, expected_seed):
    image = build_adapter()._parse_response(
        response(200, json=data, headers={"content-type": "application/json"}),
        output_format="png",
    )

    assert image.image.base64 == expected_image
    assert image.image.format == "png"
    assert image.seed == expected_seed


@pytest.mark.parametrize(
    "provider_response",
    [
        response(200, json={}, headers={"content-type": "application/json"}),
        response(200),
    ],
)
def test_parse_response_rejects_missing_image(provider_response):
    with pytest.raises(ProviderError):
        build_adapter()._parse_response(provider_response, output_format="png")


@pytest.mark.parametrize(
    ("status", "body", "error_type", "message"),
    [
        (401, {"message": " bad key "}, AuthenticationError, "bad key"),
        (403, {}, ContentFilterError, None),
        (429, {"error": "slow down"}, RateLimitError, "slow down"),
        (400, {"detail": "bad input"}, InvalidRequestError, "bad input"),
        (413, {"name": "too large"}, InvalidRequestError, "too large"),
        (
            422,
            {"errors": [{"message": "first"}, {"detail": "second"}, "third"]},
            InvalidRequestError,
            "first; second; third",
        ),
        (500, {}, ProviderError, None),
    ],
)
def test_status_errors(status, body, error_type, message):
    adapter = build_adapter()

    with pytest.raises(error_type) as caught:
        adapter._raise_for_status(response(status, json=body))

    if message:
        assert message in str(caught.value)
    if status == 500:
        assert caught.value.status_code == 500


def test_success_status_and_error_message_fallback_shapes():
    adapter = build_adapter()
    adapter._raise_for_status(response(200))

    assert (
        adapter._extract_error_message(response(500, text=" plain failure "))
        == "plain failure"
    )
    assert (
        adapter._extract_error_message(
            response(500, json={"errors": [{"code": "x"}], "message": "unused"})
        )
        == "{'code': 'x'}"
    )
    assert adapter._extract_error_message(response(500, json=[])) == "[]"
    assert (
        adapter._extract_error_message(
            response(500, json={"errors": [], "message": "fallback"})
        )
        == "fallback"
    )
    assert (
        adapter._extract_error_message(response(500, json={"message": "  "}))
        == '{"message":"  "}'
    )


def test_extractors_handle_invalid_values_and_headers():
    adapter = build_adapter()

    assert adapter._extract_base64_image({"image": 3, "artifacts": "bad"}) is None
    assert adapter._extract_base64_image({"artifacts": [{"base64": ""}, "bad"]}) is None
    assert (
        adapter._extract_seed({"seed": "3", "artifacts": [{"seed": "4"}, None]}) is None
    )
    assert adapter._extract_seed(httpx.Headers({"seed": "bad", "x-seed": "12"})) == 12
    assert adapter._extract_seed(httpx.Headers({"seed": "", "x-seed": "bad"})) is None
    assert adapter._extract_seed("bad") is None


@pytest.mark.parametrize(
    ("image_request", "expected"),
    [
        (
            ImageGenerationRequest(
                prompt="fake", extra_params={"output_format": "webp"}
            ),
            "webp",
        ),
        (ImageGenerationRequest(prompt="fake", quality="jpeg"), "jpeg"),
        (ImageGenerationRequest(prompt="fake", quality="high"), "png"),
        (
            ImageGenerationRequest(prompt="fake", extra_params={"output_format": 3}),
            "png",
        ),
    ],
)
def test_output_format_precedence(image_request, expected):
    assert build_adapter()._get_output_format(image_request) == expected


@pytest.mark.parametrize(
    ("content_type", "expected"),
    [
        ("image/jpeg", "jpeg"),
        ("image/webp", "webp"),
        ("image/png", "png"),
        ("application/octet-stream", "fallback"),
    ],
)
def test_infer_output_format(content_type, expected):
    assert build_adapter()._infer_output_format(content_type, "fallback") == expected


def test_closest_aspect_ratio():
    adapter = build_adapter()

    assert adapter._closest_aspect_ratio(1600, 900) == "16:9"
    assert adapter._closest_aspect_ratio(900, 1600) == "9:16"
