"""Upgrade preserves active personal use without granting additional functions."""

import pytest

from app.core.integration_migration import initialize_integrations
from app.integrations.credentials import encrypt_secret
from app.models.integration import Integration
from app.models.user import User
from app.models.wechat_knowledge import WeChatKnowledgeBinding
import pytest_asyncio
from tortoise.context import TortoiseContext


@pytest_asyncio.fixture
async def database():
    async with TortoiseContext() as context:
        await context.init(
            db_url="sqlite://:memory:", modules={"models": ["app.models"]}
        )
        await context.generate_schemas()
        yield


@pytest.mark.asyncio
async def test_existing_personal_use_is_preserved_once_and_later_admin_selection_wins(
    database,
):
    user = await User.create(
        username="wechat-migration",
        email="migration@example.test",
        hashed_password="unused",
    )
    binding = await WeChatKnowledgeBinding.create(
        user=user,
        wechat_user_id="wx_legacy",
        bot_id="bot",
        token=encrypt_secret("legacy"),
        base_url="https://ilinkai.weixin.qq.com",
        purpose="agent",
    )
    await initialize_integrations()
    integration = await Integration.get(provider_type="wechat")
    assert integration.enabled_capabilities == ["agent_chat"]
    assert (await WeChatKnowledgeBinding.get(id=binding.id)).token == binding.token
    await Integration.filter(id=integration.id).update(enabled_capabilities=[])
    await initialize_integrations()
    assert (await Integration.get(id=integration.id)).enabled_capabilities == []
    assert (await WeChatKnowledgeBinding.get(id=binding.id)).purpose == "agent"
