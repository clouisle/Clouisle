from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.services.workflow.executors.knowledge import (
    DocumentExtractorNodeExecutor,
    KnowledgeRetrievalNodeExecutor,
)


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("config", "resolved_query", "expected_error"),
    [
        ({}, None, "validation_error"),
        (
            {"knowledgeBaseId": "kb-1", "queryVariableRef": "{{start.query}}"},
            "",
            "query_parameter_required",
        ),
        (
            {
                "knowledgeBaseId": "kb-1",
                "querySource": "constant",
                "queryConstantValue": "",
            },
            None,
            "query_parameter_required",
        ),
    ],
)
async def test_knowledge_retrieval_validates_config_and_query(
    config, resolved_query, expected_error
):
    context = MagicMock()
    context.resolve_variable_ref = AsyncMock(return_value=resolved_query)

    result = await KnowledgeRetrievalNodeExecutor().execute(
        {"data": {"knowledgeRetrievalConfig": config}}, context, MagicMock()
    )

    assert result.error == expected_error


@pytest.mark.anyio
async def test_knowledge_retrieval_returns_not_found_for_unknown_knowledge_base():
    workflow_id, team_id = uuid4(), uuid4()
    with (
        patch("app.models.workflow.Workflow.filter") as workflow_filter,
        patch("app.models.knowledge_base.KnowledgeBase.filter") as kb_filter,
    ):
        workflow_filter.return_value.only.return_value.first = AsyncMock(
            return_value=SimpleNamespace(team_id=team_id)
        )
        kb_filter.return_value.first = AsyncMock(return_value=None)
        result = await KnowledgeRetrievalNodeExecutor().execute(
            {
                "data": {
                    "knowledgeRetrievalConfig": {
                        "knowledgeBaseId": "missing-kb",
                        "querySource": "constant",
                        "queryConstantValue": "question",
                    }
                }
            },
            MagicMock(),
            SimpleNamespace(workflow_id=workflow_id),
        )

    workflow_filter.assert_called_once_with(id=workflow_id)
    kb_filter.assert_called_once_with(id="missing-kb", team_id=team_id)
    assert result.error == "not_found"


@pytest.mark.anyio
async def test_knowledge_retrieval_searches_and_formats_results():
    document_id = uuid4()
    chunk_id = uuid4()
    workflow_id = uuid4()
    kb = SimpleNamespace(
        id=uuid4(),
        name="Docs",
        status="active",
        embedding_model_id=uuid4(),
        rerank_model_id=uuid4(),
        team_id=uuid4(),
        settings=None,
    )
    context = MagicMock()
    context.resolve_variable_ref = AsyncMock(return_value=123)
    retrieve = AsyncMock(
        return_value=SimpleNamespace(
            results=(
                {
                    "content": "first",
                    "score": 0.9,
                    "metadata": {"page": 1},
                    "document_id": document_id,
                    "chunk_id": chunk_id,
                },
                {},
            )
        )
    )

    with (
        patch("app.models.workflow.Workflow.filter") as workflow_filter,
        patch("app.models.knowledge_base.KnowledgeBase.filter") as kb_filter,
        patch("app.services.retrieval.retrieve", retrieve),
    ):
        workflow_filter.return_value.only.return_value.first = AsyncMock(
            return_value=SimpleNamespace(team_id=kb.team_id)
        )
        kb_filter.return_value.first = AsyncMock(return_value=kb)
        result = await KnowledgeRetrievalNodeExecutor().execute(
            {
                "data": {
                    "knowledgeRetrievalConfig": {
                        "knowledgeBaseId": "kb-1",
                        "queryVariableRef": "{{start.query}}",
                        "searchMode": "vector",
                        "topK": 3,
                        "threshold": 0.4,
                        "outputVariable": "matches",
                    }
                }
            },
            context,
            SimpleNamespace(workflow_id=workflow_id),
        )

    context.resolve_variable_ref.assert_awaited_once_with("{{start.query}}")
    kb_filter.assert_called_once_with(id="kb-1", team_id=kb.team_id)
    request = retrieve.await_args.args[0]
    assert request.query == "123"
    assert request.search_mode == "vector"
    assert request.top_k == 3
    assert request.score_threshold == 0.4
    assert request.targets[0].kb_id == kb.id
    assert request.targets[0].embedding_model_id == kb.embedding_model_id
    assert result.outputs == {
        "matches": [
            {
                "content": "first",
                "score": 0.9,
                "metadata": {"page": 1},
                "documentId": str(document_id),
                "chunkId": str(chunk_id),
            },
            {
                "content": "",
                "score": 0,
                "metadata": {},
                "documentId": None,
                "chunkId": None,
            },
        ],
        "context": "first\n\n---\n\n",
        "totalFound": 2,
    }


@pytest.mark.anyio
async def test_knowledge_retrieval_translates_search_errors_and_uses_defaults():
    workflow_id, team_id = uuid4(), uuid4()
    kb = SimpleNamespace(
        id=uuid4(),
        name="Docs",
        status="active",
        embedding_model_id=None,
        rerank_model_id=None,
        team_id=team_id,
        settings=None,
    )
    error = RuntimeError("search failed")

    with (
        patch("app.models.workflow.Workflow.filter") as workflow_filter,
        patch("app.models.knowledge_base.KnowledgeBase.filter") as kb_filter,
        patch("app.services.retrieval.retrieve", new=AsyncMock(side_effect=error)),
        patch(
            "app.services.workflow.executors.knowledge.translate_public_workflow_error",
            return_value="translated_error",
        ) as translate,
    ):
        workflow_filter.return_value.only.return_value.first = AsyncMock(
            return_value=SimpleNamespace(team_id=team_id)
        )
        kb_filter.return_value.first = AsyncMock(return_value=kb)
        result = await KnowledgeRetrievalNodeExecutor().execute(
            {
                "data": {
                    "knowledgeRetrievalConfig": {
                        "knowledgeBaseId": "kb-1",
                        "querySource": "constant",
                        "queryConstantValue": "question",
                        "outputVariable": "",
                    }
                }
            },
            MagicMock(),
            SimpleNamespace(workflow_id=workflow_id),
        )

    kb_filter.assert_called_once_with(id="kb-1", team_id=team_id)
    translate.assert_called_once_with(error)
    assert result.error == "translated_error"


@pytest.mark.anyio
async def test_document_extractor_resolves_config_and_returns_result():
    context = MagicMock()
    context.resolve_variable_ref = AsyncMock(return_value=123)
    extract = AsyncMock(return_value={"content": "text", "metadata": {"pages": 1}})

    extractor = MagicMock()
    extractor.return_value.extract = extract
    document_module = SimpleNamespace(DocumentExtractor=extractor)
    with patch.dict("sys.modules", {"app.services.document": document_module}):
        result = await DocumentExtractorNodeExecutor().execute(
            {
                "data": {
                    "config": {
                        "inputVariable": "{{upload.file}}",
                        "extractionMode": "markdown",
                        "ocrEnabled": False,
                        "language": "en",
                    }
                }
            },
            context,
            MagicMock(),
        )

    context.resolve_variable_ref.assert_awaited_once_with("{{upload.file}}")
    extract.assert_awaited_once_with(
        file_path="123", mode="markdown", ocr_enabled=False, language="en"
    )
    assert result.outputs == {
        "content": "text",
        "metadata": {"pages": 1},
        "structured": None,
    }


@pytest.mark.anyio
async def test_document_extractor_validates_input_and_translates_errors():
    context = MagicMock()
    context.resolve_variable_ref = AsyncMock(side_effect=[None, "/tmp/file.pdf"])
    executor = DocumentExtractorNodeExecutor()

    extractor = MagicMock()
    document_module = SimpleNamespace(DocumentExtractor=extractor)
    with patch.dict("sys.modules", {"app.services.document": document_module}):
        missing = await executor.execute({}, context, MagicMock())

    error = RuntimeError("extract failed")
    extractor.return_value.extract = AsyncMock(side_effect=error)
    with (
        patch.dict("sys.modules", {"app.services.document": document_module}),
        patch(
            "app.services.workflow.executors.knowledge.translate_public_workflow_error",
            return_value="translated_error",
        ) as translate,
    ):
        failed = await executor.execute({}, context, MagicMock())

    assert missing.error == "validation_error"
    extractor.return_value.extract.assert_awaited_once_with(
        file_path="/tmp/file.pdf", mode="text", ocr_enabled=True, language="auto"
    )
    translate.assert_called_once_with(error)
    assert failed.error == "translated_error"


def test_output_declarations():
    knowledge = KnowledgeRetrievalNodeExecutor()
    document = DocumentExtractorNodeExecutor()

    assert knowledge.get_output_variables({}) == [
        {"name": "results", "type": "array"},
        {"name": "context", "type": "string"},
        {"name": "totalFound", "type": "number"},
    ]
    assert [(item.name, item.type.kind) for item in knowledge.get_output_specs({})] == [
        ("results", "array"),
        ("context", "string"),
        ("totalFound", "number"),
    ]
    assert document.get_output_variables({}) == [
        {"name": "content", "type": "string"},
        {"name": "metadata", "type": "object"},
        {"name": "structured", "type": "object"},
    ]
    assert [(item.name, item.type.kind) for item in document.get_output_specs({})] == [
        ("content", "string"),
        ("metadata", "object"),
        ("structured", "object"),
    ]
