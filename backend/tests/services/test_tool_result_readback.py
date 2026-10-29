"""Behavior of the model-callable persisted tool-result readback.

The cases use the real ORM so branch, conversation and run scoping are
exercised instead of asserted through call wiring. They never execute a tool:
every input is a pre-existing ``Message`` row.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio
from tortoise.context import TortoiseContext

import app.services.tool_result_readback as readback_module

from app.models.agent import (
    Agent,
    Conversation,
    Message,
    MessageRole,
    MessageRoundRole,
)
from app.models.agent_run import AgentRun, AgentRunMode, AgentRunStatus
from app.models.user import Team, User
from app.services import agent_run_store
from app.services.message_branching import (
    activate_conversation_branch,
    is_message_on_active_branch,
)
from app.services.tool_context import RuntimeToolIdentity, tool_identity_scope
from app.services.tool_result_readback import (
    MAX_WINDOW_CHARS,
    READ_TOOL_RESULT_TOOL,
    build_definition_descriptor,
    build_read_tool_result_schema,
    execute_read_tool_result,
    model_visible_tool_result,
    parse_tool_result_ref,
    read_tool_result,
    tool_result_ref,
)
from app.utils.tool_output import persisted_asset_view_result


@pytest_asyncio.fixture
async def database():
    async with TortoiseContext() as context:
        await context.init(
            db_url="sqlite://:memory:", modules={"models": ["app.models"]}
        )
        await context.generate_schemas()
        yield


async def _seed(*, agent_name: str = "readback-agent"):
    team = await Team.create(id=uuid4(), name=f"team-{uuid4()}")
    owner = await User.create(
        id=uuid4(),
        username=f"owner-{uuid4()}",
        email=f"{uuid4()}@example.test",
        hashed_password="unused",
    )
    other = await User.create(
        id=uuid4(),
        username=f"other-{uuid4()}",
        email=f"{uuid4()}@example.test",
        hashed_password="unused",
    )
    agent = await Agent.create(id=uuid4(), team_id=team.id, name=agent_name)
    conversation = await Conversation.create(
        id=uuid4(), agent_id=agent.id, user_id=owner.id
    )
    return owner, other, agent, conversation


async def _tool_result(
    conversation: Conversation,
    *,
    content: str,
    tool_call_id: str = "call_1",
    round_id=None,
    tool_name: str = "web_search",
    is_active: bool = True,
    round_index: int = 0,
) -> Message:
    return await Message.create(
        id=uuid4(),
        conversation_id=conversation.id,
        role=MessageRole.TOOL,
        content=content,
        tool_call_id=tool_call_id,
        tool_name=tool_name,
        round_id=round_id or uuid4(),
        round_index=round_index,
        round_role=MessageRoundRole.TOOL_RESULT,
        is_round_canonical=False,
        is_active=is_active,
    )


async def _run(conversation: Conversation, owner: User, agent: Agent, round_id):
    return await AgentRun.create(
        id=uuid4(),
        agent_id=agent.id,
        conversation_id=conversation.id,
        user_id=owner.id,
        mode=AgentRunMode.SEND,
        active_round_id=round_id,
    )


@pytest.mark.asyncio
async def test_readback_pagination_reconstructs_the_persisted_text(database):
    owner, _other, agent, conversation = await _seed()
    message = await _tool_result(conversation, content="αβγ😀defghij")
    ref = tool_result_ref(message.round_id, message.tool_call_id)

    first = json.loads(
        await read_tool_result(
            {"ref": ref, "offset": 0, "limit": 4},
            agent=agent,
            user=owner,
            conversation_id=conversation.id,
        )
    )
    second = json.loads(
        await read_tool_result(
            {"ref": ref, "offset": first["next_offset"], "limit": 1000},
            agent=agent,
            user=owner,
            conversation_id=conversation.id,
        )
    )

    assert first["content"] == "αβγ😀"
    assert first["has_more"] is True
    assert first["next_offset"] == 4
    assert first["total_chars"] == len("αβγ😀defghij")
    assert first["ref"] == ref
    assert second["content"] == "defghij"
    assert second["has_more"] is False
    assert second["next_offset"] is None
    assert first["content"] + second["content"] == "αβγ😀defghij"


@pytest.mark.asyncio
async def test_readback_pagination_boundaries_and_numeric_coercion(database):
    owner, _other, agent, conversation = await _seed()
    message = await _tool_result(conversation, content="abcde")
    ref = tool_result_ref(message.round_id, message.tool_call_id)

    at_end = json.loads(
        await read_tool_result(
            {"ref": ref, "offset": 5, "limit": 10},
            agent=agent,
            user=owner,
            conversation_id=conversation.id,
        )
    )
    past_end = json.loads(
        await read_tool_result(
            {"ref": ref, "offset": 99, "limit": 10},
            agent=agent,
            user=owner,
            conversation_id=conversation.id,
        )
    )
    for payload in (at_end, past_end):
        assert payload["content"] == ""
        assert payload["has_more"] is False
        assert payload["next_offset"] is None
        assert payload["total_chars"] == 5

    # JSON numbers arrive as strings from some providers; the page still works.
    coerced = json.loads(
        await read_tool_result(
            {"ref": ref, "offset": "1", "limit": "2"},
            agent=agent,
            user=owner,
            conversation_id=conversation.id,
        )
    )
    assert coerced["content"] == "bc"
    assert coerced["offset"] == 1
    assert coerced["limit"] == 2


@pytest.mark.asyncio
async def test_readback_rejects_fractional_pagination(database):
    owner, _other, agent, conversation = await _seed()
    message = await _tool_result(conversation, content="abcde")
    ref = tool_result_ref(message.round_id, message.tool_call_id)

    for arguments in (
        {"ref": ref, "offset": 1.5},
        {"ref": ref, "limit": 2.5},
    ):
        result = json.loads(
            await read_tool_result(
                arguments,
                agent=agent,
                user=owner,
                conversation_id=conversation.id,
            )
        )
        assert result["error"] == "invalid_pagination"
        assert result["message"] == "offset and limit must be integers"


@pytest.mark.asyncio
async def test_readback_prefers_the_latest_duplicate_result(database):
    owner, _other, agent, conversation = await _seed()
    round_id = uuid4()
    await _tool_result(
        conversation,
        content="older attempt",
        tool_call_id="call_retry",
        round_id=round_id,
        round_index=1,
    )
    await _tool_result(
        conversation,
        content="newest attempt",
        tool_call_id="call_retry",
        round_id=round_id,
        round_index=5,
    )

    payload = json.loads(
        await read_tool_result(
            {"ref": tool_result_ref(round_id, "call_retry")},
            agent=agent,
            user=owner,
            conversation_id=conversation.id,
        )
    )

    assert payload["content"] == "newest attempt"


@pytest.mark.asyncio
async def test_readback_returns_the_model_facing_text_from_persisted_envelopes(
    database,
):
    owner, _other, agent, conversation = await _seed()
    envelope = json.dumps(
        {
            "kind": "tool.result.persisted",
            "version": 1,
            "display": {"rows": [1, 2, 3]},
            "llm_result": "complete model view",
        }
    )
    marker = json.dumps(
        {
            "kind": "asset.view.persisted",
            "version": 1,
            "display": {"kind": "asset.view"},
            "marker": '{"kind":"asset.view","version":1,"ref":"abcd"}',
        }
    )
    envelope_message = await _tool_result(
        conversation, content=envelope, tool_call_id="call_env"
    )
    marker_message = await _tool_result(
        conversation,
        content=marker,
        tool_call_id="call_marker",
        tool_name="view_asset",
    )

    for message, expected in (
        (envelope_message, "complete model view"),
        (
            marker_message,
            '{"kind":"asset.view","version":1,"ref":"abcd"}',
        ),
    ):
        payload = json.loads(
            await read_tool_result(
                {"ref": tool_result_ref(message.round_id, message.tool_call_id)},
                agent=agent,
                user=owner,
                conversation_id=conversation.id,
            )
        )
        assert payload["content"] == expected
        assert payload["tool_name"] == message.tool_name


@pytest.mark.asyncio
async def test_readback_rejects_a_reference_from_another_conversation(database):
    owner, _other, agent, conversation = await _seed()
    # Same owner and agent: only the conversation scope can distinguish them.
    other_conversation = await Conversation.create(
        id=uuid4(), agent_id=agent.id, user_id=owner.id
    )
    foreign = await _tool_result(other_conversation, content="secret payload")

    payload = json.loads(
        await read_tool_result(
            {"ref": tool_result_ref(foreign.round_id, foreign.tool_call_id)},
            agent=agent,
            user=owner,
            conversation_id=conversation.id,
        )
    )

    assert payload == {
        "error": "tool_result_not_found",
        "message": "no completed tool result matches this reference on the active branch",
    }


@pytest.mark.asyncio
async def test_readback_rejects_a_non_owner_before_reading_anything(database):
    owner, other, agent, conversation = await _seed()
    message = await _tool_result(conversation, content="owner data")

    payload = json.loads(
        await read_tool_result(
            {"ref": tool_result_ref(message.round_id, message.tool_call_id)},
            agent=agent,
            user=other,
            conversation_id=conversation.id,
        )
    )

    assert payload["error"] == "access_denied"
    assert "owner data" not in json.dumps(payload)


@pytest.mark.asyncio
async def test_readback_rejects_invalid_conversation_and_actor_contexts(database):
    owner, _other, agent, conversation = await _seed()
    message = await _tool_result(conversation, content="boundary data")
    ref = tool_result_ref(message.round_id, message.tool_call_id)

    # Malformed conversation id, unknown conversation, and an actor without an
    # identity all fail closed before any result lookup.
    for conversation_id in ("not-a-uuid", uuid4()):
        payload = json.loads(
            await read_tool_result(
                {"ref": ref},
                agent=agent,
                user=owner,
                conversation_id=conversation_id,
            )
        )
        assert payload["error"] == "access_denied"
    anonymous = json.loads(
        await read_tool_result(
            {"ref": ref},
            agent=agent,
            user=SimpleNamespace(id=None),
            conversation_id=conversation.id,
        )
    )
    assert anonymous["error"] == "access_denied"

    # A conversation bound to another agent is never readable.
    _owner2, _other2, other_agent, _conversation2 = await _seed()
    mismatch = json.loads(
        await read_tool_result(
            {"ref": ref},
            agent=other_agent,
            user=owner,
            conversation_id=conversation.id,
        )
    )
    assert mismatch["error"] == "access_denied"
    assert "boundary data" not in json.dumps(mismatch)


@pytest.mark.asyncio
async def test_readback_reads_legacy_conversations_without_an_agent(database):
    """Conversations survive agent deletion; ownership still authorizes them."""
    owner, _other, seeded_agent, _seeded_conversation = await _seed()
    agent = await Agent.create(
        id=uuid4(), team_id=seeded_agent.team_id, name="current-agent"
    )
    conversation = await Conversation.create(
        id=uuid4(), agent_id=None, user_id=owner.id
    )
    message = await _tool_result(conversation, content="legacy conversation data")

    payload = json.loads(
        await read_tool_result(
            {"ref": tool_result_ref(message.round_id, message.tool_call_id)},
            agent=agent,
            user=owner,
            conversation_id=conversation.id,
        )
    )

    assert payload["content"] == "legacy conversation data"


@pytest.mark.asyncio
async def test_readback_ignores_an_inactive_side_branch_result(database):
    owner, _other, agent, conversation = await _seed()
    message = await _tool_result(conversation, content="side branch", is_active=False)

    payload = json.loads(
        await read_tool_result(
            {"ref": tool_result_ref(message.round_id, message.tool_call_id)},
            agent=agent,
            user=owner,
            conversation_id=conversation.id,
        )
    )

    assert payload["error"] == "tool_result_not_found"


@pytest.mark.asyncio
async def test_current_round_tool_result_is_visible_to_the_active_branch(database):
    """A just-persisted round step is readable before and after finalization.

    The loop persists assistant steps and tool results as non-canonical rows
    before the next model turn, and only finalizes the canonical assistant
    afterwards. ``is_message_on_active_branch`` must therefore see those rows
    during the run, and branch supersession must still make them unreadable.
    """
    owner, _other, agent, conversation = await _seed()
    round_id = uuid4()
    user_message = await Message.create(
        id=uuid4(),
        conversation_id=conversation.id,
        role=MessageRole.USER,
        content="question",
        round_id=round_id,
        round_index=0,
        round_role=MessageRoundRole.USER_INPUT,
        is_round_canonical=True,
    )
    tool_result = await _tool_result(
        conversation,
        content="live round output",
        tool_call_id="call_live",
        round_id=round_id,
        round_index=1,
    )

    # No branch activation has run yet: the persisted round step defaults to
    # the active branch, exactly as the live loop leaves it.
    assert await is_message_on_active_branch(conversation.id, tool_result.id) is True

    run = await _run(conversation, owner, agent, round_id)
    identity = RuntimeToolIdentity(
        run_id=run.id, entrypoint="agent_run", run_kind="agent"
    )
    with tool_identity_scope(identity):
        live = json.loads(
            await read_tool_result(
                {"tool_call_id": "call_live"},
                agent=agent,
                user=owner,
                conversation_id=conversation.id,
            )
        )
    assert live["content"] == "live round output"

    # End-of-run finalization activates the canonical path; round steps of the
    # assistant-final round stay active.
    assistant = await Message.create(
        id=uuid4(),
        conversation_id=conversation.id,
        role=MessageRole.ASSISTANT,
        content="answer",
        round_id=round_id,
        round_index=2,
        round_role=MessageRoundRole.ASSISTANT_FINAL,
        is_round_canonical=True,
    )
    await activate_conversation_branch(conversation.id, [user_message, assistant])
    assert await is_message_on_active_branch(conversation.id, tool_result.id) is True

    # A later branch switch supersedes the old round, making it unreadable even
    # though the durable run record still points at it.
    new_round = uuid4()
    new_user = await Message.create(
        id=uuid4(),
        conversation_id=conversation.id,
        role=MessageRole.USER,
        content="edited question",
        round_id=new_round,
        round_index=0,
        round_role=MessageRoundRole.USER_INPUT,
        is_round_canonical=True,
    )
    new_assistant = await Message.create(
        id=uuid4(),
        conversation_id=conversation.id,
        role=MessageRole.ASSISTANT,
        content="new answer",
        round_id=new_round,
        round_index=1,
        round_role=MessageRoundRole.ASSISTANT_FINAL,
        is_round_canonical=True,
    )
    await activate_conversation_branch(conversation.id, [new_user, new_assistant])
    assert await is_message_on_active_branch(conversation.id, tool_result.id) is False

    with tool_identity_scope(identity):
        denied = json.loads(
            await read_tool_result(
                {"ref": tool_result_ref(round_id, "call_live")},
                agent=agent,
                user=owner,
                conversation_id=conversation.id,
            )
        )
    assert denied["error"] == "tool_result_not_found"


@pytest.mark.asyncio
async def test_tool_call_id_fallback_is_scoped_to_the_run_active_round(database):
    owner, _other, agent, conversation = await _seed()
    active_round = uuid4()
    run = await _run(conversation, owner, agent, active_round)
    current = await _tool_result(
        conversation,
        content="current round",
        tool_call_id="call_now",
        round_id=active_round,
    )
    older = await _tool_result(
        conversation, content="older round", tool_call_id="call_old", round_id=uuid4()
    )

    identity = RuntimeToolIdentity(
        run_id=run.id, entrypoint="agent_run", run_kind="agent"
    )
    with tool_identity_scope(identity):
        current_payload = json.loads(
            await read_tool_result(
                {"tool_call_id": "call_now"},
                agent=agent,
                user=owner,
                conversation_id=conversation.id,
            )
        )
        older_payload = json.loads(
            await read_tool_result(
                {"tool_call_id": "call_old"},
                agent=agent,
                user=owner,
                conversation_id=conversation.id,
            )
        )
        older_ref_payload = json.loads(
            await read_tool_result(
                {"ref": tool_result_ref(older.round_id, older.tool_call_id)},
                agent=agent,
                user=owner,
                conversation_id=conversation.id,
            )
        )

    assert current_payload["content"] == "current round"
    assert current_payload["ref"] == tool_result_ref(
        current.round_id, current.tool_call_id
    )
    assert older_payload["error"] == "tool_result_not_found"
    assert older_ref_payload["error"] == "tool_result_not_found"


@pytest.mark.asyncio
async def test_tool_call_id_fallback_requires_a_durable_run(database):
    owner, _other, agent, conversation = await _seed()
    await _tool_result(conversation, content="only round")

    payload = json.loads(
        await read_tool_result(
            {"tool_call_id": "call_1"},
            agent=agent,
            user=owner,
            conversation_id=conversation.id,
        )
    )

    assert payload["error"] == "invalid_reference"


@pytest.mark.asyncio
async def test_workflow_run_identity_has_no_persisted_conversation_result(database):
    owner, _other, agent, conversation = await _seed()
    round_id = uuid4()
    message = await _tool_result(
        conversation, content="conversation result", round_id=round_id
    )
    workflow_identity = RuntimeToolIdentity(
        run_id=uuid4(), entrypoint="workflow", run_kind="workflow"
    )

    with tool_identity_scope(workflow_identity):
        payload = json.loads(
            await read_tool_result(
                {"ref": tool_result_ref(message.round_id, message.tool_call_id)},
                agent=agent,
                user=owner,
                conversation_id=conversation.id,
            )
        )

    assert payload["error"] == "tool_result_not_found"


@pytest.mark.asyncio
async def test_readback_run_identity_mismatches_are_unreadable(database):
    owner, _other, agent, conversation = await _seed()
    round_id = uuid4()
    await _tool_result(
        conversation,
        content="scoped run data",
        tool_call_id="call_scoped",
        round_id=round_id,
    )
    ref = tool_result_ref(round_id, "call_scoped")
    _owner2, other2, agent2, conversation2 = await _seed()

    async def create_run(**overrides):
        values = {
            "id": uuid4(),
            "agent_id": agent.id,
            "conversation_id": conversation.id,
            "user_id": owner.id,
            "mode": AgentRunMode.SEND,
            "active_round_id": round_id,
        }
        values.update(overrides)
        return await AgentRun.create(**values)

    identities = {
        "invalid_run_id": RuntimeToolIdentity(
            run_id="not-a-uuid", entrypoint="agent_run"
        ),
        "missing_run": RuntimeToolIdentity(run_id=uuid4(), entrypoint="agent_run"),
        "wrong_conversation": RuntimeToolIdentity(
            run_id=(await create_run(conversation_id=conversation2.id)).id,
            entrypoint="agent_run",
        ),
        "wrong_user": RuntimeToolIdentity(
            run_id=(await create_run(user_id=other2.id)).id,
            entrypoint="agent_run",
        ),
        "wrong_agent": RuntimeToolIdentity(
            run_id=(await create_run(agent_id=agent2.id)).id,
            entrypoint="agent_run",
        ),
        "no_active_round": RuntimeToolIdentity(
            run_id=(await create_run(active_round_id=None)).id,
            entrypoint="agent_run",
        ),
    }

    for name, identity in identities.items():
        with tool_identity_scope(identity):
            by_ref = json.loads(
                await read_tool_result(
                    {"ref": ref},
                    agent=agent,
                    user=owner,
                    conversation_id=conversation.id,
                )
            )
            by_call = json.loads(
                await read_tool_result(
                    {"tool_call_id": "call_scoped"},
                    agent=agent,
                    user=owner,
                    conversation_id=conversation.id,
                )
            )
        assert by_ref["error"] == "tool_result_not_found", name
        assert by_call["error"] == "tool_result_not_found", name


@pytest.mark.asyncio
async def test_known_tool_result_is_rendered_like_replay(database):
    """Plain known-tool rows persisted display JSON, but the model saw text."""
    owner, _other, agent, conversation = await _seed()
    content = json.dumps({"expression": "2+2", "result": 4})
    message = await _tool_result(
        conversation,
        content=content,
        tool_name="calculate",
        tool_call_id="call_calc",
        round_id=uuid4(),
    )

    recovered = json.loads(
        await read_tool_result(
            {"ref": tool_result_ref(message.round_id, message.tool_call_id)},
            agent=agent,
            user=owner,
            conversation_id=conversation.id,
        )
    )

    from app.services.chat_context import summarize_tool_result_for_llm

    assert recovered["content"] == summarize_tool_result_for_llm("calculate", content)
    assert recovered["content"] != content
    assert recovered["content"].startswith("2+2 = 4")


@pytest.mark.asyncio
async def test_approval_resume_persists_the_explicit_model_result(database):
    """A resumed explicit result stores the live loop's model representation.

    Approval resume executes the original call out-of-band. Without the
    ``persistable_model_result`` envelope the row would only hold the display
    payload, so replayed history (which used ``llm_result``) and
    ``read_tool_result`` would disagree with what the model originally saw.
    """
    owner, _other, agent, conversation = await _seed()
    round_id = uuid4()
    run = await _run(conversation, owner, agent, round_id)
    run.status = AgentRunStatus.RUNNING
    await run.save(update_fields=["status"])
    display = json.dumps({"rows": [1, 2, 3]})
    model_text = "complete model view of rows 1-3"

    payload = await agent_run_store.record_resumed_tool_result(
        run.id,
        tool_call_id="call_approved",
        tool_name="custom_lookup",
        tool_display_name="Lookup",
        display_result=display,
        llm_result=model_text,
        is_error=False,
        round_id=round_id,
        round_index=2,
        iteration_index=1,
        explicit=True,
    )

    assert payload is not None
    # API-facing payloads keep the display representation; only the persisted
    # model context gains the envelope.
    assert payload["resume_tool_result"]["result"] == display
    assert payload["history_override"][-1]["content"] == model_text

    message = await Message.get(
        conversation_id=conversation.id, tool_call_id="call_approved"
    )
    envelope = json.loads(message.content)
    assert envelope == {
        "kind": "tool.result.persisted",
        "version": 1,
        "display": {"rows": [1, 2, 3]},
        "llm_result": model_text,
    }

    recovered = json.loads(
        await read_tool_result(
            {"ref": tool_result_ref(round_id, "call_approved")},
            agent=agent,
            user=owner,
            conversation_id=conversation.id,
        )
    )
    assert recovered["content"] == model_text


@pytest.mark.asyncio
async def test_approval_resume_plain_results_stay_byte_identical(database):
    owner, _other, agent, conversation = await _seed()
    round_id = uuid4()
    run = await _run(conversation, owner, agent, round_id)
    run.status = AgentRunStatus.RUNNING
    await run.save(update_fields=["status"])
    display = '{"ok": true}'

    await agent_run_store.record_resumed_tool_result(
        run.id,
        tool_call_id="call_plain",
        tool_name="custom_lookup",
        tool_display_name="Lookup",
        display_result=display,
        llm_result=display,
        is_error=False,
        round_id=round_id,
        round_index=2,
        iteration_index=1,
    )

    message = await Message.get(
        conversation_id=conversation.id, tool_call_id="call_plain"
    )
    assert message.content == display


@pytest.mark.asyncio
async def test_asset_view_resume_persists_the_live_replay_envelope(database):
    """Resumed view_asset rows must keep the native rehydration marker.

    The live loop persists ``{"kind": "asset.view.persisted", "display",
    "marker"}``; replay uses that marker to rebuild native multimodal parts.
    A display-only row would lose them, and ``read_tool_result`` could not
    recreate them from text.
    """
    owner, _other, agent, conversation = await _seed()
    round_id = uuid4()
    run = await _run(conversation, owner, agent, round_id)
    run.status = AgentRunStatus.RUNNING
    await run.save(update_fields=["status"])
    display = {
        "kind": "asset.view",
        "version": 1,
        "ref": "abcd",
        "modality": "image",
    }
    marker = json.dumps(
        {"version": 1, "kind": "asset.view", "ref": "abcd", "modality": "image"}
    )
    persisted = persisted_asset_view_result(display, marker)

    await agent_run_store.record_resumed_tool_result(
        run.id,
        tool_call_id="call_view",
        tool_name="view_asset",
        tool_display_name="View asset",
        display_result=json.dumps(display),
        llm_result=marker,
        is_error=False,
        round_id=round_id,
        round_index=2,
        iteration_index=1,
        persisted_content=persisted,
    )

    message = await Message.get(
        conversation_id=conversation.id, tool_call_id="call_view"
    )
    assert json.loads(message.content) == {
        "kind": "asset.view.persisted",
        "version": 1,
        "display": display,
        "marker": marker,
    }

    recovered = json.loads(
        await read_tool_result(
            {"ref": tool_result_ref(round_id, "call_view")},
            agent=agent,
            user=owner,
            conversation_id=conversation.id,
        )
    )
    assert recovered["content"] == marker


@pytest.mark.asyncio
async def test_unknown_and_malformed_inputs_fail_clearly(database):
    owner, _other, agent, conversation = await _seed()
    message = await _tool_result(conversation, content="data")

    cases = {
        "missing": {},
        "bad_ref": {"ref": "nope"},
        "bad_round": {"ref": f"tr1:not-a-uuid:{message.tool_call_id}"},
        "mismatch": {
            "ref": tool_result_ref(message.round_id, message.tool_call_id),
            "tool_call_id": "other",
        },
        "negative_offset": {
            "ref": tool_result_ref(message.round_id, message.tool_call_id),
            "offset": -1,
        },
        "zero_limit": {
            "ref": tool_result_ref(message.round_id, message.tool_call_id),
            "limit": 0,
        },
    }
    for name, arguments in cases.items():
        payload = json.loads(
            await read_tool_result(
                arguments,
                agent=agent,
                user=owner,
                conversation_id=conversation.id,
            )
        )
        expected = (
            "invalid_pagination"
            if name in {"negative_offset", "zero_limit"}
            else "invalid_reference"
        )
        assert payload["error"] == expected, name

    missing = json.loads(
        await read_tool_result(
            {"ref": tool_result_ref(uuid4(), "absent")},
            agent=agent,
            user=owner,
            conversation_id=conversation.id,
        )
    )
    assert missing["error"] == "tool_result_not_found"


@pytest.mark.asyncio
async def test_readback_rejects_malformed_references_and_pagination(database):
    owner, _other, agent, conversation = await _seed()
    message = await _tool_result(conversation, content="data")
    valid = tool_result_ref(message.round_id, "call_1")

    async def call(arguments):
        return json.loads(
            await read_tool_result(
                arguments,
                agent=agent,
                user=owner,
                conversation_id=conversation.id,
            )
        )

    malformed_references = [
        {"ref": None},
        {"ref": 123},
        {"ref": "x" * 325},
        {"ref": f"tr2:{message.round_id}:call_1"},
        {"ref": f"tr1:{message.round_id}"},
        {"ref": f"tr1:{message.round_id}:"},
        {"ref": f"tr1:{message.round_id}:{'c' * 201}"},
        {"ref": valid, "tool_call_id": 123},
        {"tool_call_id": 123},
        {"tool_call_id": ""},
        {"tool_call_id": "c" * 201},
    ]
    for arguments in malformed_references:
        payload = await call(arguments)
        assert payload["error"] == "invalid_reference", arguments

    assert (await call([]))["error"] == "invalid_reference"

    bad_pagination = [
        {"ref": valid, "offset": True},
        {"ref": valid, "limit": False},
        {"ref": valid, "offset": "abc"},
        {"ref": valid, "limit": "abc"},
        {"ref": valid, "offset": -1},
        {"ref": valid, "limit": 0},
    ]
    for arguments in bad_pagination:
        payload = await call(arguments)
        assert payload["error"] == "invalid_pagination", arguments

    # A model may copy the marker's ``ref=`` prefix verbatim.
    prefixed = await call({"ref": f"ref={valid}"})
    assert prefixed["content"] == "data"


@pytest.mark.asyncio
async def test_limit_is_bounded_but_never_overflows(database):
    owner, _other, agent, conversation = await _seed()
    message = await _tool_result(conversation, content="x" * (MAX_WINDOW_CHARS + 50))

    payload = json.loads(
        await read_tool_result(
            {
                "ref": tool_result_ref(message.round_id, message.tool_call_id),
                "limit": MAX_WINDOW_CHARS + 5000,
            },
            agent=agent,
            user=owner,
            conversation_id=conversation.id,
        )
    )

    assert payload["limit"] == MAX_WINDOW_CHARS
    assert len(payload["content"]) == MAX_WINDOW_CHARS
    assert payload["has_more"] is True
    assert payload["next_offset"] == MAX_WINDOW_CHARS


@pytest.mark.asyncio
async def test_empty_result_and_executor_never_raise(database):
    owner, _other, agent, conversation = await _seed()
    message = await _tool_result(conversation, content="")

    payload = json.loads(
        await execute_read_tool_result(
            {"ref": tool_result_ref(message.round_id, message.tool_call_id)},
            agent=agent,
            user=owner,
            conversation_id=conversation.id,
        )
    )
    assert payload["content"] == ""
    assert payload["total_chars"] == 0
    assert payload["has_more"] is False

    missing = json.loads(
        await execute_read_tool_result(
            {"ref": tool_result_ref(message.round_id, message.tool_call_id)},
            agent=agent,
            user=None,
            conversation_id=conversation.id,
        )
    )
    assert missing["error"] == "access_denied"


def test_reference_round_trip_and_schema_contract():
    round_id = uuid4()
    ref = tool_result_ref(round_id, "call:with:colons")
    assert ref == tool_result_ref(str(round_id), "call:with:colons")
    parsed_round, parsed_call = parse_tool_result_ref(ref)
    assert parsed_round == round_id
    assert parsed_call == "call:with:colons"

    schema = build_read_tool_result_schema()["function"]
    assert schema["name"] == READ_TOOL_RESULT_TOOL
    assert set(schema["parameters"]["properties"]) == {
        "ref",
        "tool_call_id",
        "offset",
        "limit",
    }
    # Real consumer: the durable worker validates the same schema into the
    # provider-facing ToolDefinition before every model turn.
    from app.llm.types import ToolDefinition

    definition = ToolDefinition.model_validate(build_read_tool_result_schema())
    assert definition.function.name == READ_TOOL_RESULT_TOOL
    assert (
        definition.function.parameters["properties"]["limit"]["maximum"]
        == MAX_WINDOW_CHARS
    )

    from app.api.v1.endpoints.chat_tools import _is_policy_managed_tool

    assert _is_policy_managed_tool(READ_TOOL_RESULT_TOOL) is True


def test_unknown_payload_is_returned_byte_identical():
    raw = '{"rows": [1, 2], "cursor": "abc"}'
    assert model_visible_tool_result(raw) == raw
    assert model_visible_tool_result(None) == ""


@pytest.mark.asyncio
async def test_execute_readback_contains_unexpected_failures(monkeypatch):
    async def boom(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(readback_module, "read_tool_result", boom)

    payload = json.loads(
        await execute_read_tool_result({}, agent=None, user=None, conversation_id=None)
    )

    assert payload["error"] == "tool_execution_failed"


def test_reference_builder_rejects_unusable_inputs():
    round_id = uuid4()
    for bad in (None, "", True):
        with pytest.raises(ValueError):
            tool_result_ref(round_id, bad)
    with pytest.raises(ValueError):
        tool_result_ref(round_id, "c" * 201)
    with pytest.raises(ValueError):
        tool_result_ref("not-a-uuid", "call")
    assert tool_result_ref(round_id, 123).endswith(":123")


def test_reference_parser_rejects_unusable_inputs():
    round_id = uuid4()
    for bad in (
        None,
        123,
        "",
        "x" * 325,
        "ref=",
        f"tr2:{round_id}:call",
        f"tr1:{round_id}",
        f"tr1:{round_id}:",
        f"tr1:{round_id}:{'c' * 201}",
    ):
        with pytest.raises(ValueError):
            parse_tool_result_ref(bad)


def test_model_visible_result_edge_cases():
    from app.services.chat_context import summarize_tool_result_for_llm
    from app.utils.tool_output import render_tool_output

    assert model_visible_tool_result(123) == ""
    assert model_visible_tool_result("") == ""
    assert model_visible_tool_result("plain text", "calculate") == "plain text"
    assert model_visible_tool_result("[1, 2]", "calculate") == "[1, 2]"
    assert model_visible_tool_result("{bad json", "calculate") == "{bad json"

    error_payload = '{"error": "boom"}'
    assert model_visible_tool_result(error_payload, "calculate") == render_tool_output(
        "calculate", {"error": "boom"}
    )

    # A malformed or version-mismatched asset envelope is not treated as a
    # marker; it falls back to the same replay rendering as any known tool.
    unusable_marker = json.dumps(
        {
            "kind": "asset.view.persisted",
            "version": 1,
            "display": {"kind": "asset.view"},
            "marker": 123,
        }
    )
    version_mismatch = json.dumps(
        {
            "kind": "asset.view.persisted",
            "version": 2,
            "display": {},
            "marker": "m",
        }
    )
    for payload in (unusable_marker, version_mismatch):
        assert model_visible_tool_result(
            payload, "view_asset"
        ) == summarize_tool_result_for_llm("view_asset", payload)

    # Malformed generic envelopes also fall back instead of being trusted.
    bad_generic = [
        json.dumps(
            {
                "kind": "tool.result.persisted",
                "version": 2,
                "display": {},
                "llm_result": "model text",
            }
        ),
        json.dumps(
            {
                "kind": "tool.result.persisted",
                "version": 1,
                "display": {},
                "llm_result": 123,
            }
        ),
    ]
    for payload in bad_generic:
        assert model_visible_tool_result(
            payload, "calculate"
        ) == summarize_tool_result_for_llm("calculate", payload)


def test_definition_descriptor_matches_the_stored_tool_contract():
    descriptor = build_definition_descriptor()
    function = build_read_tool_result_schema()["function"]

    assert descriptor["name"] == READ_TOOL_RESULT_TOOL
    assert descriptor["description"] == function["description"]
    # get_builtin_definition expects the legacy parameter-descriptor list.
    assert descriptor["parameters"] == []
    assert descriptor["definition_version"] == 1


def test_resumed_result_persistence_follows_the_live_loop():
    from app.api.v1.endpoints.chat_tools import AssetViewResult
    from app.services.agent_run_worker import _resumed_result_persistence
    from app.utils.tool_output import ToolExecutionResult

    asset = AssetViewResult(
        display_result={"kind": "asset.view", "ref": "abcd"},
        llm_result='{"kind":"asset.view","ref":"abcd"}',
    )
    explicit, persisted = _resumed_result_persistence(asset)
    assert explicit is False
    envelope = json.loads(persisted)
    assert envelope == {
        "kind": "asset.view.persisted",
        "version": 1,
        "display": {"kind": "asset.view", "ref": "abcd"},
        "marker": '{"kind":"asset.view","ref":"abcd"}',
    }

    explicit, persisted = _resumed_result_persistence(
        ToolExecutionResult(display_result={"rows": [1]}, llm_result="model text")
    )
    assert explicit is True
    assert persisted is None

    assert _resumed_result_persistence('{"ok": true}') == (False, None)


def test_resumed_result_content_follows_the_persistence_contract():
    display = '{"rows": [1, 2]}'
    model_text = "model view of two rows"

    # Plain results (no explicit model representation) stay byte-identical.
    assert (
        agent_run_store.persisted_tool_result_content(
            "custom_lookup", display, display, explicit=False
        )
        == display
    )
    # Explicit results are wrapped exactly like the live loop wraps them.
    wrapped = json.loads(
        agent_run_store.persisted_tool_result_content(
            "custom_lookup", display, model_text, explicit=True
        )
    )
    assert wrapped == {
        "kind": "tool.result.persisted",
        "version": 1,
        "display": {"rows": [1, 2]},
        "llm_result": model_text,
    }
    # An already-persisted payload is never double-wrapped.
    already = json.dumps(wrapped)
    assert (
        agent_run_store.persisted_tool_result_content(
            "custom_lookup", already, model_text, explicit=True
        )
        == already
    )
