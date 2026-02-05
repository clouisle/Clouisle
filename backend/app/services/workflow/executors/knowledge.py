"""
Knowledge base node executors.

Handles knowledge base retrieval for RAG workflows.
"""

from typing import TYPE_CHECKING
import logging

from ..executor import NodeExecutor, NodeExecutorRegistry, ExecutionResult

if TYPE_CHECKING:
    from app.models.workflow import WorkflowRun
    from ..context import ExecutionContext

logger = logging.getLogger(__name__)


@NodeExecutorRegistry.register("knowledge_retrieval")
class KnowledgeRetrievalNodeExecutor(NodeExecutor):
    """
    Knowledge base retrieval node executor.

    Retrieves relevant documents from a knowledge base.

    Node Config:
        {
            "knowledgeBaseId": "uuid",
            "queryVariable": "{{start.query}}",
            "topK": 5,
            "scoreThreshold": 0.5,
            "filters": {
                "metadata.type": "faq"
            },
            "rerankEnabled": false,
            "rerankModel": "reranker-model-id"
        }

    Outputs:
        {
            "results": [
                {
                    "content": "Document content...",
                    "score": 0.85,
                    "metadata": {...},
                    "documentId": "uuid"
                }
            ],
            "context": "Combined context string",
            "totalFound": 5
        }
    """

    async def execute(
        self,
        node: dict,
        context: "ExecutionContext",
        run: "WorkflowRun",
    ) -> ExecutionResult:
        """Execute knowledge retrieval node."""
        from app.models.knowledge_base import KnowledgeBase
        from app.services.knowledge_base import KnowledgeBaseService

        node_data = node.get("data", {})
        config = node_data.get("config", {})

        kb_id = config.get("knowledgeBaseId")
        query_var = config.get("queryVariable", "")
        top_k = config.get("topK", 5)
        score_threshold = config.get("scoreThreshold", 0.5)
        filters = config.get("filters", {})
        rerank_enabled = config.get("rerankEnabled", False)
        rerank_model = config.get("rerankModel")

        if not kb_id:
            return ExecutionResult(error="Knowledge base ID not configured")

        # Get query
        query = await context.resolve_variable_ref(query_var)
        if not query:
            return ExecutionResult(error="Query is empty")

        # Load knowledge base
        kb = await KnowledgeBase.filter(id=kb_id).first()
        if not kb:
            return ExecutionResult(error=f"Knowledge base not found: {kb_id}")

        try:
            kb_service = KnowledgeBaseService()

            # Perform retrieval
            results = await kb_service.search(
                knowledge_base=kb,
                query=str(query),
                top_k=top_k,
                score_threshold=score_threshold,
                filters=filters,
            )

            # Rerank if enabled
            if rerank_enabled and rerank_model and results:
                results = await kb_service.rerank(
                    results=results,
                    query=str(query),
                    model_id=rerank_model,
                )

            # Format results
            formatted_results = []
            context_parts = []

            for result in results:
                formatted_results.append({
                    "content": result.get("content", ""),
                    "score": result.get("score", 0),
                    "metadata": result.get("metadata", {}),
                    "documentId": result.get("document_id"),
                })
                context_parts.append(result.get("content", ""))

            # Combine context
            combined_context = "\n\n---\n\n".join(context_parts)

            return ExecutionResult(
                outputs={
                    "results": formatted_results,
                    "context": combined_context,
                    "totalFound": len(formatted_results),
                }
            )

        except Exception as e:
            logger.exception(f"Knowledge retrieval error: {e}")
            return ExecutionResult(error=f"Retrieval failed: {str(e)}")

    def get_output_variables(self, config: dict) -> list[dict]:
        """Get output variables."""
        return [
            {"name": "results", "type": "array"},
            {"name": "context", "type": "string"},
            {"name": "totalFound", "type": "number"},
        ]


@NodeExecutorRegistry.register("document_extractor")
class DocumentExtractorNodeExecutor(NodeExecutor):
    """
    Document extractor node executor.

    Extracts content from documents (PDF, DOCX, etc.).

    Node Config:
        {
            "inputVariable": "{{upload.file}}",
            "extractionMode": "text" | "markdown" | "structured",
            "ocrEnabled": true,
            "language": "auto"
        }

    Outputs:
        {
            "content": "Extracted text...",
            "metadata": {
                "pages": 10,
                "wordCount": 1500,
                "language": "en"
            },
            "structured": {...}  # If extractionMode is "structured"
        }
    """

    async def execute(
        self,
        node: dict,
        context: "ExecutionContext",
        run: "WorkflowRun",
    ) -> ExecutionResult:
        """Execute document extraction node."""
        from app.services.document import DocumentExtractor

        node_data = node.get("data", {})
        config = node_data.get("config", {})

        input_var = config.get("inputVariable", "")
        extraction_mode = config.get("extractionMode", "text")
        ocr_enabled = config.get("ocrEnabled", True)
        language = config.get("language", "auto")

        # Get input file path
        file_path = await context.resolve_variable_ref(input_var)
        if not file_path:
            return ExecutionResult(error="No file provided for extraction")

        try:
            extractor = DocumentExtractor()

            result = await extractor.extract(
                file_path=str(file_path),
                mode=extraction_mode,
                ocr_enabled=ocr_enabled,
                language=language,
            )

            return ExecutionResult(
                outputs={
                    "content": result.get("content", ""),
                    "metadata": result.get("metadata", {}),
                    "structured": result.get("structured"),
                }
            )

        except Exception as e:
            logger.exception(f"Document extraction error: {e}")
            return ExecutionResult(error=f"Extraction failed: {str(e)}")

    def get_output_variables(self, config: dict) -> list[dict]:
        """Get output variables."""
        return [
            {"name": "content", "type": "string"},
            {"name": "metadata", "type": "object"},
            {"name": "structured", "type": "object"},
        ]
