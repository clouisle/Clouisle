from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import chat
from app.llm.errors import LLMError
from app.llm.types import ChatResponse as ModelResponse
from app.llm.types import FunctionCall, Message, ToolCall, Usage
from app.models.agent import MessageRoundStatus, RAGMode
from app.schemas.agent import ChatRequest, FileUrl, ImageContent
from app.schemas.response import BusinessError, ResponseCode


class UpdateQuery:
    def __init__(self):
        self.update = AsyncMock(return_value=1)


def stored_message(**values):
    defaults = {
        "id": uuid4(),
        "conversation_id": values["conversation"].id,
        "images": None,
        "file_urls": None,
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
        "created_at": datetime.now(timezone.utc),
        "round_id": None,
        "round_index": 0,
        "round_role": None,
        "is_round_canonical": False,
        "iteration_index": None,
        "round_status": None,
        "parent_id": None,
        "branch_parent_id": None,
        "is_active": True,
        "version_number": 1,
        "save": AsyncMock(),
    }
    defaults.update(values)
    defaults.pop("conversation")
    return SimpleNamespace(**defaults)


async def setup_chat(monkeypatch, *, max_iterations=3, rag_mode=RAGMode.OFF):
    user = SimpleNamespace(id=uuid4(), is_active=True, locale="en")
    team_id = uuid4()
    agent = SimpleNamespace(
        id=uuid4(),
        team_id=team_id,
        team=SimpleNamespace(id=team_id),
        rag_mode=rag_mode,
        max_iterations=max_iterations,
        enable_vision=True,
        enable_user_input_request=False,
    )
    conversation = SimpleNamespace(id=uuid4(), title=None)
    created = []

    async def create_message(**values):
        result = stored_message(**values)
        created.append(result)
        return result

    conversation_query = UpdateQuery()
    agent_query = UpdateQuery()
    prepared = SimpleNamespace(
        messages=[Message(role="user", content="prepared prompt")]
    )

    monkeypatch.setattr(chat.deps, "check_api_key_agent_access", AsyncMock())
    monkeypatch.setattr(chat, "check_agent_chat_access", AsyncMock(return_value=agent))
    monkeypatch.setattr(
        chat, "get_or_create_conversation", AsyncMock(return_value=conversation)
    )
    monkeypatch.setattr(
        chat, "get_next_user_branch_parent_id", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(chat.Message, "create", AsyncMock(side_effect=create_message))
    monkeypatch.setattr(chat, "update_message_stats", AsyncMock())
    monkeypatch.setattr(
        chat,
        "get_agent_chat_model",
        AsyncMock(
            return_value=SimpleNamespace(
                model=SimpleNamespace(
                    provider="stub",
                    model_id="unit-model",
                    capabilities={"vision": True},
                    context_length=8192,
                    max_output_tokens=1024,
                )
            )
        ),
    )
    monkeypatch.setattr(
        chat, "get_streaming_config", lambda _agent: {"tool_timeouts": {}}
    )
    monkeypatch.setattr(
        "app.services.sandbox.gateway.sandbox_gateway.create_session",
        AsyncMock(return_value="sandbox-session"),
    )
    monkeypatch.setattr(
        chat,
        "build_file_content_for_context",
        AsyncMock(return_value=("parsed attachment", [{"filename": "notes.txt"}])),
    )
    monkeypatch.setattr(
        chat, "get_visible_conversation_messages", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(
        chat,
        "collect_conversation_images",
        lambda *_args, **_kwargs: ([{"url": "old.png"}], [{"url": "old.png"}]),
    )
    monkeypatch.setattr(
        chat,
        "append_conversation_image_inventory",
        lambda text, inventory: f"{text}\nimages={len(inventory)}",
    )
    monkeypatch.setattr(chat, "get_agent_tools", AsyncMock(return_value=[]))
    monkeypatch.setattr(chat, "get_tool_display_names", AsyncMock(return_value={}))
    monkeypatch.setattr(chat, "prepare_model_context", AsyncMock(return_value=prepared))
    monkeypatch.setattr(
        chat.Conversation, "filter", lambda **_kwargs: conversation_query
    )
    monkeypatch.setattr(chat.Agent, "filter", lambda **_kwargs: agent_query)
    monkeypatch.setattr(chat, "get_prefix_path_before", AsyncMock(return_value=[]))
    monkeypatch.setattr(chat, "activate_conversation_branch", AsyncMock())
    monkeypatch.setattr(chat, "persist_macro_summary_best_effort", AsyncMock())
    monkeypatch.setattr(chat, "enqueue_session_memory_extraction", Mock())
    monkeypatch.setattr(chat, "append_generated_images", Mock())

    return SimpleNamespace(
        user=user,
        agent=agent,
        conversation=conversation,
        created=created,
        prepared=prepared,
        conversation_query=conversation_query,
        agent_query=agent_query,
    )


def model_response(*, content="answer", tool_calls=None, prompt=3, completion=2):
    return ModelResponse(
        id=str(uuid4()),
        model="stub/unit-model",
        content=content,
        reasoning_content="reasoning",
        tool_calls=tool_calls,
        finish_reason="tool_calls" if tool_calls else "stop",
        usage=Usage(
            prompt_tokens=prompt,
            completion_tokens=completion,
            total_tokens=prompt + completion,
        ),
    )


@pytest.mark.anyio
async def test_chat_persists_rag_attachments_and_completed_round(monkeypatch):
    state = await setup_chat(monkeypatch, rag_mode=RAGMode.AUTO)
    rag = [{"content": "raw context", "score": 0.8}]
    monkeypatch.setattr(chat, "perform_rag_retrieval", AsyncMock(return_value=rag))
    monkeypatch.setattr(chat, "aggregate_rag_contexts", Mock(return_value=rag))
    monkeypatch.setattr(chat, "build_rag_prompt", Mock(return_value="grounded prompt"))
    provider = AsyncMock(return_value=model_response())
    monkeypatch.setattr("app.llm.model_manager.team_chat", provider)
    request = ChatRequest(
        message="explain the notes",
        images=[ImageContent(url="current.png")],
        file_urls=[
            FileUrl(
                filename="notes.txt",
                url="https://files.test/notes.txt",
                size=10,
                mime_type="text/plain",
            )
        ],
    )

    result = await chat.chat(state.agent.id, request, (state.user, None))

    user_message, assistant = state.created
    assert user_message.content == "explain the notes"
    assert user_message.rag_context == rag
    assert user_message.images == [{"type": "image_url", "url": "current.png"}]
    assert user_message.file_urls == [{"filename": "notes.txt"}]
    user_message.save.assert_awaited_once_with(update_fields=["file_urls"])
    assert assistant.content == "answer"
    assert assistant.token_usage == {"prompt": 3, "completion": 2}
    assert assistant.round_status == MessageRoundStatus.COMPLETED
    assert result["data"].usage == {
        "prompt_tokens": 3,
        "completion_tokens": 2,
        "total_tokens": 5,
    }
    chat.activate_conversation_branch.assert_awaited_once_with(
        state.conversation.id, [user_message, assistant]
    )
    chat.persist_macro_summary_best_effort.assert_awaited_once()
    chat.enqueue_session_memory_extraction.assert_called_once_with(
        state.agent, state.conversation, assistant
    )
    provider_message = provider.await_args.kwargs["messages"][0]
    assert provider_message["role"] == "user"
    assert provider_message["content"] == "prepared prompt"


@pytest.mark.anyio
async def test_chat_executes_tool_round_and_aggregates_usage(monkeypatch):
    state = await setup_chat(monkeypatch)
    tool_call = ToolCall(
        id="call-1",
        function=FunctionCall(name="lookup", arguments="not-json"),
    )
    provider = AsyncMock(
        side_effect=[
            model_response(
                content="checking", tool_calls=[tool_call], prompt=4, completion=1
            ),
            model_response(content="final answer", prompt=2, completion=3),
        ]
    )
    monkeypatch.setattr("app.llm.model_manager.team_chat", provider)
    monkeypatch.setattr(
        chat,
        "get_agent_tools",
        AsyncMock(
            return_value=[
                {
                    "function": {
                        "name": "lookup",
                        "description": "Look up data",
                        "parameters": {"type": "object"},
                    }
                }
            ]
        ),
    )
    monkeypatch.setattr(
        chat, "get_tool_display_names", AsyncMock(return_value={"lookup": "Lookup"})
    )
    execute = AsyncMock(return_value={"answer": 42})
    monkeypatch.setattr(chat, "execute_tool_call", execute)
    monkeypatch.setattr(
        chat, "get_tool_execution_payloads", lambda result: (result, "tool says 42")
    )

    result = await chat.chat(
        state.agent.id, ChatRequest(message="use the tool"), (state.user, None)
    )

    user_message, assistant_step, tool_result, assistant = state.created
    assert assistant_step.tool_calls[0] == {
        "id": "call-1",
        "name": "lookup",
        "display_name": "Lookup",
        "arguments": {},
    }
    assert assistant_step.is_round_canonical is False
    assert tool_result.content == {"answer": 42}
    assert tool_result.tool_call_id == "call-1"
    assert assistant.content == "final answer"
    assert assistant.token_usage == {"prompt": 6, "completion": 4}
    assert result["data"].usage["total_tokens"] == 10
    execute.assert_awaited_once_with(
        "lookup",
        {},
        agent=state.agent,
        tool_timeouts={},
        user=state.user,
        session_id="sandbox-session",
        current_images=[{"url": "old.png"}],
    )
    second_context = chat.prepare_model_context.await_args_list[1].kwargs
    assert [entry["role"] for entry in second_context["history_override"]] == [
        "assistant",
        "tool",
    ]
    assert provider.await_count == 2
    chat.activate_conversation_branch.assert_awaited_once_with(
        state.conversation.id, [user_message, assistant]
    )


@pytest.mark.anyio
async def test_chat_persists_iteration_cap_as_terminal_round(monkeypatch):
    state = await setup_chat(monkeypatch, max_iterations=1)
    tool_call = ToolCall(
        id="call-1", function=FunctionCall(name="lookup", arguments="{}")
    )
    monkeypatch.setattr(
        "app.llm.model_manager.team_chat",
        AsyncMock(return_value=model_response(tool_calls=[tool_call])),
    )
    monkeypatch.setattr(chat, "execute_tool_call", AsyncMock(return_value="result"))
    monkeypatch.setattr(
        chat, "get_tool_execution_payloads", lambda result: (result, result)
    )
    monkeypatch.setattr(
        chat, "build_max_iterations_terminal_content", lambda locale: f"limit:{locale}"
    )

    await chat.chat(
        state.agent.id, ChatRequest(message="loop forever"), (state.user, None)
    )

    final_message = state.created[-1]
    assert final_message.content == "limit:en"
    assert final_message.reasoning_content is None
    assert final_message.round_status == MessageRoundStatus.MAX_ITERATIONS_REACHED
    assert final_message.tool_calls is None
    assert state.created[1].tool_calls == [
        {
            "id": "call-1",
            "name": "lookup",
            "display_name": "lookup",
            "arguments": {},
        }
    ]


@pytest.mark.anyio
async def test_chat_maps_provider_failure_without_final_persistence(monkeypatch):
    state = await setup_chat(monkeypatch)
    monkeypatch.setattr(
        "app.llm.model_manager.team_chat", AsyncMock(side_effect=LLMError("offline"))
    )

    with pytest.raises(BusinessError) as error:
        await chat.chat(
            state.agent.id, ChatRequest(message="hello"), (state.user, None)
        )

    assert error.value.code == ResponseCode.UNKNOWN_ERROR
    assert error.value.msg_key == "llm_processing_failed"
    assert error.value.status_code == 500
    assert len(state.created) == 1
    chat.activate_conversation_branch.assert_not_awaited()
    chat.persist_macro_summary_best_effort.assert_not_awaited()
