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
            "knowledgeBaseName": "My Knowledge Base",
            "query": "{{start.query}}",
            "searchMode": "hybrid" | "vector" | "fulltext",
            "topK": 5,
            "threshold": 0.0,
            "outputVariables": {
                "results": "results"
            }
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
        from app.services.vector_store import VectorStore

        node_data = node.get("data", {})
        # Get knowledgeRetrievalConfig from node data
        kr_config = node_data.get("knowledgeRetrievalConfig", {})

        kb_id = kr_config.get("knowledgeBaseId")
        query_source = kr_config.get("querySource", "variable")
        search_mode = kr_config.get("searchMode", "hybrid")
        top_k = kr_config.get("topK", 5)
        threshold = kr_config.get("threshold", 0.0)
        output_var = kr_config.get("outputVariable", "results")

        if not kb_id:
            return ExecutionResult(error="Knowledge base ID not configured")

        # Resolve query based on source
        if query_source == "variable":
            query_ref = kr_config.get("queryVariableRef", "")
            query = await context.resolve_variable_ref(query_ref)
        else:  # constant
            query = kr_config.get("queryConstantValue", "")

        if not query:
            return ExecutionResult(error="Query is empty")

        # Load knowledge base
        kb = await KnowledgeBase.filter(id=kb_id).first()
        if not kb:
            return ExecutionResult(error=f"Knowledge base not found: {kb_id}")

        try:
            # Get embedding model and team ID from KB for usage tracking
            embedding_model_id = (
                str(kb.embedding_model_id) if kb.embedding_model_id else None
            )
            team_id = str(kb.team_id) if kb.team_id else None

            vector_store = VectorStore(
                embedding_model_id=embedding_model_id,
                rerank_model_id=str(kb.rerank_model_id) if kb.rerank_model_id else None,
                team_id=team_id,
            )

            # Perform retrieval based on search mode
            results = await vector_store.search(
                kb_id=kb_id,
                query=str(query),
                search_mode=search_mode,  # vector, fulltext, or hybrid
                top_k=top_k,
                score_threshold=threshold,
            )

            # Format results
            formatted_results = []
            context_parts = []

            for result in results:
                # Convert UUID to string if present
                doc_id = result.get("document_id")
                if doc_id is not None:
                    doc_id = str(doc_id)

                chunk_id = result.get("chunk_id")
                if chunk_id is not None:
                    chunk_id = str(chunk_id)

                formatted_results.append(
                    {
                        "content": result.get("content", ""),
                        "score": result.get("score", 0),
                        "metadata": result.get("metadata", {}),
                        "documentId": doc_id,
                        "chunkId": chunk_id,
                    }
                )
                context_parts.append(result.get("content", ""))

            # Combine context
            combined_context = "\n\n---\n\n".join(context_parts)

            # Use custom output variable name
            return ExecutionResult(
                outputs={
                    output_var: formatted_results,
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
