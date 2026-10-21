"""Owner isolation, web/bot switching and upgrade invariants on real ORM."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from tests.services.test_feishu_agent_runtime import make_agent, receipt_for
from app.api.v1.endpoints import feishu_agent_settings as settings
from app.core.feishu_agent_migration import migrate_feishu_agent_selection
from app.models.agent import Agent, AgentVisibility
from app.models.feishu_agent import (
    FeishuAgentPreference,
    FeishuAgentReceipt,
    FeishuAgentSession,
)
from app.models.feishu_user import FeishuUser
from app.models.user import User
from app.schemas.response import BusinessError
from app.services import feishu_agent_runtime as runtime
from app.services.feishu_agent_preferences import available_agents
from tortoise import connections

pytest_plugins = ["tests.services.test_feishu_agent_runtime"]


@pytest.mark.asyncio
async def test_web_selection_is_owner_scoped_and_keeps_accepted_messages(
    world, monkeypatch
):
    monkeypatch.setattr(settings.AuditLogService, "log", AsyncMock())
    second = await make_agent(world.team, world.user, "Second")
    other = await User.create(
        username="another", email="another@example.test", hashed_password="unused"
    )
    await FeishuUser.create(user=other, feishu_user_id="other_sender")
    await FeishuAgentPreference.create(
        integration=world.integration, user=other, agent=world.agent
    )
    before = await receipt_for(world)
    result = await settings.update_config(
        settings.PreferenceInput(agent_id=second.id), MagicMock(), world.user
    )
    assert result["data"]["agent_id"] == str(second.id)
    after = await receipt_for(world)
    assert (await FeishuAgentReceipt.get(id=before.id)).agent_id == world.agent.id
    assert after.agent_id == second.id
    assert (await FeishuAgentPreference.get(user=other)).agent_id == world.agent.id
    await runtime.process_message(str(before.id))
    assert world.submission.calls[0][0] == world.agent.id


@pytest.mark.asyncio
async def test_private_agent_denied_and_clear_does_not_restore_default(
    world, monkeypatch
):
    monkeypatch.setattr(settings.AuditLogService, "log", AsyncMock())
    other = await User.create(
        username="private-owner", email="private@example.test", hashed_password="unused"
    )
    private = await make_agent(world.team, other, "Secret")
    await Agent.filter(id=private.id).update(visibility=AgentVisibility.PRIVATE)
    assert private.id not in [agent.id for agent in await available_agents(world.user)]
    with pytest.raises(BusinessError):
        await settings.update_config(
            settings.PreferenceInput(agent_id=private.id), MagicMock(), world.user
        )
    assert (await FeishuAgentPreference.get(user=world.user)).agent_id == world.agent.id
    await settings.update_config(
        settings.PreferenceInput(agent_id=None), MagicMock(), world.user
    )
    receipt = await receipt_for(world)
    assert receipt.agent_id is None
    await runtime.process_message(str(receipt.id))
    assert not world.submission.calls
    assert (
        await FeishuAgentReceipt.get(id=receipt.id)
    ).error == "feishu_agent_agent_none"


@pytest.mark.asyncio
async def test_bot_use_updates_personal_config_even_before_processing(world):
    second = await make_agent(world.team, world.user, "Second")
    await receipt_for(world, text=f"/use {second.id}")
    assert (await settings.get_config(world.user))["data"]["agent_id"] == str(second.id)
    cross_chat = await receipt_for(world, chat_id="oc_second_chat")
    assert cross_chat.agent_id == second.id


@pytest.mark.asyncio
async def test_unlinked_user_cannot_select_an_agent(world, monkeypatch):
    monkeypatch.setattr(settings.AuditLogService, "log", AsyncMock())
    await FeishuUser.filter(user=world.user).delete()
    assert (await settings.list_agents(world.user))["data"] == []
    with pytest.raises(BusinessError):
        await settings.update_config(
            settings.PreferenceInput(agent_id=world.agent.id), MagicMock(), world.user
        )


@pytest.mark.asyncio
async def test_migration_keeps_existing_user_choices_and_never_recreates_cleared_selection(
    world,
):
    connection = connections.get("default")
    await FeishuAgentPreference.all().delete()
    await connection.execute_query(
        "ALTER TABLE feishu_agent_sessions ADD COLUMN is_selected BOOLEAN NOT NULL DEFAULT FALSE"
    )
    session = await FeishuAgentSession.create(
        integration=world.integration,
        user=world.user,
        agent=world.agent,
        chat_id="legacy",
    )
    await connection.execute_query(
        "UPDATE feishu_agent_sessions SET is_selected=1 WHERE id=?", [str(session.id)]
    )
    await migrate_feishu_agent_selection()
    assert (await FeishuAgentPreference.get(user=world.user)).agent_id == world.agent.id
    await FeishuAgentPreference.filter(user=world.user).update(agent_id=None)
    await migrate_feishu_agent_selection()
    assert (await FeishuAgentPreference.get(user=world.user)).agent_id is None
    columns = await connection.execute_query_dict(
        'PRAGMA table_info("feishu_agent_sessions")'
    )
    assert "is_selected" not in {row["name"] for row in columns}


def test_personal_contract_rejects_user_impersonation():
    with pytest.raises(ValueError):
        settings.PreferenceInput.model_validate(
            {"agent_id": None, "user_id": str(uuid4())}
        )


@pytest.mark.asyncio
async def test_personal_switch_pauses_intake_processing_and_replies_without_losing_selection(
    world, monkeypatch
):
    from tests.services.test_feishu_agent_runtime import text_event
    from app.models.feishu_agent import FeishuAgentDelivery

    monkeypatch.setattr(settings.AuditLogService, "log", AsyncMock())
    receipt = await receipt_for(world)
    await settings.update_config(
        settings.PreferenceInput(is_enabled=False), MagicMock(), world.user
    )
    summary = (await settings.get_config(world.user))["data"]
    assert summary["is_enabled"] is False
    assert summary["agent_id"] == str(world.agent.id)
    assert await runtime.accept_message(text_event(message_id="paused")) is None
    await runtime.process_message(str(receipt.id))
    assert not world.submission.calls
    assert (await FeishuAgentReceipt.get(id=receipt.id)).status == "pending"
    await runtime._reply_text(receipt, "pending response")
    await runtime.deliver_pending_for_integration(world.integration.id)
    assert not world.transport.sent
    assert (await FeishuAgentDelivery.get(receipt=receipt)).status == "pending"
    await settings.update_config(
        settings.PreferenceInput(is_enabled=True), MagicMock(), world.user
    )
    await runtime.process_message(str(receipt.id))
    assert world.submission.calls[0][0] == world.agent.id
    await runtime.deliver_pending_for_integration(world.integration.id)
    assert any(row[1] == "pending response" for row in world.transport.sent)


@pytest.mark.asyncio
async def test_enabling_requires_saved_agent_and_is_owner_scoped(world, monkeypatch):
    monkeypatch.setattr(settings.AuditLogService, "log", AsyncMock())
    other = await User.create(
        username="switch-other",
        email="switch-other@example.test",
        hashed_password="unused",
    )
    await FeishuUser.create(user=other, feishu_user_id="switch-other")
    await FeishuAgentPreference.create(
        integration=world.integration, user=other, agent=world.agent
    )
    await settings.update_config(
        settings.PreferenceInput(is_enabled=False), MagicMock(), world.user
    )
    assert (await FeishuAgentPreference.get(user=other)).is_enabled is False
    await settings.update_config(
        settings.PreferenceInput(agent_id=None), MagicMock(), world.user
    )
    with pytest.raises(BusinessError):
        await settings.update_config(
            settings.PreferenceInput(is_enabled=True), MagicMock(), world.user
        )
    assert (await FeishuAgentPreference.get(user=world.user)).is_enabled is False


@pytest.mark.asyncio
async def test_personal_switch_migration_preserves_existing_users_but_not_future_opt_out(
    world,
):
    connection = connections.get("default")
    await connection.execute_query(
        "ALTER TABLE feishu_agent_preferences DROP COLUMN is_enabled"
    )
    await migrate_feishu_agent_selection()
    assert (await FeishuAgentPreference.get(user=world.user)).is_enabled is True
    await FeishuAgentPreference.filter(user=world.user).update(is_enabled=False)
    await migrate_feishu_agent_selection()
    assert (await FeishuAgentPreference.get(user=world.user)).is_enabled is False
