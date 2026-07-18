from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.api.v1.admin.endpoints import models as models_endpoint

import pytest

from app.api.v1.admin.endpoints.models import test_model_config as run_test_model_config
from app.llm.adapters.chat.moonshot_adapter import MoonshotAdapter
from app.llm.adapters.chat.ollama_adapter import OllamaAdapter
from app.llm.adapters.image.siliconflow import SiliconFlowImageAdapter
from app.schemas.model import ModelProvider, ModelTestRequest, ModelType


@pytest.mark.anyio
async def test_model_config_forwards_default_params_to_chat_test():
    captured: dict[str, object] = {}

    async def fake_test_chat_model(
        provider,
        model_id,
        api_key,
        base_url,
        default_params,
        config,
    ):
        captured.update(
            {
                "provider": provider,
                "model_id": model_id,
                "api_key": api_key,
                "base_url": base_url,
                "default_params": default_params,
                "config": config,
            }
        )

    with patch(
        "app.api.v1.admin.endpoints.models._test_chat_model",
        new=AsyncMock(side_effect=fake_test_chat_model),
    ):
        response = await run_test_model_config(
            ModelTestRequest(
                provider=ModelProvider.DEEPSEEK,
                model_id="deepseek-v4-pro",
                model_type=ModelType.CHAT,
                api_key="test-key",
                base_url="https://api.deepseek.com",
                default_params={
                    "reasoning_effort": "high",
                    "extra_body": {"thinking": {"type": "enabled"}},
                },
                config={"timeout": 30},
            ),
            current_user=SimpleNamespace(),
        )

    assert captured["provider"] == ModelProvider.DEEPSEEK
    assert captured["model_id"] == "deepseek-v4-pro"
    assert captured["default_params"] == {
        "reasoning_effort": "high",
        "extra_body": {"thinking": {"type": "enabled"}},
    }
    assert captured["config"] == {"timeout": 30}
    assert response["data"].success is True


@pytest.mark.anyio
async def test_model_config_accepts_siliconflow_image_models():
    response = await run_test_model_config(
        ModelTestRequest(
            provider=ModelProvider.SILICONFLOW,
            model_id="black-forest-labs/FLUX.1-schnell",
            model_type=ModelType.TEXT_TO_IMAGE,
            api_key="test-key",
            base_url="https://api.siliconflow.cn/v1",
        ),
        current_user=SimpleNamespace(),
    )

    assert response["data"].success is True

    from app.llm.adapters.image import create_image_adapter

    adapter = create_image_adapter(
        SimpleNamespace(
            provider=ModelProvider.SILICONFLOW,
            model_id="black-forest-labs/FLUX.1-schnell",
            api_key="test-key",
            base_url="https://api.siliconflow.cn/v1",
            config={},
            default_params={},
        )
    )
    assert isinstance(adapter, SiliconFlowImageAdapter)


@pytest.mark.anyio
async def test_model_config_routes_siliconflow_image_requests_to_image_validation():
    with patch.object(
        models_endpoint, "_test_image_model", new_callable=AsyncMock
    ) as test_image_model:
        response = await run_test_model_config(
            ModelTestRequest(
                provider=ModelProvider.SILICONFLOW,
                model_id="black-forest-labs/FLUX.1-schnell",
                model_type=ModelType.TEXT_TO_IMAGE,
                api_key="test-key",
                base_url="https://api.siliconflow.cn/v1",
            ),
            current_user=SimpleNamespace(),
        )

    test_image_model.assert_awaited_once_with(
        ModelProvider.SILICONFLOW,
        "black-forest-labs/FLUX.1-schnell",
        "test-key",
        "https://api.siliconflow.cn/v1",
        {},
        {},
    )
    assert response["data"].success is True


@pytest.mark.anyio
async def test_openai_responses_image_validation_generates_a_real_test_image():
    adapter = SimpleNamespace(generate=AsyncMock())

    with patch(
        "app.llm.adapters.image.create_image_adapter", return_value=adapter
    ) as create_adapter:
        await models_endpoint._test_image_model(
            ModelProvider.OPENAI_RESPONSES,
            "gpt-5",
            "test-key",
            "https://api.openai.com/v1",
            {"quality": "low"},
            {"timeout": 30},
        )

    temp_model = create_adapter.call_args.args[0]
    assert temp_model.default_params == {"quality": "low"}
    assert temp_model.config == {"timeout": 30}
    adapter.generate.assert_awaited_once()
    request = adapter.generate.await_args.args[0]
    assert request.prompt == "A simple connection test image"
    assert request.num_images == 1
    assert request.quality == "low"
    assert request.images is None


@pytest.mark.anyio
async def test_model_config_routes_moonshot_chat_requests_to_native_adapter():
    with patch.object(
        MoonshotAdapter,
        "chat",
        new=AsyncMock(return_value=SimpleNamespace(content="ok")),
    ):
        response = await run_test_model_config(
            ModelTestRequest(
                provider=ModelProvider.MOONSHOT,
                model_id="kimi-k2.6",
                model_type=ModelType.CHAT,
                api_key="test-key",
                base_url="https://api.moonshot.cn/v1",
                config={"thinking": {"enabled": True}},
            ),
            current_user=SimpleNamespace(),
        )

    assert response["data"].success is True


@pytest.mark.anyio
async def test_model_config_routes_ollama_chat_requests_without_api_key():
    with patch.object(
        OllamaAdapter, "chat", new=AsyncMock(return_value=SimpleNamespace(content="ok"))
    ):
        response = await run_test_model_config(
            ModelTestRequest(
                provider=ModelProvider.OLLAMA,
                model_id="qwen3",
                model_type=ModelType.CHAT,
                api_key=None,
                base_url="http://localhost:11434/v1",
                config={"thinking": {"enabled": True}},
            ),
            current_user=SimpleNamespace(),
        )

    assert response["data"].success is True
