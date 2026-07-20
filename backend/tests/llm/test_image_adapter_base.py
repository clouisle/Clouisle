from types import SimpleNamespace

import pytest

from app.llm.adapters import image
from app.llm.adapters.image.base import BaseImageAdapter
from app.llm.errors import InvalidRequestError, UnsupportedOperationError
from app.llm.types import ImageGenerationRequest, ImageGenerationResponse


class ImageAdapter(BaseImageAdapter):
    def __init__(self, model_config: object) -> None:
        self.model_config = model_config

    async def generate(
        self, request: ImageGenerationRequest
    ) -> ImageGenerationResponse:
        raise NotImplementedError


def test_image_adapter_base_requires_generate_implementation() -> None:
    with pytest.raises(TypeError, match="abstract method"):
        BaseImageAdapter()


def test_image_adapter_resolves_request_params_in_precedence_order() -> None:
    adapter = ImageAdapter(
        SimpleNamespace(default_params={"style": "default", "quality": "hd"})
    )

    assert adapter._get_effective_param(
        ImageGenerationRequest(
            prompt="test", style="request", extra_params={"style": "extra"}
        ),
        field_name="style",
        param_key="style",
    ) == "request"
    assert adapter._get_effective_param(
        ImageGenerationRequest(prompt="test", extra_params={"style": "extra"}),
        field_name="style",
        param_key="style",
    ) == "extra"
    assert adapter._get_effective_param(
        ImageGenerationRequest(prompt="test"),
        field_name="quality",
        param_key="quality",
        fallback="standard",
    ) == "hd"
    assert adapter._get_effective_param(
        ImageGenerationRequest(prompt="test", style=""),
        field_name="style",
        param_key="style",
        fallback="natural",
    ) == "default"


def test_image_adapter_merges_extra_params_and_filters_empty_values() -> None:
    adapter = ImageAdapter(
        SimpleNamespace(default_params={"seed": 1, "style": "", "ignored": "value"})
    )
    request = ImageGenerationRequest(
        prompt="test", extra_params={"seed": 2, "quality": "hd", "style": None}
    )

    assert adapter._get_effective_extra_params(request) == {
        "seed": 2,
        "style": None,
        "ignored": "value",
        "quality": "hd",
    }
    assert adapter._get_effective_extra_params(
        request, include_keys={"seed", "style", "quality"}
    ) == {"seed": 2, "quality": "hd"}


@pytest.mark.parametrize("timeout", ["invalid", 0, -1, float("nan"), float("inf")])
def test_image_adapter_rejects_invalid_request_timeout(timeout: object) -> None:
    adapter = ImageAdapter(SimpleNamespace(config={"timeout": timeout}))

    with pytest.raises(InvalidRequestError) as exc_info:
        adapter._get_request_timeout()

    assert exc_info.value.field == "timeout"


def test_image_adapter_uses_valid_or_default_request_timeout() -> None:
    assert ImageAdapter(SimpleNamespace(config={"timeout": "12.5"}))._get_request_timeout() == 12.5
    assert ImageAdapter(SimpleNamespace(config=None))._get_request_timeout() == 300


def test_image_factory_rejects_unsupported_provider() -> None:
    with pytest.raises(UnsupportedOperationError) as exc_info:
        image.create_image_adapter(SimpleNamespace(provider="unsupported"))

    assert exc_info.value.operation == "generate_image"
    assert exc_info.value.provider == "unsupported"
