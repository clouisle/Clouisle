"""Focused branch coverage for workflow executors without dedicated tests."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.workflow.context import ExecutionContext


class TestKnowledgeExecutors:
    @pytest.mark.asyncio
    async def test_retrieval_validates_and_formats_custom_output(self):
        from app.services.workflow.executors.knowledge import (
            KnowledgeRetrievalNodeExecutor,
        )

        executor = KnowledgeRetrievalNodeExecutor()
        context = MagicMock(spec=ExecutionContext)
        context.resolve_variable_ref = AsyncMock(return_value="question")
        run = MagicMock()

        assert (
            await executor.execute(
                {"data": {"knowledgeRetrievalConfig": {}}}, context, run
            )
        ).error == "validation_error"
        with patch("app.models.knowledge_base.KnowledgeBase.filter") as filter_mock:
            filter_mock.return_value.first = AsyncMock(return_value=None)
            result = await executor.execute(
                {
                    "data": {
                        "knowledgeRetrievalConfig": {
                            "knowledgeBaseId": "kb",
                            "queryVariableRef": "{{q}}",
                        }
                    }
                },
                context,
                run,
            )
        assert result.error == "not_found"

        kb = MagicMock(embedding_model_id=None, rerank_model_id=None, team_id=None)
        with (
            patch("app.models.knowledge_base.KnowledgeBase.filter") as filter_mock,
            patch("app.services.vector_store.VectorStore") as store_cls,
        ):
            filter_mock.return_value.first = AsyncMock(return_value=kb)
            store_cls.return_value.search = AsyncMock(
                return_value=[
                    {"content": "chunk", "score": 0.8, "document_id": 1, "chunk_id": 2}
                ]
            )
            result = await executor.execute(
                {
                    "data": {
                        "knowledgeRetrievalConfig": {
                            "knowledgeBaseId": "kb",
                            "querySource": "constant",
                            "queryConstantValue": "question",
                            "searchMode": "vector",
                            "topK": 2,
                            "threshold": 0.4,
                            "outputVariable": "hits",
                        }
                    }
                },
                context,
                run,
            )
        assert result.outputs == {
            "hits": [
                {
                    "content": "chunk",
                    "score": 0.8,
                    "metadata": {},
                    "documentId": "1",
                    "chunkId": "2",
                }
            ],
            "context": "chunk",
            "totalFound": 1,
        }
        store_cls.return_value.search.assert_awaited_once_with(
            kb_id="kb",
            query="question",
            search_mode="vector",
            top_k=2,
            score_threshold=0.4,
        )

    @pytest.mark.asyncio
    async def test_document_extractor_validates_and_translates_exception(self):
        from app.services.workflow.executors.knowledge import (
            DocumentExtractorNodeExecutor,
        )

        executor = DocumentExtractorNodeExecutor()
        context = MagicMock(spec=ExecutionContext)
        context.resolve_variable_ref = AsyncMock(side_effect=[None, "/tmp/file.pdf"])
        run = MagicMock()
        document_module = MagicMock()
        document_module.DocumentExtractor.return_value.extract = AsyncMock(
            side_effect=RuntimeError("secret")
        )
        with patch.dict("sys.modules", {"app.services.document": document_module}):
            assert (
                await executor.execute({"data": {"config": {}}}, context, run)
            ).error == "validation_error"
            result = await executor.execute(
                {
                    "data": {
                        "config": {
                            "inputVariable": "{{file}}",
                            "extractionMode": "markdown",
                            "ocrEnabled": False,
                            "language": "zh",
                        }
                    }
                },
                context,
                run,
            )
        assert result.error == "secret"


class TestLLMExecutor:
    @pytest.mark.asyncio
    async def test_llm_validates_missing_and_unknown_models(self):
        from app.services.workflow.executors.llm import LLMNodeExecutor

        executor = LLMNodeExecutor()
        context, run = MagicMock(spec=ExecutionContext), MagicMock()
        assert (
            await executor.execute({"data": {"llmConfig": {}}}, context, run)
        ).error == "validation_error"
        with (
            patch("app.models.model.TeamModel.filter") as team_filter,
            patch("app.models.model.Model.filter") as model_filter,
        ):
            team_filter.return_value.prefetch_related.return_value.first = AsyncMock(
                return_value=None
            )
            model_filter.return_value.first = AsyncMock(return_value=None)
            result = await executor.execute(
                {"data": {"llmConfig": {"modelId": "missing"}}}, context, run
            )
        assert result.error == "model_not_found"

    @pytest.mark.asyncio
    async def test_llm_streaming_resolves_prompts_and_json_format(self):
        from app.services.workflow.executors.llm import LLMNodeExecutor
        from app.services.workflow.lazy_stream import LazyStreamResult

        executor = LLMNodeExecutor()
        context = MagicMock(spec=ExecutionContext)
        context.resolve_variable_ref = AsyncMock(return_value="resolved")
        team_model = MagicMock(model=MagicMock(id="model-id"))
        with patch("app.models.model.TeamModel.filter") as team_filter:
            team_filter.return_value.prefetch_related.return_value.first = AsyncMock(
                return_value=team_model
            )
            result = await executor.execute(
                {
                    "id": "llm",
                    "data": {
                        "llmConfig": {
                            "modelId": "team-model",
                            "systemPrompt": "System {{x}}",
                            "userPrompt": "Ask {{y}}",
                            "streaming": True,
                            "responseFormat": "json",
                        }
                    },
                },
                context,
                MagicMock(),
            )
        assert isinstance(result.outputs["response"], LazyStreamResult)
        assert result.outputs["response"].messages == [
            {"role": "system", "content": "System resolved"},
            {"role": "user", "content": "Ask resolved"},
        ]
        assert result.outputs["response"].response_format == {"type": "json_object"}


class TestSubWorkflowExecutor:
    @pytest.mark.asyncio
    async def test_subworkflow_validation_depth_and_not_found(self):
        from app.services.workflow.errors import MaxDepthExceededError
        from app.services.workflow.executors.subworkflow import (
            MAX_DEPTH,
            SubWorkflowNodeExecutor,
        )

        executor = SubWorkflowNodeExecutor()
        context, run = MagicMock(spec=ExecutionContext), MagicMock(depth=0)
        assert (
            await executor.execute({"data": {"config": {}}}, context, run)
        ).error == "validation_error"
        run.depth = MAX_DEPTH
        with pytest.raises(MaxDepthExceededError):
            await executor.execute(
                {
                    "data": {
                        "config": {"workflowId": "00000000-0000-0000-0000-000000000001"}
                    }
                },
                context,
                run,
            )
        run.depth = 0
        with patch("app.models.workflow.Workflow.filter") as workflow_filter:
            workflow_filter.return_value.first = AsyncMock(return_value=None)
            result = await executor.execute(
                {
                    "data": {
                        "subWorkflowConfig": {
                            "workflowId": "00000000-0000-0000-0000-000000000001"
                        }
                    }
                },
                context,
                run,
            )
        assert result.error == "workflow_not_found"
