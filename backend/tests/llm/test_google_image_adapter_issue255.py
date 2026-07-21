import asyncio
import base64
from enum import Enum
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from app.llm.adapters.image.google import GoogleImageAdapter
from app.llm.errors import ContentFilterError, InvalidRequestError, ProviderError
from app.llm.types import ImageContent, ImageGenerationRequest


class Provider(Enum):
    GOOGLE = "google"


def model(model_id="gemini-3-pro-image-preview", **kwargs):
    return SimpleNamespace(
        provider=kwargs.pop("provider", Provider.GOOGLE),
        model_id=model_id,
        api_key="fake-key",
        base_url="https://google.invalid",
        config=kwargs.pop("config", {}),
        default_params=kwargs.pop("default_params", {}),
        **kwargs,
    )


def adapter(model_id="gemini-3-pro-image-preview", **kwargs):
    return GoogleImageAdapter(model(model_id, **kwargs))


@pytest.fixture(autouse=True)
def fake_google_sdk(monkeypatch):
    part = SimpleNamespace(
        from_bytes=lambda **kwargs: kwargs,
        from_uri=lambda **kwargs: kwargs,
    )
    types = SimpleNamespace(
        Part=part,
        HttpOptions=lambda **kwargs: SimpleNamespace(**kwargs),
    )
    genai = SimpleNamespace(types=types, Client=None)
    monkeypatch.setitem(
        __import__("sys").modules, "google", SimpleNamespace(genai=genai)
    )
    monkeypatch.setitem(__import__("sys").modules, "google.genai", genai)
    return genai


def response_with_image(data=b"image", mime_type="image/png", text=" revised "):
    return SimpleNamespace(
        candidates=[
            SimpleNamespace(
                finish_reason="STOP",
                content=SimpleNamespace(
                    parts=[
                        SimpleNamespace(text=text, inline_data=None),
                        SimpleNamespace(
                            text=None,
                            inline_data=SimpleNamespace(data=data, mime_type=mime_type),
                        ),
                    ]
                ),
            )
        ]
    )


def test_init_and_split_reference_image_variants():
    google = adapter(provider="google")
    assert google.provider == "google"

    request = ImageGenerationRequest(
        prompt="edit",
        extra_params={
            "image": ImageContent(base64="aW1hZ2U="),
            "images": {"url": "gs://bucket/image.png"},
            "reference_images": [{"url": "data:image/png;base64,aW1hZ2U="}],
            "temperature": 0.2,
        },
    )
    images, overrides = google._split_extra_params(request)
    assert len(images) == 3
    assert overrides == {"temperature": 0.2}

    explicit = ImageContent(url="gs://bucket/explicit.png")
    images, overrides = google._split_extra_params(
        ImageGenerationRequest(
            prompt="edit",
            images=[explicit],
            extra_params={"images": [{"url": "gs://bucket/legacy.png"}]},
        )
    )
    assert images == [explicit]
    assert overrides == {}
    assert google._split_extra_params(ImageGenerationRequest(prompt="plain")) == (
        [],
        {},
    )


def test_split_rejects_unsupported_reference_payload():
    with pytest.raises(InvalidRequestError, match="Unsupported Google reference"):
        adapter()._split_extra_params(
            ImageGenerationRequest(prompt="edit", extra_params={"image": 42})
        )


def test_generation_config_covers_overrides_and_inference():
    google = adapter()
    config = google._build_generation_config(
        ImageGenerationRequest(prompt="draw", width=1200, height=1200, seed=4),
        seed_offset=2,
        overrides={
            "response_modalities": ["modality.image"],
            "image_config": {"aspect_ratio": "9:16"},
            "image_size": "4K",
            "temperature": 0.4,
        },
    )
    assert config == {
        "response_modalities": ["TEXT", "IMAGE"],
        "seed": 6,
        "image_config": {"aspect_ratio": "9:16", "image_size": "4K"},
        "temperature": 0.4,
    }

    old_model = adapter("gemini-2.5-flash-image")
    config = old_model._build_generation_config(
        ImageGenerationRequest(prompt="draw", extra_params={"aspect_ratio": "3:2"}),
        seed_offset=0,
        overrides={"aspect_ratio": "3:2", "image_config": "ignored"},
    )
    assert config == {
        "response_modalities": ["TEXT", "IMAGE"],
        "image_config": {"aspect_ratio": "3:2"},
    }


@pytest.mark.parametrize(
    ("dimensions", "expected"),
    [((1024, 768), "1K"), ((2048, 1024), "2K"), ((4096, 2048), "4K")],
)
def test_image_size_boundaries_and_aspect_ratio(dimensions, expected):
    google = adapter()
    assert google._infer_image_size(*dimensions) == expected
    assert (
        google._build_image_config(
            ImageGenerationRequest(
                prompt="draw", width=dimensions[0], height=dimensions[1]
            ),
            {},
        )["image_size"]
        == expected
    )
    assert google._closest_aspect_ratio(1600, 900) == "16:9"
    assert google._supports_image_size()
    assert not adapter("gemini-2.5-flash-image")._supports_image_size()


def test_response_modalities_defaults_and_missing_image():
    google = adapter()
    assert google._normalize_response_modalities(None) == ["TEXT", "IMAGE"]
    assert google._normalize_response_modalities(["text"]) == ["TEXT", "IMAGE"]


def test_build_contents_and_all_inline_part_sources(
    monkeypatch, tmp_path, fake_google_sdk
):
    calls = []
    monkeypatch.setattr(
        fake_google_sdk.types.Part,
        "from_bytes",
        staticmethod(lambda **kwargs: calls.append(("bytes", kwargs)) or kwargs),
    )
    monkeypatch.setattr(
        fake_google_sdk.types.Part,
        "from_uri",
        staticmethod(lambda **kwargs: calls.append(("uri", kwargs)) or kwargs),
    )
    path = tmp_path / "reference.jpg"
    path.write_bytes(b"file-bytes")
    google = adapter()

    contents = asyncio.run(
        google._build_contents(
            ImageGenerationRequest(
                prompt="portrait", style="natural", negative_prompt="blur"
            ),
            [
                ImageContent(base64=base64.b64encode(b"raw").decode(), format="webp"),
                ImageContent(file_path=str(path)),
                ImageContent(url="data:image/gif;base64,Z2lm"),
                ImageContent(url="gs://bucket/image.jpg"),
            ],
        )
    )

    assert contents[0] == "portrait\n\nStyle: natural\nAvoid: blur"
    assert calls == [
        ("bytes", {"data": b"raw", "mime_type": "image/webp"}),
        ("bytes", {"data": b"file-bytes", "mime_type": "image/jpeg"}),
        ("bytes", {"data": b"gif", "mime_type": "image/gif"}),
        ("uri", {"file_uri": "gs://bucket/image.jpg", "mime_type": "image/jpeg"}),
    ]


def test_remote_part_uses_mocked_fetch(monkeypatch, fake_google_sdk):
    google = adapter()
    monkeypatch.setattr(
        google, "_fetch_remote_image", AsyncMock(return_value=(b"remote", "image/avif"))
    )
    monkeypatch.setattr(
        fake_google_sdk.types.Part, "from_bytes", staticmethod(lambda **kwargs: kwargs)
    )

    part = asyncio.run(
        google._image_to_google_part(ImageContent(url="https://fake.invalid/image"))
    )
    assert part == {"data": b"remote", "mime_type": "image/avif"}


def test_missing_image_source_is_rejected():
    with pytest.raises(InvalidRequestError):
        asyncio.run(adapter()._image_to_google_part(ImageContent()))


class FakeAsyncClient:
    response = None
    error = None

    def __init__(self, **kwargs):
        assert kwargs == {"timeout": 30.0}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def get(self, url):
        assert url == "https://fake.invalid/reference"
        if self.error:
            raise self.error
        return self.response


def test_fetch_remote_image_success_and_content_type_fallback(monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    response = SimpleNamespace(
        content=b"remote", headers={"content-type": "image/webp; charset=binary"}
    )
    response.raise_for_status = lambda: None
    FakeAsyncClient.response = response
    FakeAsyncClient.error = None
    assert asyncio.run(
        adapter()._fetch_remote_image("https://fake.invalid/reference", "image/png")
    ) == (b"remote", "image/webp")

    response.headers = {"content-type": ""}
    assert asyncio.run(
        adapter()._fetch_remote_image("https://fake.invalid/reference", "image/png")
    ) == (b"remote", "image/png")


def test_fetch_remote_image_wraps_http_errors(monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    FakeAsyncClient.error = httpx.ConnectError("offline")
    with pytest.raises(ProviderError, match="offline"):
        asyncio.run(
            adapter()._fetch_remote_image("https://fake.invalid/reference", "image/png")
        )
    FakeAsyncClient.error = None


def test_base64_data_uri_and_mime_helpers():
    google = adapter()
    assert google._decode_base64("aW1hZ2U=") == b"image"
    assert google._decode_base64("data:;base64,aW1hZ2U=") == b"image"
    assert google._parse_data_uri("data:;base64,aW1hZ2U=") == ("image/png", b"image")
    assert google._guess_mime_type(ImageContent(format="jpg")) == "image/jpeg"
    assert google._guess_mime_type(ImageContent(format="png")) == "image/png"
    assert google._mime_to_format("image/jpeg; charset=binary") == "jpeg"
    assert google._mime_to_format("image/webp") == "webp"
    assert google._mime_to_format("image/gif") == "png"


def test_parse_generated_images_handles_encoded_data_and_ignores_non_images():
    google = adapter()
    encoded = base64.b64encode(b"webp")
    response = SimpleNamespace(
        candidates=[
            SimpleNamespace(content=None, finish_reason="STOP"),
            SimpleNamespace(
                finish_reason="STOP",
                content=SimpleNamespace(
                    parts=[
                        SimpleNamespace(text=" ", inline_data=None),
                        SimpleNamespace(
                            text=None,
                            inline_data=SimpleNamespace(
                                data=b"text", mime_type="text/plain"
                            ),
                        ),
                        SimpleNamespace(
                            text=" final ",
                            inline_data=SimpleNamespace(
                                data=encoded.decode(), mime_type="image/webp"
                            ),
                        ),
                    ]
                ),
            ),
        ]
    )
    images = google._parse_generated_images(response, fallback_seed=None)
    assert images[0].image.base64 == encoded.decode()
    assert images[0].image.format == "webp"
    assert images[0].revised_prompt == "final"


@pytest.mark.parametrize("finish_reason", ["SAFETY", "IMAGE_BLOCKED"])
def test_parse_generated_images_reports_candidate_safety(finish_reason):
    response = SimpleNamespace(
        candidates=[
            SimpleNamespace(
                finish_reason=finish_reason, content=SimpleNamespace(parts=[])
            )
        ]
    )
    with pytest.raises(ContentFilterError):
        adapter()._parse_generated_images(response, fallback_seed=None)


def test_parse_generated_images_reports_feedback_and_empty_output():
    google = adapter()
    with pytest.raises(ContentFilterError, match="PROHIBITED"):
        google._parse_generated_images(
            SimpleNamespace(
                candidates=[],
                prompt_feedback=SimpleNamespace(block_reason="PROHIBITED"),
            ),
            fallback_seed=None,
        )
    with pytest.raises(InvalidRequestError):
        google._parse_generated_images(
            SimpleNamespace(
                candidates=[], prompt_feedback=SimpleNamespace(block_reason=None)
            ),
            fallback_seed=None,
        )


def test_generate_uses_mock_client_and_stops_when_enough_images(
    monkeypatch, fake_google_sdk
):
    generate_content = AsyncMock(
        return_value=SimpleNamespace(
            candidates=[
                response_with_image(b"one").candidates[0],
                response_with_image(b"two").candidates[0],
            ]
        )
    )
    fake_client = SimpleNamespace(
        aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
    )

    def client_factory(**kwargs):
        assert kwargs["api_key"] == "fake-key"
        assert kwargs["http_options"].timeout == 12500
        return fake_client

    fake_google_sdk.Client = client_factory

    result = asyncio.run(
        adapter(config={"timeout": 12.5}).generate(
            ImageGenerationRequest(prompt="draw", num_images=2, seed=10)
        )
    )

    assert result.model == "gemini-3-pro-image-preview"
    assert len(result.images) == 2
    assert all(image.seed == 10 for image in result.images)
    assert generate_content.await_count == 1
    call = generate_content.await_args
    assert call.kwargs["model"] == "gemini-3-pro-image-preview"
    assert call.kwargs["contents"] == ["draw"]
    assert call.kwargs["config"]["seed"] == 10
