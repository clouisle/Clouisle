from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.workflow.executors.llm import LLMNodeExecutor
from app.services.workflow.lazy_stream import LazyStreamResult


def mock_model_queries(team_model=None, model=None):
    team_filter = MagicMock()
    team_filter.return_value.prefetch_related.return_value.first = AsyncMock(
        return_value=team_model
    )
    model_filter = MagicMock()
    model_filter.return_value.first = AsyncMock(return_value=model)
    return team_filter, model_filter


class TestLLMNodeExecutor:
    @pytest.mark.anyio
    async def test_execute_requires_model_id(self):
        result = await LLMNodeExecutor().execute(
            {"id": "llm_1", "data": {"llmConfig": {}}}, MagicMock(), MagicMock()
        )

        assert result.error == "validation_error"

    @pytest.mark.anyio
    async def test_execute_returns_error_when_model_does_not_exist(self):
        team_filter, model_filter = mock_model_queries()
        with (
            patch("app.models.model.TeamModel.filter", team_filter),
            patch("app.models.model.Model.filter", model_filter),
        ):
            result = await LLMNodeExecutor().execute(
                {
                    "id": "llm_1",
                    "data": {"llmConfig": {"modelId": "missing-model"}},
                },
                MagicMock(),
                MagicMock(),
            )

        assert result.error == "model_not_found"
        model_filter.assert_called_once_with(id="missing-model")

    @pytest.mark.anyio
    async def test_execute_resolves_prompts_inputs_schema_and_usage(self):
        team_model = SimpleNamespace(model=SimpleNamespace(id="model-1"))
        team_filter, model_filter = mock_model_queries(team_model=team_model)
        context = MagicMock()
        context.resolve_variable_ref = AsyncMock(
            side_effect=["assistant", "question", {"a": 1}]
        )
        chat_result = SimpleNamespace(
            content="answer",
            reasoning_content="reasoning",
            usage=SimpleNamespace(prompt_tokens=3, completion_tokens=2, total_tokens=5),
        )

        with (
            patch("app.models.model.TeamModel.filter", team_filter),
            patch("app.models.model.Model.filter", model_filter),
            patch(
                "app.llm.model_manager.chat",
                new=AsyncMock(return_value=chat_result),
            ) as chat,
        ):
            result = await LLMNodeExecutor().execute(
                {
                    "id": "llm_1",
                    "data": {
                        "llmConfig": {
                            "modelId": "team-model-1",
                            "systemPrompt": "You are {{role}}",
                            "userPrompt": "Answer {{query}}",
                            "inputs": [
                                {"name": "context", "variableRef": "{{context}}"}
                            ],
                            "temperature": 0.2,
                            "maxTokens": 100,
                            "topP": 0.8,
                            "responseFormat": "json_schema",
                            "jsonSchema": '{"type": "object"}',
                        }
                    },
                },
                context,
                MagicMock(),
            )

        assert result.outputs == {
            "response": "answer",
            "reasoning": "reasoning",
            "usage": {
                "prompt_tokens": 3,
                "completion_tokens": 2,
                "total_tokens": 5,
            },
        }
        chat.assert_awaited_once_with(
            messages=[
                {"role": "system", "content": "You are assistant"},
                {"role": "user", "content": 'context: {"a": 1}\n\nAnswer question'},
            ],
            model_id="model-1",
            temperature=0.2,
            max_tokens=100,
            top_p=0.8,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "response",
                    "strict": True,
                    "schema": {"type": "object"},
                },
            },
        )
        model_filter.assert_not_called()

    @pytest.mark.anyio
    async def test_execute_streaming_returns_lazy_result_for_direct_model(self):
        direct_model = SimpleNamespace(id="model-1")
        team_filter, model_filter = mock_model_queries(model=direct_model)

        with (
            patch("app.models.model.TeamModel.filter", team_filter),
            patch("app.models.model.Model.filter", model_filter),
        ):
            result = await LLMNodeExecutor().execute(
                {
                    "id": "llm_1",
                    "data": {
                        "config": {
                            "modelId": "model-1",
                            "userPrompt": "Hello",
                            "streaming": True,
                            "responseFormat": "json",
                        }
                    },
                },
                MagicMock(),
                MagicMock(),
            )

        lazy_result = result.outputs["response"]
        assert isinstance(lazy_result, LazyStreamResult)
        assert lazy_result.model_id == "model-1"
        assert lazy_result.messages == [{"role": "user", "content": "Hello"}]
        assert lazy_result.response_format == {"type": "json_object"}
        assert result.outputs["reasoning"] == ""
        assert result.outputs["usage"] == {}

    @pytest.mark.anyio
    async def test_execute_translates_model_error(self):
        team_model = SimpleNamespace(model=SimpleNamespace(id="model-1"))
        team_filter, model_filter = mock_model_queries(team_model=team_model)

        with (
            patch("app.models.model.TeamModel.filter", team_filter),
            patch("app.models.model.Model.filter", model_filter),
            patch(
                "app.llm.model_manager.chat",
                new=AsyncMock(side_effect=RuntimeError("provider secret")),
            ),
            patch(
                "app.services.workflow.executors.llm.translate_public_workflow_error",
                return_value="workflow_execution_error",
            ) as translate_error,
        ):
            result = await LLMNodeExecutor().execute(
                {
                    "id": "llm_1",
                    "data": {"llmConfig": {"modelId": "team-model-1"}},
                },
                MagicMock(),
                MagicMock(),
            )

        assert result.error == "workflow_execution_error"
        translate_error.assert_called_once()

    @pytest.mark.anyio
    async def test_validate_config_and_output_specs(self):
        executor = LLMNodeExecutor()

        assert await executor.validate_config({}) == [
            "Model ID is required",
            "User prompt or inputs are required",
        ]
        assert (
            await executor.validate_config(
                {"modelId": "model-1", "inputs": [{"name": "query"}]}
            )
            == []
        )
        assert [output.name for output in executor.get_output_specs({})] == [
            "response",
            "reasoning",
            "usage",
        ]
