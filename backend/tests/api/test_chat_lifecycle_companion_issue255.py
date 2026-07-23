from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.api.v1.endpoints import chat
from app.models.agent import MessageRole, MessageRoundRole, MessageRoundStatus


class _Query:
    def __init__(self, *, rows=None, count=0):
        self.rows = rows or []
        self.value = count

    def order_by(self, *_args):
        return self

    async def all(self):
        return self.rows

    async def count(self):
        return self.value

    async def update(self, **_kwargs):
        return 1


def _message(**overrides):
    values = {
        "id": uuid4(),
        "conversation_id": uuid4(),
        "role": MessageRole.ASSISTANT,
        "content": "answer",
        "tool_calls": None,
        "tool_call_id": None,
        "tool_name": None,
        "reasoning_content": None,
        "model_used": None,
        "token_usage": None,
        "duration_ms": None,
        "first_token_ms": None,
        "is_manually_stopped": False,
        "rag_context": None,
        "created_at": datetime.now(UTC),
        "round_id": None,
        "round_index": 0,
        "round_role": None,
        "is_round_canonical": True,
        "iteration_index": None,
        "round_status": None,
        "parent_id": None,
        "is_active": True,
        "version_number": 1,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.anyio
async def test_round_steps_skip_query_without_canonical_rounds():
    message_model = MagicMock()

    with patch.object(chat, "Message", message_model):
        result = await chat.build_round_steps_map([_message()])

    assert result == {}
    message_model.filter.assert_not_called()


@pytest.mark.anyio
async def test_round_steps_group_trace_fields_and_optional_enums():
    round_id = uuid4()
    canonical = _message(round_id=round_id)
    step = _message(
        round_id=round_id,
        is_round_canonical=False,
        round_index=2,
        round_role=MessageRoundRole.TOOL_RESULT,
        round_status=MessageRoundStatus.COMPLETED,
        iteration_index=1,
        tool_call_id="call-1",
        tool_name="lookup",
    )
    message_model = MagicMock()
    message_model.filter.return_value = _Query(rows=[step])

    with patch.object(chat, "Message", message_model):
        result = await chat.build_round_steps_map([canonical])

    assert result[round_id][0]["round_role"] == "tool_result"
    assert result[round_id][0]["round_status"] == "completed"
    assert result[round_id][0]["tool_call_id"] == "call-1"
    message_model.filter.assert_called_once_with(
        conversation_id=canonical.conversation_id,
        is_active=True,
        round_id__in=[round_id],
        is_round_canonical=False,
    )


@pytest.mark.anyio
async def test_round_payloads_skip_steps_and_nest_them_under_final_message():
    round_id = uuid4()
    user = _message(role=MessageRole.USER)
    step = _message(round_id=round_id, is_round_canonical=False)
    final = _message(
        round_id=round_id,
        round_role=MessageRoundRole.ASSISTANT_FINAL,
    )
    serialized = iter(
        [
            SimpleNamespace(model_dump=lambda: {"id": user.id}),
            SimpleNamespace(model_dump=lambda: {"id": final.id}),
        ]
    )
    message_out = MagicMock()
    message_out.model_validate.side_effect = lambda _message: next(serialized)

    with (
        patch.object(
            chat,
            "build_round_steps_map",
            AsyncMock(return_value={round_id: [{"id": step.id}]}),
        ),
        patch.object(chat, "MessageOut", message_out),
    ):
        result = await chat.build_message_round_payloads([user, step, final])

    assert result == [
        {"id": user.id},
        {"id": final.id, "steps": [{"id": step.id}]},
    ]
    assert message_out.model_validate.call_count == 2


@pytest.mark.anyio
async def test_version_output_and_stats_cover_full_lifecycle_payload():
    round_id = uuid4()
    parent_id = uuid4()
    message = _message(
        parent_id=parent_id,
        round_id=round_id,
        round_role=MessageRoundRole.ASSISTANT_FINAL,
        round_status=MessageRoundStatus.COMPLETED,
    )
    versions = [
        chat.MessageVersion(
            id=parent_id,
            version_number=1,
            is_active=False,
            content="original",
            created_at=datetime.now(UTC),
        ),
        chat.MessageVersion(
            id=message.id,
            version_number=2,
            is_active=True,
            content=message.content,
            created_at=message.created_at,
        ),
    ]
    agent = SimpleNamespace(id=uuid4(), team=SimpleNamespace(id=uuid4()))
    message_filter = MagicMock(return_value=_Query(count=1))
    agent_filter = MagicMock(return_value=_Query())
    team_filter = MagicMock(return_value=_Query())

    with (
        patch.object(chat.Message, "filter", message_filter),
        patch.object(
            chat, "get_message_versions", AsyncMock(return_value=versions)
        ) as get_versions,
        patch.object(chat.Agent, "filter", agent_filter),
        patch.object(chat.Team, "filter", team_filter),
    ):
        output = await chat.build_message_out_with_versions(
            message, include_versions=True
        )
        await chat.update_message_stats(agent, {"prompt": 3, "completion": None})

    assert output.version_count == 2
    assert output.versions == versions
    assert output.round_role == "assistant_final"
    assert output.round_status == "completed"
    get_versions.assert_awaited_once_with(message)
    message_filter.assert_called_once_with(parent_id=parent_id)
    agent_filter.assert_called_once_with(id=agent.id)
    team_filter.assert_called_once_with(id=agent.team.id)
