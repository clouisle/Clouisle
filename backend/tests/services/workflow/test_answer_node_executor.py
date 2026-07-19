"""Behavioral tests for the answer node executor."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.workflow.executors.answer import AnswerNodeExecutor
from app.services.workflow.lazy_stream import LazyStreamResult


@pytest.mark.asyncio
async def test_configured_outputs_are_streamed_and_concatenated():
    context = MagicMock()
    context.run_id = "run-1"
    context.get_node_outputs = AsyncMock(return_value={})
    context.resolve_variable_ref = AsyncMock(
        side_effect=["first", {"status": "done"}, None]
    )
    publish_token = AsyncMock()
    node = {
        "id": "answer-1",
        "data": {
            "answerConfig": {
                "outputs": [
                    {"sourceVariable": "{{node.first}}"},
                    {"sourceVariable": "{{node.second}}"},
                    {"sourceVariable": "{{node.empty}}"},
                ]
            }
        },
    }

    with patch(
        "app.services.workflow.stream.StreamManager.publish_token", publish_token
    ):
        result = await AnswerNodeExecutor().execute(node, context, MagicMock())

    assert result.outputs == {"answer": 'first\n{"status": "done"}'}
    assert [call.args for call in publish_token.await_args_list] == [
        ("answer-1", "first"),
        ("answer-1", "\n"),
        ("answer-1", '{"status": "done"}'),
        ("answer-1", "\n"),
    ]


@pytest.mark.asyncio
async def test_missing_and_empty_sources_are_skipped():
    context = MagicMock()
    context.run_id = "run-1"
    context.get_node_outputs = AsyncMock(return_value={})
    context.resolve_variable_ref = AsyncMock(return_value="")
    publish_token = AsyncMock()
    node = {
        "id": "answer-1",
        "data": {
            "answerConfig": {
                "outputs": [{}, {"sourceVariable": ""}, {"sourceVariable": "plain"}]
            }
        },
    }

    with patch(
        "app.services.workflow.stream.StreamManager.publish_token", publish_token
    ):
        result = await AnswerNodeExecutor().execute(node, context, MagicMock())

    assert result.outputs == {"answer": ""}
    context.resolve_variable_ref.assert_awaited_once_with("plain")
    publish_token.assert_not_awaited()


@pytest.mark.asyncio
async def test_legacy_template_and_variables_are_combined():
    context = MagicMock()
    context.run_id = "run-1"
    context.resolve_variable_ref = AsyncMock(
        side_effect=lambda ref: {
            "{{name}}": "Alice",
            "{{missing}}": None,
            "{{count}}": 2,
            "{{empty}}": None,
        }[ref]
    )
    node = {
        "id": "answer-1",
        "data": {
            "config": {
                "answerTemplate": "Hello {{name}} / {{missing}}",
                "variables": [
                    {"name": "count", "variableRef": "{{count}}"},
                    {"name": "empty", "variableRef": "{{empty}}"},
                ],
            }
        },
    }

    result = await AnswerNodeExecutor().execute(node, context, MagicMock())

    assert result.outputs == {"answer": "Hello Alice / {{missing}}\n2"}


@pytest.mark.asyncio
async def test_lazy_output_resolves_with_answer_stream_target():
    lazy = LazyStreamResult("model", [], 0.5, None, 1.0)
    context = MagicMock()
    context.run_id = "run-1"
    context.get_node_outputs = AsyncMock(return_value={"response": lazy})
    context.resolve_variable_ref = AsyncMock(return_value="streamed response")
    node = {
        "id": "answer-1",
        "data": {"answerConfig": {"outputs": [{"sourceVariable": "{{llm.response}}"}]}},
    }

    result = await AnswerNodeExecutor().execute(node, context, MagicMock())

    assert result.outputs == {"answer": "streamed response"}
    context.resolve_variable_ref.assert_awaited_once_with(
        "{{llm.response}}", stream_to_node_id="answer-1"
    )


@pytest.mark.asyncio
async def test_missing_node_output_is_not_lazy():
    context = MagicMock()
    context.get_node_outputs = AsyncMock(return_value=None)

    assert (
        await AnswerNodeExecutor._is_lazy_variable("{{llm.response}}", context) is False
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "source_variable",
    ["plain", "{{single}}", "{{sys.query}}", "{{conversation.id}}"],
)
async def test_non_node_references_are_not_lazy(source_variable):
    context = MagicMock()
    context.get_node_outputs = AsyncMock()

    assert await AnswerNodeExecutor._is_lazy_variable(source_variable, context) is False
    context.get_node_outputs.assert_not_awaited()


@pytest.mark.asyncio
async def test_output_metadata_is_answer_string():
    executor = AnswerNodeExecutor()

    assert executor.get_output_variables({}) == [{"name": "answer", "type": "string"}]
    specs = executor.get_output_specs({})
    assert len(specs) == 1
    assert specs[0].name == "answer"
    assert specs[0].type.kind == "string"
