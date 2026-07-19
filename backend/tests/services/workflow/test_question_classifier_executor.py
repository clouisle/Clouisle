from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.model import Model, TeamModel
from app.services.workflow.context import ExecutionContext
from app.services.workflow.executors.condition import QuestionClassifierNodeExecutor


CATEGORIES = [
    {"id": "tech", "name": "Technical Support", "description": "Technical issues"},
    {"id": "billing", "name": "Billing", "description": "Payment questions"},
]


def query(first):
    result = MagicMock()
    result.prefetch_related.return_value = result
    result.first = AsyncMock(return_value=first)
    return result


def context(input_value="How do I pay?"):
    result = MagicMock(spec=ExecutionContext)
    result.resolve_variable_ref = AsyncMock(return_value=input_value)
    result.set_branch = AsyncMock()
    return result


def node(config):
    return {
        "id": "classifier-1",
        "data": {"questionClassifierConfig": config},
    }


class TestQuestionClassifierNodeExecutor:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("config", "input_value"),
        [({}, "question"), ({"modelId": "team-model"}, "")],
    )
    async def test_rejects_missing_model_or_input(self, config, input_value):
        execution_context = context(input_value)

        result = await QuestionClassifierNodeExecutor().execute(
            node(config), execution_context, MagicMock()
        )

        assert result.error == "validation_error"
        execution_context.set_branch.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_returns_model_not_found_after_legacy_model_fallback(self):
        execution_context = context()

        with (
            patch.object(TeamModel, "filter", return_value=query(None)) as team_filter,
            patch.object(Model, "filter", return_value=query(None)) as model_filter,
        ):
            result = await QuestionClassifierNodeExecutor().execute(
                node({"modelId": "missing", "sourceVariable": "{{start.query}}"}),
                execution_context,
                MagicMock(),
            )

        assert result.error == "model_not_found"
        team_filter.assert_called_once_with(id="missing")
        model_filter.assert_called_once_with(id="missing")

    @pytest.mark.asyncio
    async def test_parses_embedded_json_and_category_name_for_team_model(self):
        execution_context = context()
        team_model = SimpleNamespace(model=SimpleNamespace(id="model-1"))
        response = SimpleNamespace(
            content='Result: {"category":"Billing","confidence":0.9,"reasoning":"payment"}'
        )
        config = {
            "modelId": "team-model-1",
            "sourceVariable": "{{start.query}}",
            "categories": CATEGORIES,
            "instruction": "Prefer billing for payment questions.",
        }

        with (
            patch.object(TeamModel, "filter", return_value=query(team_model)),
            patch(
                "app.llm.model_manager.chat", new=AsyncMock(return_value=response)
            ) as chat,
        ):
            result = await QuestionClassifierNodeExecutor().execute(
                node(config), execution_context, MagicMock()
            )

        assert result.outputs == {
            "category": "billing",
            "confidence": 0.9,
            "reasoning": "payment",
        }
        assert result.next_handles == ["billing"]
        execution_context.resolve_variable_ref.assert_awaited_once_with(
            "{{start.query}}"
        )
        execution_context.set_branch.assert_awaited_once_with("classifier-1", "billing")
        call = chat.await_args.kwargs
        assert call["model_id"] == "model-1"
        assert (
            "Additional instructions:\nPrefer billing" in call["messages"][0]["content"]
        )
        assert call["messages"][1] == {"role": "user", "content": "How do I pay?"}

    @pytest.mark.asyncio
    async def test_uses_legacy_config_model_and_plain_text_fallback(self):
        execution_context = context("The server is unavailable")
        response = SimpleNamespace(content="This is a TECHNICAL SUPPORT request")
        legacy_node = {
            "id": "classifier-1",
            "data": {
                "config": {
                    "modelId": "model-2",
                    "inputVariable": "{{legacy.input}}",
                    "categories": CATEGORIES,
                }
            },
        }

        with (
            patch.object(TeamModel, "filter", return_value=query(None)),
            patch.object(
                Model, "filter", return_value=query(SimpleNamespace(id="model-2"))
            ),
            patch("app.llm.model_manager.chat", new=AsyncMock(return_value=response)),
        ):
            result = await QuestionClassifierNodeExecutor().execute(
                legacy_node, execution_context, MagicMock()
            )

        assert result.outputs == {
            "category": "tech",
            "confidence": 0.5,
            "reasoning": response.content,
        }
        assert result.next_handles == ["tech"]
        execution_context.resolve_variable_ref.assert_awaited_once_with(
            "{{legacy.input}}"
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("categories", "expected_handle"),
        [(CATEGORIES, "tech"), ([], "other")],
    )
    async def test_invalid_category_uses_default_output_and_safe_handle(
        self, categories, expected_handle
    ):
        execution_context = context()
        response = SimpleNamespace(content='{"category":"unknown"}')

        with (
            patch.object(
                TeamModel,
                "filter",
                return_value=query(
                    SimpleNamespace(model=SimpleNamespace(id="model-1"))
                ),
            ),
            patch("app.llm.model_manager.chat", new=AsyncMock(return_value=response)),
        ):
            result = await QuestionClassifierNodeExecutor().execute(
                node({"modelId": "team-model", "categories": categories}),
                execution_context,
                MagicMock(),
            )

        assert result.outputs == {
            "category": "other",
            "confidence": 0.5,
            "reasoning": "",
        }
        assert result.next_handles == [expected_handle]
        execution_context.set_branch.assert_awaited_once_with(
            "classifier-1", expected_handle
        )

    @pytest.mark.asyncio
    async def test_translates_chat_errors_without_selecting_branch(self):
        execution_context = context()
        error = RuntimeError("provider unavailable")

        with (
            patch.object(
                TeamModel,
                "filter",
                return_value=query(
                    SimpleNamespace(model=SimpleNamespace(id="model-1"))
                ),
            ),
            patch("app.llm.model_manager.chat", new=AsyncMock(side_effect=error)),
            patch(
                "app.services.workflow.executors.condition.translate_public_workflow_error",
                return_value="translated_error",
            ) as translate,
        ):
            result = await QuestionClassifierNodeExecutor().execute(
                node({"modelId": "team-model", "categories": CATEGORIES}),
                execution_context,
                MagicMock(),
            )

        assert result.error == "translated_error"
        translate.assert_called_once_with(error)
        execution_context.set_branch.assert_not_awaited()

    def test_declares_category_confidence_and_reasoning_outputs(self):
        executor = QuestionClassifierNodeExecutor()

        assert executor.get_output_variables({}) == [
            {"name": "category", "type": "string"},
            {"name": "confidence", "type": "number"},
            {"name": "reasoning", "type": "string"},
        ]
        assert [
            (item.name, item.type.kind) for item in executor.get_output_specs({})
        ] == [
            ("category", "string"),
            ("confidence", "number"),
            ("reasoning", "string"),
        ]
