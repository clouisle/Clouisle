from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.api.v1.admin.endpoints.models import test_model_config as run_test_model_config
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
