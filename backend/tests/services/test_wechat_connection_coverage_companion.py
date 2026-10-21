"""Connection authorization, model choices and binding summaries against a real ORM."""

import contextvars
from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio
from tortoise.context import TortoiseContext

from app.models.agent_run import AgentRun, AgentRunMode, AgentRunStatus
from app.models.knowledge_base import KnowledgeBase
from app.models.model import Model, ModelType, TeamModel
from app.models.user import Team, User
from app.models.wechat_agent import WeChatAgentConfig, WeChatAgentSession
from app.models.wechat_knowledge import (
    WeChatKnowledgeBinding,
    WeChatKnowledgeCollection,
)
from app.schemas.response import BusinessError
from app.services import wechat_connection as connection


@pytest_asyncio.fixture
async def db():
    async with TortoiseContext() as context:
        await context.init(
            db_url="sqlite://:memory:", modules={"models": ["app.models"]}
        )
        await context.generate_schemas()
        from app.models.integration import Integration

        await Integration.create(
            name="wechat",
            provider_type="wechat",
            display_name="WeChat iLink",
            enabled_capabilities=["agent_chat", "knowledge_collection"],
        )
        yield context


async def make_user(**overrides) -> User:
    values = {
        "id": uuid4(),
        "username": f"user-{uuid4().hex[:8]}",
        "email": f"{uuid4().hex[:8]}@example.test",
        "hashed_password": "unused",
        "is_active": True,
        "approval_status": "approved",
    }
    values.update(overrides)
    return await User.create(**values)


async def make_kb(user: User, **overrides) -> KnowledgeBase:
    team = await Team.create(id=uuid4(), name=f"team-{uuid4().hex[:6]}")
    values = {
        "id": uuid4(),
        "name": "Target",
        "team": team,
        "created_by": user,
        "status": "active",
    }
    values.update(overrides)
    return await KnowledgeBase.create(**values)


@pytest.mark.asyncio
async def test_binding_target_fails_closed_before_lookup(db, monkeypatch):
    from app.api.v1 import endpoints as endpoints_pkg  # noqa: F401
    from app.api.v1.endpoints import knowledge_bases as kb_endpoints

    seen: list[tuple] = []

    async def check_kb_access(kb_id, user, *, require_write=False):
        seen.append((kb_id, user.id, require_write))
        return SimpleNamespace(status="active", team=None)

    monkeypatch.setattr(kb_endpoints, "check_kb_access", check_kb_access)
    monkeypatch.setattr(
        kb_endpoints, "_kb_access_mode", contextvars.ContextVar("mode", default=None)
    )

    inactive = await make_user(is_active=False)
    with pytest.raises(BusinessError) as inactive_error:
        await connection.check_binding_target(uuid4(), inactive)
    assert inactive_error.value.msg_key == "inactive_user"

    unapproved = await make_user(approval_status="pending")
    with pytest.raises(BusinessError) as unapproved_error:
        await connection.check_binding_target(uuid4(), unapproved)
    assert unapproved_error.value.msg_key == "inactive_user"

    user = await make_user()
    with pytest.raises(BusinessError) as missing:
        await connection.check_binding_target(None, user)
    assert missing.value.msg_key == "kb_not_found"

    # An authorized lookup requests write access under the platform access mode.
    kb = await connection.check_binding_target(uuid4(), user)
    assert len(seen) == 1
    assert seen[0][1] == user.id
    assert seen[0][2] is True
    assert kb.status == "active"

    async def inactive_kb(kb_id, user, *, require_write=False):
        return SimpleNamespace(status="archived", team=None)

    monkeypatch.setattr(kb_endpoints, "check_kb_access", inactive_kb)
    with pytest.raises(BusinessError) as archived:
        await connection.check_binding_target(uuid4(), user)
    assert archived.value.msg_key == "wechat_kb_inactive"


@pytest.mark.asyncio
async def test_available_models_selects_vision_and_speech_only(db):
    user = await make_user()
    kb = await make_kb(user)
    vision = await Model.create(
        id=uuid4(),
        name="Vision",
        provider="openai",
        model_id="gpt-4o",
        model_type=ModelType.CHAT.value,
        capabilities={"vision": True},
    )
    blind = await Model.create(
        id=uuid4(),
        name="Blind",
        provider="openai",
        model_id="gpt-4o-mini",
        model_type=ModelType.CHAT.value,
        capabilities={},
    )
    speech = await Model.create(
        id=uuid4(),
        name="Speech",
        provider="openai",
        model_id="whisper-1",
        model_type=ModelType.STT.value,
    )
    for model in (vision, blind, speech):
        await TeamModel.create(id=uuid4(), team=kb.team, model=model, is_enabled=True)

    choices = await connection.available_models(kb)
    assert [item["name"] for item in choices["vision"]] == ["Vision"]
    assert [item["name"] for item in choices["stt"]] == ["Speech"]


@pytest.mark.asyncio
async def test_validate_models_rejects_unavailable_choices(db):
    user = await make_user()
    kb = await make_kb(user)
    speech = await Model.create(
        id=uuid4(),
        name="Speech",
        provider="openai",
        model_id="whisper-1",
        model_type=ModelType.STT.value,
    )
    await TeamModel.create(id=uuid4(), team=kb.team, model=speech, is_enabled=True)

    # Nothing selected is always valid, and an authorized choice passes.
    await connection.validate_models(kb, None, None)
    await connection.validate_models(kb, None, speech.id)

    with pytest.raises(BusinessError) as vision_error:
        await connection.validate_models(kb, uuid4(), None)
    assert vision_error.value.msg_key == "wechat_model_unavailable"

    with pytest.raises(BusinessError) as stt_error:
        await connection.validate_models(kb, None, uuid4())
    assert stt_error.value.msg_key == "wechat_model_unavailable"


@pytest.mark.asyncio
async def test_binding_summary_reports_inactive_and_active_agent_state(db):
    user = await make_user()
    binding = await WeChatKnowledgeBinding.create(
        user=user,
        wechat_user_id="wechat-user",
        bot_id="bot",
        token="encrypted",
        base_url="https://ilinkai.weixin.qq.com",
        purpose="none",
    )

    idle = await connection.binding_summary(binding)
    assert idle["collection"] is None
    assert idle["agent_config"] is None

    kb = await make_kb(user)
    collection = await WeChatKnowledgeCollection.create(
        binding=binding, knowledge_base_id=kb.id
    )
    summary = await connection.binding_summary(binding)
    assert summary["collection"]["knowledge_base_id"] == str(kb.id)
    assert summary["collection"]["knowledge_base_name"] == kb.name

    from app.models.agent import Agent, Conversation

    agent = await Agent.create(
        id=uuid4(), name="Assistant", team=kb.team, created_by=user
    )
    conversation = await Conversation.create(
        id=uuid4(), title="WeChat", agent=agent, user=user
    )
    await WeChatAgentConfig.create(binding=binding, agent=agent, variables={"a": 1})
    configured = await connection.binding_summary(binding)
    assert configured["agent_config"]["agent_name"] == "Assistant"
    assert configured["agent_config"]["variables"] == {"a": 1}
    assert configured["agent_config"]["conversation_id"] is None
    assert configured["agent_config"]["run_status"] is None

    run = await AgentRun.create(
        id=uuid4(),
        agent=agent,
        conversation=conversation,
        user=user,
        mode=AgentRunMode.SEND,
        status=AgentRunStatus.RUNNING,
    )
    await WeChatAgentSession.create(
        id=uuid4(),
        binding=binding,
        agent=agent,
        conversation=conversation,
        active_run=run,
    )
    active = await connection.binding_summary(binding)
    assert active["agent_config"]["conversation_id"] == str(conversation.id)
    assert active["agent_config"]["run_id"] == str(run.id)
    assert active["agent_config"]["run_status"] == AgentRunStatus.RUNNING.value
    assert collection.knowledge_base_id == kb.id
