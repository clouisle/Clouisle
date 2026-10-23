"""Single-purpose switching: agent authorization, busy detection, variable validation."""

from uuid import uuid4

import pytest
import pytest_asyncio
from tortoise.context import TortoiseContext

from app.integrations.credentials import encrypt_secret
from app.models.agent import Agent, AgentStatus, Conversation
from app.models.agent_run import AgentRun, AgentRunMode, AgentRunStatus
from app.models.user import Team, TeamMember, User
from app.models.integration_delivery import IntegrationDelivery
from app.models.wechat_agent import (
    WeChatAgentReceipt,
    WeChatAgentSession,
)
from app.models.wechat_knowledge import (
    WeChatKnowledgeBinding,
    WeChatKnowledgeReceipt,
)

from tests.services.delivery_fixtures import wechat_delivery_fields
from app.schemas.response import BusinessError
from app.services import wechat_purpose


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


def definition(name: str, **overrides) -> dict:
    entry = {"name": name, "type": "text", "required": False}
    entry.update(overrides)
    return entry


def variables(*entries: dict):
    return SimpleAgent(entries)


class SimpleAgent:
    def __init__(self, entries):
        self.variables = list(entries)


def test_resolve_variables_rejects_unknown_names():
    with pytest.raises(BusinessError) as unknown:
        wechat_purpose.resolve_variables(variables(definition("a")), {"b": "x"})
    assert unknown.value.msg_key == "wechat_agent_variables_invalid"


def test_resolve_variables_requires_required_values():
    with pytest.raises(BusinessError) as missing:
        wechat_purpose.resolve_variables(variables(definition("a", required=True)), {})
    assert missing.value.msg_key == "wechat_agent_variables_invalid"

    with pytest.raises(BusinessError) as blank:
        wechat_purpose.resolve_variables(
            variables(definition("a", required=True)), {"a": ""}
        )
    assert blank.value.msg_key == "wechat_agent_variables_invalid"


def test_resolve_variables_uses_defaults_for_hidden_and_omitted_entries():
    resolved = wechat_purpose.resolve_variables(
        variables(
            definition("shown", default="fallback"),
            definition("hidden", hidden=True, default="forced"),
            definition("optional", default=""),
            definition("absent"),
        ),
        {"shown": "provided", "hidden": "ignored"},
    )
    # A hidden definition always takes its default; an empty optional value is dropped.
    assert resolved == {"shown": "provided", "hidden": "forced"}


@pytest.mark.parametrize("value", [True, "maybe", float("nan"), float("inf"), 11])
def test_resolve_variables_validates_numbers(value):
    with pytest.raises(BusinessError) as invalid:
        wechat_purpose.resolve_variables(
            variables(definition("n", type="number", min=0, max=10)),
            {"n": value},
        )
    assert invalid.value.msg_key == "wechat_agent_variables_invalid"


def test_resolve_variables_accepts_bounded_numbers_and_normalizes_checkboxes_and_text():
    resolved = wechat_purpose.resolve_variables(
        variables(
            definition("n", type="number", min=0, max=10),
            definition("flag", type="checkbox"),
            definition("off", type="checkbox"),
            definition("note", maxLength=5, options=["ok", "fine"]),
        ),
        {"n": "7.5", "flag": True, "off": "false", "note": "fine"},
    )
    assert resolved == {"n": "7.5", "flag": "true", "off": "false", "note": "fine"}


def test_resolve_variables_rejects_checkbox_types_options_and_length():
    with pytest.raises(BusinessError) as bad_checkbox:
        wechat_purpose.resolve_variables(
            variables(definition("c", type="checkbox")), {"c": 1}
        )
    assert bad_checkbox.value.msg_key == "wechat_agent_variables_invalid"

    with pytest.raises(BusinessError) as bad_type:
        wechat_purpose.resolve_variables(variables(definition("t")), {"t": 5})
    assert bad_type.value.msg_key == "wechat_agent_variables_invalid"

    with pytest.raises(BusinessError) as too_long:
        wechat_purpose.resolve_variables(
            variables(definition("t", maxLength=2)), {"t": "abc"}
        )
    assert too_long.value.msg_key == "wechat_agent_variables_invalid"

    with pytest.raises(BusinessError) as outside_options:
        wechat_purpose.resolve_variables(
            variables(definition("t", options=["a", "b"])), {"t": "c"}
        )
    assert outside_options.value.msg_key == "wechat_agent_variables_invalid"


@pytest.mark.asyncio
async def test_authorized_agent_checks_identity_and_publication(db, monkeypatch):
    from app.api.v1.endpoints import chat as chat_endpoints

    with pytest.raises(BusinessError) as no_agent:
        await wechat_purpose.authorized_agent(None, await make_user())
    assert (no_agent.value.msg_key, no_agent.value.status_code) == (
        "agent_not_found",
        404,
    )

    inactive = await make_user(is_active=False)
    with pytest.raises(BusinessError) as not_active:
        await wechat_purpose.authorized_agent(uuid4(), inactive)
    assert (not_active.value.msg_key, not_active.value.status_code) == (
        "inactive_user",
        403,
    )

    pending = await make_user(approval_status="pending")
    with pytest.raises(BusinessError) as unapproved:
        await wechat_purpose.authorized_agent(uuid4(), pending)
    assert unapproved.value.msg_key == "inactive_user"

    user = await make_user()
    team = await Team.create(id=uuid4(), name="Team")
    await TeamMember.create(id=uuid4(), team=team, user=user, role="owner")

    draft = await Agent.create(
        id=uuid4(),
        name="Draft",
        team=team,
        created_by=user,
        status=AgentStatus.DRAFT,
        visibility="team",
    )
    visible = await chat_endpoints.check_agent_chat_access(draft.id, user)
    assert visible.id == draft.id

    monkeypatch.setattr(chat_endpoints, "check_agent_chat_access", _returning(draft))
    with pytest.raises(BusinessError) as unpublished:
        await wechat_purpose.authorized_agent(draft.id, user)
    assert (unpublished.value.msg_key, unpublished.value.status_code) == (
        "agent_access_denied",
        403,
    )

    published = await Agent.create(
        id=uuid4(),
        name="Published",
        team=team,
        created_by=user,
        status=AgentStatus.PUBLISHED,
        visibility="team",
    )
    monkeypatch.setattr(
        chat_endpoints, "check_agent_chat_access", _returning(published)
    )
    assert (
        await wechat_purpose.authorized_agent(published.id, user)
    ).id == published.id


def _returning(agent):
    async def access(agent_id, user, **kwargs):
        return agent

    return access


@pytest.mark.asyncio
async def test_switch_idle_reports_each_kind_of_pending_work(db):
    user = await make_user()
    team = await Team.create(id=uuid4(), name="Team")
    agent = await Agent.create(
        id=uuid4(),
        name="Agent",
        team=team,
        created_by=user,
        status=AgentStatus.PUBLISHED,
    )
    binding = await WeChatKnowledgeBinding.create(
        user=user,
        wechat_user_id=f"wechat-{uuid4().hex[:6]}",
        bot_id="bot",
        token=encrypt_secret("token"),
        base_url="https://ilinkai.weixin.qq.com",
        purpose="agent",
    )
    conversation = await Conversation.create(
        id=uuid4(), title="WeChat", agent=agent, user=user
    )

    # Nothing pending: switching is allowed.
    await wechat_purpose.check_switch_idle(binding.id)

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
    with pytest.raises(BusinessError) as active:
        await wechat_purpose.check_switch_idle(binding.id)
    assert (active.value.msg_key, active.value.status_code) == (
        "wechat_purpose_busy",
        409,
    )

    await AgentRun.filter(id=run.id).update(status=AgentRunStatus.COMPLETED)
    await wechat_purpose.check_switch_idle(binding.id)

    receipt = await WeChatAgentReceipt.create(
        id=uuid4(),
        binding=binding,
        user=user,
        agent=agent,
        message_id="m-1",
        payload="{}",
    )
    with pytest.raises(BusinessError) as queued:
        await wechat_purpose.check_switch_idle(binding.id)
    assert queued.value.msg_key == "wechat_purpose_busy"
    await WeChatAgentReceipt.filter(id=receipt.id).delete()

    delivery_receipt = await WeChatAgentReceipt.create(
        id=uuid4(),
        binding=binding,
        user=user,
        agent=agent,
        message_id="m-2",
        payload="{}",
        status="completed",
    )
    delivery = await IntegrationDelivery.create(
        id=uuid4(),
        **wechat_delivery_fields(delivery_receipt),
        event_key="final",
        sequence=0,
        payload={"kind": "text", "text": "hi"},
    )
    with pytest.raises(BusinessError) as delivering:
        await wechat_purpose.check_switch_idle(binding.id)
    assert delivering.value.msg_key == "wechat_purpose_busy"
    await IntegrationDelivery.filter(id=delivery.id).update(status="sent")
    await wechat_purpose.check_switch_idle(binding.id)

    from app.models.knowledge_base import KnowledgeBase

    kb = await KnowledgeBase.create(
        id=uuid4(), name="Target", team=team, created_by=user
    )
    collection = await WeChatKnowledgeReceipt.create(
        id=uuid4(),
        binding=binding,
        user=user,
        message_id="c-1",
        knowledge_base_id=kb.id,
        payload="{}",
    )
    with pytest.raises(BusinessError) as collecting:
        await wechat_purpose.check_switch_idle(binding.id)
    assert collecting.value.msg_key == "wechat_purpose_busy"
    await WeChatKnowledgeReceipt.filter(id=collection.id).update(status="completed")
    await wechat_purpose.check_switch_idle(binding.id)
