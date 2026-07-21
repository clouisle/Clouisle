from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.llm.adapters.image.runway import RunwayImageAdapter
from app.llm.errors import InvalidRequestError, ProviderError
from app.llm.types import ImageGenerationRequest


def model():
    return SimpleNamespace(
        provider="runway",
        model_id="gen4_image",
        api_key="fake-key",
        base_url="https://runway.invalid",
        config={},
        default_params={},
    )


@pytest.fixture
def adapter_and_client():
    client = SimpleNamespace(create_task=AsyncMock(), wait_for_task=AsyncMock())
    with patch(
        "app.llm.adapters.image.runway.RunwayClient", return_value=client
    ) as client_class:
        adapter = RunwayImageAdapter(model())
    client_class.assert_called_once_with(adapter.model_config)
    return adapter, client


@pytest.mark.asyncio
async def test_generate_creates_and_collects_each_requested_image(adapter_and_client):
    adapter, client = adapter_and_client
    client.create_task.side_effect = [{"id": "task-1"}, {"id": 22}]
    client.wait_for_task.side_effect = [
        {"status": "succeeded", "output": ["https://example.test/one.png"]},
        {"status": "SUCCEEDED", "output": [{"uri": "https://example.test/two.png"}]},
    ]

    response = await adapter.generate(
        ImageGenerationRequest(prompt="A lighthouse", num_images=2, seed=10)
    )

    assert response.model == "gen4_image"
    assert [image.image.url for image in response.images] == [
        "https://example.test/one.png",
        "https://example.test/two.png",
    ]
    assert [call.args[0] for call in client.wait_for_task.await_args_list] == [
        "task-1",
        "22",
    ]
    assert [call.args[1]["seed"] for call in client.create_task.await_args_list] == [
        10,
        11,
    ]


@pytest.mark.asyncio
async def test_create_task_builds_directives_ratio_and_extra_params(adapter_and_client):
    adapter, client = adapter_and_client
    client.create_task.return_value = {"id": "task"}
    request = ImageGenerationRequest(
        prompt="A skyline",
        negative_prompt="blurry",
        width=1536,
        height=1024,
        style="cinematic",
        extra_params={"guidanceScale": 6.5, "ratio": "custom"},
    )

    assert await adapter._create_task(request, 0) == "task"

    path, payload = client.create_task.await_args.args
    assert path == "/v1/text_to_image"
    assert payload == {
        "model": "gen4_image",
        "promptText": "A skyline\n\nStyle: cinematic\nAvoid: blurry",
        "ratio": "custom",
        "guidanceScale": 6.5,
    }


@pytest.mark.asyncio
async def test_create_task_uses_fallback_ratio_and_requires_id(adapter_and_client):
    adapter, client = adapter_and_client
    client.create_task.return_value = {}

    with (
        patch(
            "app.llm.adapters.image.runway.closest_aspect_ratio",
            return_value="unsupported",
        ),
        pytest.raises(ProviderError) as exc_info,
    ):
        await adapter._create_task(ImageGenerationRequest(prompt="Plain"), 0)

    assert exc_info.value.provider == "runway"
    assert client.create_task.await_args.args[1]["ratio"] == "1080:1080"
    assert "seed" not in client.create_task.await_args.args[1]


@pytest.mark.parametrize(
    ("task", "message"),
    [
        ({"status": "FAILED", "failure": "unsafe"}, "unsafe"),
        ({"status": "failed", "error": "offline"}, "offline"),
        ({"status": "pending"}, "Runway image task failed"),
    ],
)
def test_parse_images_rejects_unsuccessful_tasks(adapter_and_client, task, message):
    adapter, _ = adapter_and_client

    with pytest.raises(ProviderError, match=message) as exc_info:
        adapter._parse_images(task)

    assert exc_info.value.model == "gen4_image"


def test_parse_images_accepts_all_list_output_shapes(adapter_and_client):
    adapter, _ = adapter_and_client

    images = adapter._parse_images(
        {
            "status": "SUCCEEDED",
            "output": [
                "https://example.test/a.png",
                {"url": "https://example.test/b.png"},
                {"uri": "https://example.test/c.png"},
                {"url": 123},
                None,
            ],
        }
    )

    assert [image.image.url for image in images] == [
        "https://example.test/a.png",
        "https://example.test/b.png",
        "https://example.test/c.png",
    ]
    assert all(image.image.format == "png" for image in images)


@pytest.mark.parametrize("key", ["images", "output"])
def test_parse_images_accepts_nested_dictionary_outputs(adapter_and_client, key):
    adapter, _ = adapter_and_client

    images = adapter._parse_images(
        {
            "status": "SUCCEEDED",
            "output": {
                key: [
                    "https://example.test/a.png",
                    {"url": "https://example.test/b.png"},
                    {"uri": "https://example.test/c.png"},
                    {"uri": 123},
                    Mock(),
                ]
            },
        }
    )

    assert [image.image.url for image in images] == [
        "https://example.test/a.png",
        "https://example.test/b.png",
        "https://example.test/c.png",
    ]


@pytest.mark.parametrize(
    "output",
    [None, [], "not-a-collection", {"images": "not-a-list"}, {"output": []}],
)
def test_parse_images_rejects_missing_urls(adapter_and_client, output):
    adapter, _ = adapter_and_client

    with pytest.raises(InvalidRequestError) as exc_info:
        adapter._parse_images({"status": "SUCCEEDED", "output": output})

    assert exc_info.value.provider == "runway"
