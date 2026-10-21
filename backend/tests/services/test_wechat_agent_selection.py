"""Agent selection commands on the WeChat durable runtime, on a real ORM.

The runtime, the ``/agents`` list ACL and the ``/use`` switch are exercised
against the same isolated in-memory Tortoise database as the runtime tests:
only the submission service and the WeChat IO boundary are stubbed.  The
assertions stay on consumer-visible invariants — the persisted configuration,
the durable outbox rows, the generated runs and the receiver's own snapshot —
never on the wording of a reply.
"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import wechat_knowledge as endpoints
from app.integrations.credentials import encrypt_secret
from app.models.agent import Agent, AgentStatus, AgentVisibility, Conversation
from app.models.agent_run import AgentRun, AgentRunStatus
from app.models.integration import Integration
from app.models.user import Team, TeamMember, User
from app.models.wechat_agent import (
    WeChatAgentConfig,
    WeChatAgentDelivery,
    WeChatAgentReceipt,
    WeChatAgentSession,
)
from app.models.wechat_knowledge import WeChatKnowledgeBinding, WeChatKnowledgeReceipt
from app.services import wechat_agent_io as io
from app.services import wechat_agent_runtime as runtime
from app.services import wechat_receiver as receiver
from app.services.wechat_agent_io import deliver_pending as real_deliver_pending
from app.services.wechat_connection import utcnow
from app.services.wechat_purpose import available_agents
from tests.services.test_wechat_agent_runtime import (
    db as db,
    world as world,
    receipt_for,
)


def upstream_message(text, identifier, context_token="ctx-1"):
    return {
        "message_id": identifier,
        "from_user_id": "wechat-user",
        "message_type": 1,
        "message_state": 2,
        "context_token": context_token,
        "item_list": [{"type": 1, "text_item": {"text": text}}],
    }


async def make_extra_agent(world, name):
    """A second published Agent owned by the same WeChat user."""
    return await Agent.create(
        id=uuid4(),
        name=name,
        team=world.team,
        created_by=world.user,
        status=AgentStatus.PUBLISHED,
        visibility=AgentVisibility.TEAM,
        enable_attachments=False,
    )


async def command_receipt(world, text, identifier):
    """A durable receipt holding exactly what the receiver would persist."""
    return await WeChatAgentReceipt.create(
        binding_id=world.binding.id,
        user_id=world.user.id,
        agent_id=world.agent.id,
        variables={},
        message_id=identifier,
        payload=encrypt_secret(json.dumps(upstream_message(text, identifier))),
    )


def deliveries_for(receipt_id):
    return WeChatAgentDelivery.filter(receipt_id=receipt_id).order_by("sequence")


async def texts_for(receipt_id):
    return [row.payload.get("text") or "" for row in await deliveries_for(receipt_id)]


def agent_names(agents):
    return [agent.name for agent in agents]


async def process(world):
    return await runtime.process_binding(str(world.binding.id))


async def config_for(world):
    return await WeChatAgentConfig.get(binding_id=world.binding.id)


async def generation_of(world):
    return (await WeChatKnowledgeBinding.get(id=world.binding.id)).generation


async def complete_outbox(world):
    """Resolve every outbox row as if the transport accepted it.

    The runtime's IO boundary is stubbed, so without this a leftover pending
    delivery would keep the binding busy for the next switch.  The receipt ids
    are resolved first because SQLite cannot update through a join.
    """
    receipt_ids = await WeChatAgentReceipt.filter(
        binding_id=world.binding.id
    ).values_list("id", flat=True)
    if not receipt_ids:
        return
    await WeChatAgentDelivery.filter(
        receipt_id__in=list(receipt_ids), status__in=["pending", "sending"]
    ).update(status="submitted")


async def accept_one(world, text, identifier):
    """Persist one inbound message through the real receiver snapshot path."""
    fresh = await WeChatKnowledgeBinding.get(id=world.binding.id)
    await receiver.accept_updates(fresh, {"msgs": [upstream_message(text, identifier)]})
    return await WeChatAgentReceipt.get(message_id=identifier)


async def idle(world):
    """Leave no run, queued receipt or unsent delivery behind."""
    await complete_outbox(world)
    await process(world)
    await complete_outbox(world)


@pytest.mark.asyncio
async def test_agents_list_is_owner_scoped_and_numbered_deterministically(world):
    other_user = await User.create(
        id=uuid4(),
        username="stranger",
        email="stranger@example.test",
        hashed_password="unused",
        is_active=True,
        approval_status="approved",
    )
    other_team = await Team.create(id=uuid4(), name="Other team")
    await TeamMember.create(id=uuid4(), team=other_team, user=other_user, role="owner")
    secret = await Agent.create(
        id=uuid4(),
        name="Stranger agent",
        team=other_team,
        created_by=other_user,
        status=AgentStatus.PUBLISHED,
        visibility=AgentVisibility.PRIVATE,
        enable_attachments=False,
    )
    draft = await Agent.create(
        id=uuid4(),
        name="Draft only",
        team=world.team,
        created_by=world.user,
        status=AgentStatus.DRAFT,
        visibility=AgentVisibility.TEAM,
        enable_attachments=False,
    )
    await make_extra_agent(world, "Alpha")
    await make_extra_agent(world, "Zeta")

    receipt = await command_receipt(world, "/智能体", "list-1")
    await process(world)

    listed = agent_names(await available_agents(world.user))
    assert listed == ["Alpha", "Test agent", "Zeta"]
    accessible = {agent.id for agent in await available_agents(world.user)}
    assert secret.id not in accessible
    assert draft.id not in accessible
    assert (await WeChatAgentReceipt.get(id=receipt.id)).status == "completed"
    # Listing is read-only: it never starts a run and never switches.
    assert not await AgentRun.all().exists()
    assert (await config_for(world)).agent_id == world.agent.id
    # The numbers a user sees are the ones the web list endpoint exposes.
    published = (await endpoints.agents(world.user))["data"]
    assert [row["name"] for row in published] == listed


@pytest.mark.asyncio
async def test_agents_list_names_every_accessible_agent_in_order(world):
    await make_extra_agent(world, "Beta")
    await make_extra_agent(world, "Alpha")

    receipt = await command_receipt(world, "/agents", "list-en")
    await process(world)

    listed = agent_names(await available_agents(world.user))
    assert listed == ["Alpha", "Beta", "Test agent"]
    joined = "\n".join(await texts_for(receipt.id))
    assert joined
    positions = [joined.index(name) for name in listed]
    assert positions == sorted(positions), "the reply must follow the list order"
    for index, name in enumerate(listed, start=1):
        assert f"{index}. {name}" in joined
    assert not await AgentRun.all().exists()


@pytest.mark.asyncio
async def test_agents_command_with_no_available_agent_still_replies(world):
    """An empty list is an answer, not a silent drop."""
    await Agent.filter(team_id=world.team.id).update(status=AgentStatus.DRAFT)
    assert await available_agents(world.user) == []

    receipt = await command_receipt(world, "/agents", "list-empty")
    await runtime._agent_selection_command(receipt, "agents")

    assert (await WeChatAgentReceipt.get(id=receipt.id)).status == "completed"
    assert await deliveries_for(receipt.id).count() == 1
    assert not await AgentRun.all().exists()


@pytest.mark.asyncio
async def test_use_by_number_switches_configuration(world):
    second = await make_extra_agent(world, "Zeta")
    before = await generation_of(world)
    receipt = await command_receipt(world, "/使用 2", "use-number")
    await process(world)

    config = await config_for(world)
    assert config.agent_id == second.id
    assert config.variables == {}
    assert config.stt_model_id is None
    assert await generation_of(world) != before
    assert (await WeChatAgentReceipt.get(id=receipt.id)).status == "completed"
    assert await deliveries_for(receipt.id).count() == 1
    # A control command never produces a run.
    assert not await AgentRun.all().exists()
    assert not world.submission.calls


@pytest.mark.asyncio
async def test_use_by_uuid_switches_configuration(world):
    second = await make_extra_agent(world, "Zeta")
    receipt = await command_receipt(world, f"/use {second.id}", "use-uuid")
    await process(world)

    assert (await config_for(world)).agent_id == second.id
    assert (await WeChatAgentReceipt.get(id=receipt.id)).status == "completed"
    assert await deliveries_for(receipt.id).count() == 1
    assert not await AgentRun.all().exists()


@pytest.mark.asyncio
async def test_use_current_agent_is_a_noop_for_configuration(world):
    before = await generation_of(world)
    receipt = await command_receipt(world, "/use 1", "use-current")
    await process(world)

    assert (await config_for(world)).agent_id == world.agent.id
    assert await generation_of(world) == before
    assert (await WeChatAgentReceipt.get(id=receipt.id)).status == "completed"
    assert await deliveries_for(receipt.id).count() == 1


@pytest.mark.asyncio
async def test_switch_is_visible_in_web_summary_and_receiver_snapshot(world):
    """The web summary and the next inbound snapshot must agree."""
    second = await make_extra_agent(world, "Zeta")
    await command_receipt(world, "/使用 2", "use-summary")
    await process(world)

    summary = await endpoints.bindings(world.user)
    agent_config = summary["data"][0]["agent_config"]
    assert agent_config["agent_id"] == str(second.id)
    assert agent_config["stt_model_id"] is None

    # A stale binding object must not commit receipts against the old Agent.
    stale = SimpleNamespace(
        id=world.binding.id,
        generation=world.binding.generation,
        cursor=world.binding.cursor,
    )
    assert await receiver.accept_updates(stale, {"msgs": []}) == []

    accepted = await accept_one(world, "next message", "after-switch")
    assert accepted.agent_id == second.id
    assert accepted.variables == {}
    assert accepted.stt_model_id is None


@pytest.mark.asyncio
async def test_switch_back_preserves_the_previous_conversation(world):
    second = await make_extra_agent(world, "Zeta")

    await receipt_for(world, identifier="first-1")
    await process(world)
    run = world.submission.run
    session = await WeChatAgentSession.get(
        binding_id=world.binding.id, agent_id=world.agent.id
    )
    first_conversation = session.conversation_id
    assert first_conversation is not None
    await idle(world)

    await command_receipt(world, "/使用 2", "switch-away")
    await process(world)
    await idle(world)
    await command_receipt(world, "/使用 1", "switch-back")
    await process(world)
    await idle(world)

    assert (await config_for(world)).agent_id == world.agent.id
    session = await WeChatAgentSession.get(
        binding_id=world.binding.id, agent_id=world.agent.id
    )
    assert session.conversation_id == first_conversation
    # The new Agent never inherited the previous Agent's conversation.
    other = await WeChatAgentSession.filter(
        binding_id=world.binding.id, agent_id=second.id
    ).first()
    assert other is None or other.conversation_id != first_conversation
    # The finished run stays attached to its own conversation.
    assert str((await AgentRun.get(id=run.id)).conversation_id) == str(
        first_conversation
    )


@pytest.mark.asyncio
async def test_use_uses_variable_defaults_and_clears_speech_recognition(world):
    second = await make_extra_agent(world, "Zeta")
    await Agent.filter(id=second.id).update(
        variables=[
            {"name": "tone", "type": "text", "required": True, "default": "brief"},
            {
                "name": "hidden_key",
                "type": "text",
                "required": True,
                "hidden": True,
                "default": "shh",
            },
            {"name": "optional", "type": "text", "required": False},
        ]
    )
    await WeChatAgentConfig.filter(binding_id=world.binding.id).update(
        stt_model_id=uuid4()
    )
    receipt = await command_receipt(world, "/使用 2", "use-defaults")
    await process(world)

    config = await config_for(world)
    assert config.variables == {"tone": "brief", "hidden_key": "shh"}
    assert config.stt_model_id is None
    assert (await WeChatAgentReceipt.get(id=receipt.id)).status == "completed"


@pytest.mark.asyncio
async def test_use_required_variable_without_default_refuses_to_switch(world):
    second = await make_extra_agent(world, "Zeta")
    await Agent.filter(id=second.id).update(
        variables=[{"name": "topic", "type": "text", "required": True, "default": ""}]
    )
    before = await generation_of(world)

    receipt = await command_receipt(world, "/使用 2", "use-required")
    await process(world)

    config = await config_for(world)
    assert config.agent_id == world.agent.id, "configuration must not change"
    assert config.variables == {}
    assert await generation_of(world) == before
    assert (await WeChatAgentReceipt.get(id=receipt.id)).status == "completed"
    assert await deliveries_for(receipt.id).count() == 1
    assert not await AgentRun.all().exists()


@pytest.mark.asyncio
async def test_use_unauthorized_uuid_is_refused_without_side_effects(world):
    stranger = await User.create(
        id=uuid4(),
        username="outsider",
        email="outsider@example.test",
        hashed_password="unused",
        is_active=True,
        approval_status="approved",
    )
    stranger_team = await Team.create(id=uuid4(), name="Stranger team")
    await TeamMember.create(id=uuid4(), team=stranger_team, user=stranger, role="owner")
    secret = await Agent.create(
        id=uuid4(),
        name="Secret agent",
        team=stranger_team,
        created_by=stranger,
        status=AgentStatus.PUBLISHED,
        visibility=AgentVisibility.PRIVATE,
        enable_attachments=False,
    )
    before = await generation_of(world)
    receipt = await command_receipt(world, f"/use {secret.id}", "use-unauthorized")
    await process(world)

    assert (await config_for(world)).agent_id == world.agent.id
    assert await generation_of(world) == before
    assert (await WeChatAgentReceipt.get(id=receipt.id)).status == "completed"
    assert await deliveries_for(receipt.id).count() == 1
    assert not await AgentRun.all().exists()


@pytest.mark.asyncio
async def test_use_draft_agent_is_refused(world):
    draft = await make_extra_agent(world, "Zeta")
    await Agent.filter(id=draft.id).update(status=AgentStatus.DRAFT)
    receipt = await command_receipt(world, f"/use {draft.id}", "use-draft")
    await process(world)

    assert (await config_for(world)).agent_id == world.agent.id
    assert (await WeChatAgentReceipt.get(id=receipt.id)).status == "completed"
    assert await deliveries_for(receipt.id).count() == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text",
    [
        "/use",
        "/使用",
        "/use 99",
        "/使用 99",
        "/use not-a-number",
        "/use 0",
    ],
)
async def test_missing_or_invalid_argument_keeps_configuration(world, text):
    await make_extra_agent(world, "Zeta")
    before = await generation_of(world)
    receipt = await command_receipt(world, text, f"arg-{abs(hash(text))}")
    await process(world)

    assert (await config_for(world)).agent_id == world.agent.id
    assert await generation_of(world) == before
    assert (await WeChatAgentReceipt.get(id=receipt.id)).status == "completed"
    assert await deliveries_for(receipt.id).count() == 1
    assert not await AgentRun.all().exists()


@pytest.mark.asyncio
async def test_use_unknown_uuid_is_refused(world):
    await make_extra_agent(world, "Zeta")
    before = await generation_of(world)
    receipt = await command_receipt(world, f"/use {uuid4()}", "use-unknown")
    await process(world)

    assert (await config_for(world)).agent_id == world.agent.id
    assert await generation_of(world) == before
    assert (await WeChatAgentReceipt.get(id=receipt.id)).status == "completed"
    assert await deliveries_for(receipt.id).count() == 1


@pytest.mark.asyncio
async def test_switch_refused_while_a_run_is_active(world):
    second = await make_extra_agent(world, "Zeta")
    await receipt_for(world, identifier="busy-run")
    await process(world)
    assert (
        await AgentRun.get(id=world.submission.run.id)
    ).status == AgentRunStatus.QUEUED

    receipt = await command_receipt(world, "/使用 2", "use-busy")
    await process(world)

    assert agent_names(await available_agents(world.user))[-1] == second.name
    assert (await config_for(world)).agent_id == world.agent.id
    assert (await WeChatAgentReceipt.get(id=receipt.id)).status == "completed"
    assert await deliveries_for(receipt.id).count() == 1
    # The command did not disturb the running work.
    assert await WeChatAgentSession.filter(active_run_id__not_isnull=True).exists()


@pytest.mark.asyncio
async def test_switch_refused_while_another_receipt_is_still_queued(world):
    """An ordinary message that is still queued blocks the switch."""
    await make_extra_agent(world, "Zeta")
    # The submission boundary is unavailable, so this message stays queued
    # without ever producing a run: the pending receipt is the only blocker.
    world.submission.error = RuntimeError("submission unavailable")
    queued = await receipt_for(world, identifier="queued-msg")
    await process(world)
    await complete_outbox(world)
    assert (await WeChatAgentReceipt.get(id=queued.id)).status == "pending"
    assert not await AgentRun.all().exists()

    receipt = await command_receipt(world, "/使用 2", "use-queued")
    await process(world)

    assert (await config_for(world)).agent_id == world.agent.id
    assert (await WeChatAgentReceipt.get(id=receipt.id)).status == "completed"
    assert await deliveries_for(receipt.id).count() == 1
    # The blocked message is still waiting; the command never replaced it.
    assert (await WeChatAgentReceipt.get(id=queued.id)).status == "pending"
    assert (await WeChatAgentReceipt.get(id=queued.id)).run_id is None
    assert not await AgentRun.all().exists()


@pytest.mark.asyncio
async def test_switch_refused_while_outbox_has_a_pending_delivery(world):
    await make_extra_agent(world, "Zeta")
    await receipt_for(world, identifier="pending-outbox")
    await process(world)
    await AgentRun.filter(id=world.submission.run.id).update(
        status=AgentRunStatus.COMPLETED, finished_at=utcnow()
    )
    await process(world)
    # The runtime's IO boundary records rows but never sends them, so rows are
    # still pending here: exactly the guard condition.
    assert await WeChatAgentDelivery.filter(status="pending").exists()

    receipt = await command_receipt(world, "/使用 2", "use-outbox")
    await process(world)

    assert (await config_for(world)).agent_id == world.agent.id
    assert (await WeChatAgentReceipt.get(id=receipt.id)).status == "completed"
    assert await deliveries_for(receipt.id).count() == 1


@pytest.mark.asyncio
async def test_switch_refused_while_collection_work_is_pending(world):
    await make_extra_agent(world, "Zeta")
    await WeChatKnowledgeReceipt.create(
        binding_id=world.binding.id,
        user_id=world.user.id,
        knowledge_base_id=None,
        message_id="collecting",
        payload=encrypt_secret(
            json.dumps(upstream_message("collect me", "collecting"))
        ),
        status="processing",
    )

    receipt = await command_receipt(world, "/使用 2", "use-collecting")
    await process(world)

    assert (await config_for(world)).agent_id == world.agent.id
    assert (await WeChatAgentReceipt.get(id=receipt.id)).status == "completed"
    assert await deliveries_for(receipt.id).count() == 1


@pytest.mark.asyncio
async def test_command_receipt_does_not_block_its_own_switch(world):
    """The command itself is excluded from the busy guard."""
    second = await make_extra_agent(world, "Zeta")
    await receipt_for(world, identifier="earlier")
    await process(world)
    await AgentRun.filter(id=world.submission.run.id).update(
        status=AgentRunStatus.COMPLETED, finished_at=utcnow()
    )
    await idle(world)
    # Every earlier receipt is resolved, so only the command itself is pending.
    assert await WeChatAgentReceipt.filter(status="pending").count() == 0

    receipt = await command_receipt(world, "/使用 2", "use-own-receipt")
    await process(world)

    assert (await config_for(world)).agent_id == second.id
    assert (await WeChatAgentReceipt.get(id=receipt.id)).status == "completed"


@pytest.mark.asyncio
async def test_already_consumed_command_receipt_never_switches_twice(world):
    """A retried or racing pass cannot re-apply an applied command."""
    second = await make_extra_agent(world, "Zeta")
    receipt = await command_receipt(world, "/使用 2", "use-replay")
    await process(world)
    assert (await config_for(world)).agent_id == second.id

    # A recovery pass holding the pre-consume snapshot runs the same command.
    stale = await WeChatAgentReceipt.get(id=receipt.id)
    session = await WeChatAgentSession.get(
        binding_id=world.binding.id, agent_id=world.agent.id
    )
    await runtime._apply_command(stale, session, None, "use")

    assert (await config_for(world)).agent_id == second.id, "not re-applied"
    assert await deliveries_for(receipt.id).count() == 1, "the reply is not duplicated"
    assert not await AgentRun.all().exists()


@pytest.mark.asyncio
async def test_repeated_passes_produce_one_reply_per_command(world):
    second = await make_extra_agent(world, "Zeta")
    receipt = await command_receipt(world, "/使用 2", "use-retries")
    for _ in range(4):
        await process(world)

    assert await deliveries_for(receipt.id).count() == 1
    assert (await WeChatAgentReceipt.get(id=receipt.id)).status == "completed"
    assert (await config_for(world)).agent_id == second.id
    assert await AgentRun.all().count() == 0
    assert not world.submission.calls


@pytest.mark.asyncio
async def test_agents_command_is_not_resent_on_recovery(world):
    receipt = await command_receipt(world, "/agents", "list-retries")
    await process(world)
    await process(world)

    assert await deliveries_for(receipt.id).count() == 1
    assert (await WeChatAgentReceipt.get(id=receipt.id)).status == "completed"
    assert not await AgentRun.all().exists()


@pytest.mark.asyncio
async def test_command_before_first_conversation_gets_a_delivery_context(world):
    """A switch may be the very first message on a fresh binding."""
    await WeChatAgentSession.filter(binding_id=world.binding.id).delete()
    await Conversation.all().delete()
    second = await make_extra_agent(world, "Zeta")

    receipt = await command_receipt(world, "/使用 2", "use-fresh")
    await process(world)

    assert (await config_for(world)).agent_id == second.id
    session = await WeChatAgentSession.get(
        binding_id=world.binding.id, agent_id=world.agent.id
    )
    assert session.conversation_id is not None
    # The real IO layer can address the reply from durable rows alone.
    row = await deliveries_for(receipt.id).first()
    context, key = await io._delivery_context(
        world.binding, row, await WeChatAgentReceipt.get(id=receipt.id), None
    )
    assert key == ""
    assert context["agent_id"] == world.agent.id
    assert context["conversation_id"] == session.conversation_id
    assert context["context_token"] == "ctx-1"


@pytest.mark.asyncio
async def test_switch_reply_reaches_the_transport(world, monkeypatch):
    """End-to-end through the real outbox with a stubbed transport."""
    second = await make_extra_agent(world, "Zeta")
    receipt = await command_receipt(world, "/使用 2", "use-transport")
    sent = []

    class Transport:
        def __init__(self, *args):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def send_text(self, recipient, text, token, *, client_id):
            sent.append((recipient, text, token, client_id))

    monkeypatch.setattr(io, "WeChatClient", Transport)
    monkeypatch.setattr(
        "app.services.wechat_agent_io.deliver_pending", real_deliver_pending
    )
    await process(world)

    assert len(sent) == 1
    recipient, text, token, client_id = sent[0]
    assert recipient == world.binding.wechat_user_id
    assert token == "ctx-1"
    assert second.name in text
    assert client_id == str((await deliveries_for(receipt.id).first()).id)
    assert (await config_for(world)).agent_id == second.id


@pytest.mark.asyncio
async def test_receiver_accepted_command_message_switches(world):
    """A command arrives like any other message: durable receipt first."""
    second = await make_extra_agent(world, "Zeta")
    receipt = await accept_one(world, "/使用 2", "from-receiver")
    assert receipt.agent_id == world.agent.id

    await process(world)

    assert (await config_for(world)).agent_id == second.id
    assert (await WeChatAgentReceipt.get(id=receipt.id)).status == "completed"
    assert await deliveries_for(receipt.id).count() == 1


@pytest.mark.asyncio
async def test_next_message_after_switch_uses_the_new_agent(world):
    """The snapshot on the receipt, not the current config, routes the run."""
    second = await make_extra_agent(world, "Zeta")
    await command_receipt(world, "/使用 2", "use-then-chat")
    await process(world)
    await idle(world)

    await accept_one(world, "hello again", "after-switch-chat")
    await process(world)

    assert world.submission.calls, "the next message must start a run"
    assert world.submission.calls[-1][0] == second.id
    assert world.submission.run.agent_id == second.id
    assert world.submission.run.status == AgentRunStatus.QUEUED


@pytest.mark.asyncio
async def test_command_on_a_binding_whose_purpose_left_agent_is_not_switched(world):
    await make_extra_agent(world, "Zeta")
    await WeChatKnowledgeBinding.filter(id=world.binding.id).update(purpose="none")
    receipt = await command_receipt(world, "/使用 2", "use-purpose-none")
    await process(world)

    assert (await config_for(world)).agent_id == world.agent.id
    assert not await deliveries_for(receipt.id).exists()
    assert not await AgentRun.all().exists()
    # The refused command is not consumed, so it stays recoverable.
    assert (await WeChatAgentReceipt.get(id=receipt.id)).status == "pending"


@pytest.mark.asyncio
async def test_command_on_a_disconnected_binding_is_not_switched(world):
    await make_extra_agent(world, "Zeta")
    await WeChatKnowledgeBinding.filter(id=world.binding.id).update(
        status="disconnected", token="", disconnected_at=utcnow()
    )
    receipt = await command_receipt(world, "/使用 2", "use-disconnected")
    await process(world)

    assert (await config_for(world)).agent_id == world.agent.id
    refreshed = await WeChatAgentReceipt.get(id=receipt.id)
    assert refreshed.status == "error"
    assert refreshed.error == "wechat_agent_binding_disconnected"
    assert not await deliveries_for(receipt.id).exists()


@pytest.mark.asyncio
async def test_command_from_another_user_is_refused(world):
    await make_extra_agent(world, "Zeta")
    stranger = await User.create(
        id=uuid4(),
        username="intruder",
        email="intruder@example.test",
        hashed_password="unused",
        is_active=True,
        approval_status="approved",
    )
    receipt = await command_receipt(world, "/使用 2", "use-other-user")
    await WeChatAgentReceipt.filter(id=receipt.id).update(user_id=stranger.id)
    await process(world)

    assert (await config_for(world)).agent_id == world.agent.id
    refreshed = await WeChatAgentReceipt.get(id=receipt.id)
    assert refreshed.status == "error"
    assert not await deliveries_for(receipt.id).exists()


@pytest.mark.asyncio
async def test_agent_feature_disabled_leaves_command_receipt_untouched(world):
    await make_extra_agent(world, "Zeta")
    await Integration.filter(provider_type="wechat").update(enabled_capabilities=[])
    receipt = await command_receipt(world, "/使用 2", "use-disabled")
    await process(world)

    assert (await config_for(world)).agent_id == world.agent.id
    assert (await WeChatAgentReceipt.get(id=receipt.id)).status == "pending"
    assert not await WeChatAgentDelivery.filter(receipt_id=receipt.id).exists()


@pytest.mark.asyncio
async def test_switch_is_recorded_in_the_audit_log(world, monkeypatch):
    second = await make_extra_agent(world, "Zeta")
    recorded = AsyncMock()
    monkeypatch.setattr("app.services.audit_log.AuditLogService.log", recorded)
    await command_receipt(world, "/使用 2", "use-audit")
    await process(world)

    recorded.assert_awaited_once()
    kwargs = recorded.await_args.kwargs
    assert kwargs["action"] == "update_wechat_binding"
    assert kwargs["resource_type"] == "wechat_binding"
    assert kwargs["status"] == "success"
    assert kwargs["metadata"]["agent_id"] == str(second.id)
    assert kwargs["metadata"]["source"] == "wechat_command"
    assert kwargs["metadata"]["purpose"] == "agent"


@pytest.mark.asyncio
async def test_use_by_number_uses_the_shared_web_list_order(world):
    """The number a user typed resolves through the same ordering as /agents."""
    await make_extra_agent(world, "Zeta")
    await make_extra_agent(world, "Alpha")
    await make_extra_agent(world, "Mu")

    listed = agent_names(await available_agents(world.user))
    assert listed == ["Alpha", "Mu", "Test agent", "Zeta"]
    receipt = await command_receipt(world, "/使用 4", "use-order")
    await process(world)

    expected = (await available_agents(world.user))[3]
    assert (await config_for(world)).agent_id == expected.id
    assert expected.name == "Zeta"
    assert (await WeChatAgentReceipt.get(id=receipt.id)).status == "completed"


@pytest.mark.asyncio
@pytest.mark.parametrize("command,argument", [("/use", "  "), ("/使用", "  ")])
async def test_use_tolerates_surrounding_whitespace(world, command, argument):
    second = await make_extra_agent(world, "Zeta")
    receipt = await command_receipt(world, f"{command}{argument}2  ", f"ws-{command}")
    await process(world)

    assert (await config_for(world)).agent_id == second.id
    assert (await WeChatAgentReceipt.get(id=receipt.id)).status == "completed"
    assert await deliveries_for(receipt.id).count() == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text", ["/use2", "/USE 2", "/agents extra", "/agentsx", "/use,2"]
)
async def test_command_lookalikes_stay_ordinary_user_content(world, text):
    receipt = await command_receipt(world, text, f"lookalike-{abs(hash(text))}")
    await process(world)

    assert world.submission.calls, f"{text!r} must not be a command"
    assert world.submission.calls[-1][0] == world.agent.id
    refreshed = await WeChatAgentReceipt.get(id=receipt.id)
    assert refreshed.status == "submitted"
    assert (await config_for(world)).agent_id == world.agent.id


@pytest.mark.asyncio
async def test_legacy_commands_still_work_next_to_selection(world):
    """The new aliases must not shadow the exact legacy command set."""
    await receipt_for(world, text="/help", identifier="legacy-help")
    await process(world)
    assert (
        await WeChatAgentReceipt.get(message_id="legacy-help")
    ).status == "completed"
    assert await WeChatAgentDelivery.filter(
        receipt__message_id="legacy-help", event_key="command"
    ).exists()
    assert not await AgentRun.all().exists()
    assert (await config_for(world)).agent_id == world.agent.id


@pytest.mark.asyncio
async def test_reply_text_failure_rolls_back_the_switch(world, monkeypatch):
    """If the reply cannot be persisted the switch must not stick."""
    second = await make_extra_agent(world, "Zeta")
    before = await generation_of(world)
    receipt = await command_receipt(world, "/使用 2", "use-rollback")

    original = runtime._reply_text

    async def failing_reply(*args, **kwargs):
        await original(*args, **kwargs)
        raise RuntimeError("outbox write failed")

    monkeypatch.setattr(runtime, "_reply_text", failing_reply)
    await process(world)

    assert (await config_for(world)).agent_id == world.agent.id
    assert await generation_of(world) == before
    assert (await WeChatAgentReceipt.get(id=receipt.id)).status == "pending"
    assert await deliveries_for(receipt.id).count() == 0

    monkeypatch.undo()
    await process(world)
    assert (await config_for(world)).agent_id == second.id
    assert (await WeChatAgentReceipt.get(id=receipt.id)).status == "completed"
    assert await deliveries_for(receipt.id).count() == 1
