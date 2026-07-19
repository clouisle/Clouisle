"""Behavioral coverage for the answer workflow node executor."""

from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from app.services.workflow.context import ExecutionContext
from app.services.workflow.executors.answer import AnswerNodeExecutor


class TestAnswerNodeExecutor:
    @pytest.mark.asyncio
    async def test_configured_outputs_are_streamed_and_concatenated(self):
        context = MagicMock(spec=ExecutionContext)
        context.run_id = "run-1"
        context.get_node_outputs = AsyncMock(return_value=None)
        context.resolve_variable_ref = AsyncMock(side_effect=["first", 2])
        stream_manager = MagicMock()
        stream_manager.publish_token = AsyncMock()

        node = {
            "id": "answer-1",
            "data": {
                "answerConfig": {
                    "outputs": [
                        {"sourceVariable": "{{upstream.first}}"},
                        {"sourceVariable": "{{upstream.second}}"},
                    ]
                }
            },
        }

        with patch(
            "app.services.workflow.stream.StreamManager", return_value=stream_manager
        ):
            result = await AnswerNodeExecutor().execute(node, context, MagicMock())

        assert result.outputs == {"answer": "first\n2"}
        assert stream_manager.publish_token.await_args_list == [
            call("answer-1", "first"),
            call("answer-1", "\n"),
            call("answer-1", "2"),
        ]

    @pytest.mark.asyncio
    async def test_missing_or_empty_sources_are_skipped(self):
        context = MagicMock(spec=ExecutionContext)
        context.run_id = "run-1"
        context.get_node_outputs = AsyncMock()
        context.resolve_variable_ref = AsyncMock()
        stream_manager = MagicMock()
        stream_manager.publish_token = AsyncMock()

        node = {
            "id": "answer-1",
            "data": {
                "answerConfig": {
                    "outputs": [{"sourceVariable": ""}, {}],
                }
            },
        }

        with patch(
            "app.services.workflow.stream.StreamManager", return_value=stream_manager
        ):
            result = await AnswerNodeExecutor().execute(node, context, MagicMock())

        assert result.outputs == {"answer": ""}
        context.get_node_outputs.assert_not_awaited()
        context.resolve_variable_ref.assert_not_awaited()
        stream_manager.publish_token.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_legacy_template_and_variables_are_combined(self):
        executor = AnswerNodeExecutor()
        executor.resolve_inputs = AsyncMock(return_value={"score": 42})
        context = MagicMock(spec=ExecutionContext)
        context.run_id = "run-1"
        context.resolve_variable_ref = AsyncMock(return_value="Ada")

        node = {
            "id": "answer-1",
            "data": {
                "config": {
                    "answerTemplate": "Hello {{name}}",
                    "variables": [{"name": "score", "value": "{{upstream.score}}"}],
                }
            },
        }

        with patch("app.services.workflow.stream.StreamManager"):
            result = await executor.execute(node, context, MagicMock())

        assert result.outputs == {"answer": "Hello Ada\n42"}
        context.resolve_variable_ref.assert_awaited_once_with("{{name}}")
        executor.resolve_inputs.assert_awaited_once_with(
            context, [{"name": "score", "value": "{{upstream.score}}"}]
        )
