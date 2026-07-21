from types import SimpleNamespace
from unittest.mock import AsyncMock, call

import pytest

from app.llm.adapters.image.luma import LumaImageAdapter
from app.llm.errors import InvalidRequestError, ProviderError
from app.llm.types import ImageGenerationRequest


def adapter() -> LumaImageAdapter:
    instance = LumaImageAdapter(
        SimpleNamespace(
            model_id="photon-1",
            api_key="fake-key",
            base_url="https://luma.invalid",
            config={},
        )
    )
    instance.client = SimpleNamespace(
        create_generation=AsyncMock(side_effect=[{"id": "task-1"}, {"id": 2}]),
        wait_for_generation=AsyncMock(
            side_effect=[
                {
                    "state": "completed",
                    "assets": {"image": "https://images.invalid/one.png"},
                },
                {
                    "state": "COMPLETED",
                    "assets": {"image": "https://images.invalid/two.png"},
                },
            ]
        ),
    )
    return instance


@pytest.mark.asyncio
async def test_generate_sends_payload_and_parses_completed_tasks() -> None:
    instance = adapter()

    result = await instance.generate(
        ImageGenerationRequest(
            prompt="A lighthouse",
            negative_prompt="fog",
            width=1024,
            height=1792,
            num_images=2,
            style="cinematic",
            seed=17,
            extra_params={"guidance_scale": 6},
        )
    )

    payload = {
        "model": "photon-1",
        "prompt": "A lighthouse\n\nStyle: cinematic\nAvoid: fog",
        "aspect_ratio": "9:16",
        "seed": 17,
        "guidance_scale": 6,
    }
    assert instance.client.create_generation.await_args_list == [
        call("/generations/image", payload),
        call("/generations/image", payload),
    ]
    assert instance.client.wait_for_generation.await_args_list == [
        call("task-1"),
        call("2"),
    ]
    assert result.model == "photon-1"
    assert [image.image.url for image in result.images] == [
        "https://images.invalid/one.png",
        "https://images.invalid/two.png",
    ]
    assert all(image.image.format == "png" for image in result.images)


@pytest.mark.asyncio
async def test_create_generation_requires_task_id_with_minimal_payload() -> None:
    instance = adapter()
    instance.client.create_generation = AsyncMock(return_value={})

    with pytest.raises(ProviderError) as exc_info:
        await instance._create_generation(ImageGenerationRequest(prompt="A lighthouse"))

    _, payload = instance.client.create_generation.await_args.args
    assert payload == {
        "model": "photon-1",
        "prompt": "A lighthouse",
        "aspect_ratio": "1:1",
    }
    assert exc_info.value.provider == "luma"
    assert exc_info.value.model == "photon-1"


@pytest.mark.parametrize(
    ("generation", "message"),
    [
        ({"state": "failed", "failure_reason": "content rejected"}, "content rejected"),
        (
            {"state": "cancelled", "error": {"message": "cancelled"}},
            "{'message': 'cancelled'}",
        ),
        ({"state": "processing"}, "Luma image generation failed"),
    ],
)
def test_parse_image_rejects_unsuccessful_statuses(
    generation: dict, message: str
) -> None:
    instance = adapter()

    with pytest.raises(ProviderError, match=message) as exc_info:
        instance._parse_image(generation)

    assert exc_info.value.provider == "luma"
    assert exc_info.value.model == "photon-1"


def test_parse_image_requires_completed_asset() -> None:
    instance = adapter()

    with pytest.raises(InvalidRequestError) as exc_info:
        instance._parse_image({"state": "completed", "assets": None})

    assert exc_info.value.provider == "luma"
    assert exc_info.value.model == "photon-1"
