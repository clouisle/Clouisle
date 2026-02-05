"""
Vector store service for knowledge base.
Uses Qdrant for vector storage and similarity search.

Supports dynamic embedding dimensions - each knowledge base can use a different
embedding model with different dimensions. Each dimension maps to a dedicated
Qdrant collection (e.g., kb_dim_1536).
"""

import json
import logging
import re
from typing import Any, TYPE_CHECKING
from uuid import UUID

import jieba
from tortoise import Tortoise

from app.core.config import settings
from app.models.knowledge_base import DocumentChunk, Document, KnowledgeBase
from app.services.usage_tracker import QuotaExceededError

try:
    from qdrant_client import AsyncQdrantClient
    from qdrant_client.http import models as qmodels
except Exception:  # pragma: no cover - optional dependency at runtime
    AsyncQdrantClient = None
    qmodels = None

# Avoid circular import - import model_manager lazily
if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Initialize jieba (disable verbose output)
jieba.setLogLevel(logging.WARNING)


def _get_model_manager():
    """Get model manager lazily to avoid circular import."""
    from app.llm import model_manager

    return model_manager


_qdrant_client: "AsyncQdrantClient | None" = None
_qdrant_collections: set[str] = set()
_qdrant_payload_indexes: dict[str, set[str]] = {}


def _collection_name(dimension: int) -> str:
    return f"{settings.QDRANT_COLLECTION_PREFIX}_{dimension}"


def _qdrant_distance() -> "qmodels.Distance":
    if qmodels is None:
        raise RuntimeError("qdrant-client is not installed")
    distance = settings.QDRANT_DISTANCE.lower()
    if distance in ("cosine", "cos"):
        return qmodels.Distance.COSINE
    if distance in ("dot", "ip", "inner"):
        return qmodels.Distance.DOT
    if distance in ("euclid", "l2"):
        return qmodels.Distance.EUCLID
    raise ValueError(f"Unsupported Qdrant distance: {settings.QDRANT_DISTANCE}")


async def _get_qdrant_client() -> "AsyncQdrantClient":
    global _qdrant_client
    if AsyncQdrantClient is None:
        raise RuntimeError("qdrant-client is not installed")
    if _qdrant_client is None:
        _qdrant_client = AsyncQdrantClient(
            url=settings.QDRANT_URL,
            api_key=settings.QDRANT_API_KEY,
        )
    return _qdrant_client


async def _collection_exists(name: str) -> bool:
    if name in _qdrant_collections:
        return True
    client = await _get_qdrant_client()
    try:
        await client.get_collection(name)
        _qdrant_collections.add(name)
        return True
    except Exception:
        return False


async def _ensure_payload_index(collection: str, field_name: str) -> None:
    if qmodels is None:
        raise RuntimeError("qdrant-client is not installed")
    if field_name in _qdrant_payload_indexes.get(collection, set()):
        return
    client = await _get_qdrant_client()
    try:
        await client.create_payload_index(
            collection_name=collection,
            field_name=field_name,
            field_schema=qmodels.PayloadSchemaType.KEYWORD,
        )
    except Exception as e:
        logger.warning(f"Could not create payload index {collection}.{field_name}: {e}")
    _qdrant_payload_indexes.setdefault(collection, set()).add(field_name)


async def _ensure_collection(dimension: int) -> str:
    if qmodels is None:
        raise RuntimeError("qdrant-client is not installed")
    collection = _collection_name(dimension)
    if collection in _qdrant_collections:
        return collection
    client = await _get_qdrant_client()
    try:
        await client.get_collection(collection)
    except Exception:
        await client.create_collection(
            collection_name=collection,
            vectors_config=qmodels.VectorParams(
                size=dimension,
                distance=_qdrant_distance(),
            ),
        )
    _qdrant_collections.add(collection)
    await _ensure_payload_index(collection, "kb_id")
    await _ensure_payload_index(collection, "document_id")
    return collection


async def _delete_qdrant_points(collection: str, ids: list[str]) -> None:
    if not ids:
        return
    client = await _get_qdrant_client()
    try:
        await client.delete(
            collection_name=collection,
            points_selector=qmodels.PointIdsList(points=ids),
        )
    except Exception as e:
        logger.warning(f"Failed to delete Qdrant points from {collection}: {e}")


async def _delete_qdrant_filter(collection: str, q_filter: "qmodels.Filter") -> None:
    client = await _get_qdrant_client()
    try:
        await client.delete(
            collection_name=collection,
            points_selector=qmodels.FilterSelector(filter=q_filter),
        )
    except Exception as e:
        logger.warning(f"Failed to delete Qdrant points from {collection}: {e}")


def _build_qdrant_filter(
    kb_id: UUID, filter_doc_ids: list[UUID] | None
) -> "qmodels.Filter":
    if qmodels is None:
        raise RuntimeError("qdrant-client is not installed")
    conditions: list[qmodels.FieldCondition] = [
        qmodels.FieldCondition(
            key="kb_id",
            match=qmodels.MatchValue(value=str(kb_id)),
        )
    ]
    if filter_doc_ids:
        conditions.append(
            qmodels.FieldCondition(
                key="document_id",
                match=qmodels.MatchAny(any=[str(did) for did in filter_doc_ids]),
            )
        )
    return qmodels.Filter(must=conditions)


def _normalize_qdrant_score(score: float) -> float:
    distance = settings.QDRANT_DISTANCE.lower()
    if distance in ("cosine", "cos"):
        # Qdrant cosine score is in [-1, 1], normalize to [0, 1]
        return max(0.0, min(1.0, (score + 1.0) / 2.0))
    if distance in ("euclid", "l2"):
        # Convert distance to similarity
        return max(0.0, 1.0 / (1.0 + score))
    return score


async def _qdrant_search(
    collection: str,
    query_embedding: list[float],
    limit: int,
    query_filter: "qmodels.Filter",
) -> list["qmodels.ScoredPoint"]:
    client = await _get_qdrant_client()
    search_kwargs = dict(
        collection_name=collection,
        query_vector=query_embedding,
        limit=limit,
        query_filter=query_filter,
        with_payload=True,
    )

    result = None

    if hasattr(client, "query_points"):
        try:
            result = await client.query_points(
                collection_name=collection,
                query=query_embedding,
                limit=limit,
                query_filter=query_filter,
                with_payload=True,
            )
        except TypeError:
            result = await client.query_points(
                collection_name=collection,
                query_vector=query_embedding,
                limit=limit,
                query_filter=query_filter,
                with_payload=True,
            )
    elif hasattr(client, "search_points"):
        result = await client.search_points(**search_kwargs)
    elif hasattr(client, "search"):
        result = await client.search(**search_kwargs)
    else:
        raise AttributeError("AsyncQdrantClient has no query/search method")

    if hasattr(result, "result"):
        return list(result.result)
    if hasattr(result, "points"):
        return list(result.points)
    return list(result)


async def get_kb_embedding_dimension(kb_id: UUID) -> int | None:
    """
    Get the embedding dimension for a knowledge base.

    Args:
        kb_id: Knowledge base ID

    Returns:
        Embedding dimension or None if not set
    """
    kb = await KnowledgeBase.get_or_none(id=kb_id)
    if kb:
        return kb.embedding_dimension
    return None


async def set_kb_embedding_dimension(kb_id: UUID, dimension: int) -> bool:
    """
    Set the embedding dimension for a knowledge base.
    This should only be called once when processing the first document.

    Args:
        kb_id: Knowledge base ID
        dimension: Embedding dimension

    Returns:
        True if set successfully, False if already set
    """
    kb = await KnowledgeBase.get_or_none(id=kb_id)
    if not kb:
        logger.error(f"Knowledge base {kb_id} not found")
        return False

    if kb.embedding_dimension is not None:
        if kb.embedding_dimension != dimension:
            logger.warning(
                f"KB {kb_id} already has dimension {kb.embedding_dimension}, "
                f"cannot change to {dimension}"
            )
            return False
        return True

    kb.embedding_dimension = dimension
    await kb.save()
    logger.info(f"Set embedding dimension for KB {kb_id} to {dimension}")
    return True


class DimensionMismatchError(Exception):
    """Raised when embedding dimension doesn't match knowledge base dimension."""


async def _ensure_kb_dimension(kb_id: UUID, embedding_dim: int) -> int:
    """
    Ensure KB embedding dimension matches the embedding vector.

    If KB dimension is not set, initialize it with the embedding dimension.
    """
    kb_dim = await get_kb_embedding_dimension(kb_id)
    if kb_dim is None:
        await set_kb_embedding_dimension(kb_id, embedding_dim)
        logger.info(f"Set KB {kb_id} embedding dimension to {embedding_dim}")
        return embedding_dim
    if kb_dim != embedding_dim:
        raise DimensionMismatchError(
            f"Embedding dimension mismatch: KB uses {kb_dim}, "
            f"but model produces {embedding_dim}. "
            f"Please use a model with {kb_dim}-dimensional embeddings."
        )
    return kb_dim


class VectorStore:
    """
    Vector store service using Qdrant.

    Handles:
    - Embedding generation
    - Vector storage in Qdrant
    - Similarity search
    - Token usage tracking (when team_id is provided)
    - Dynamic embedding dimension management
    """

    def __init__(
        self,
        embedding_model_id: str | None = None,
        team_id: str | None = None,
        embedding_dimension: int | None = None,
    ):
        """
        Initialize vector store.

        Args:
            embedding_model_id: Optional embedding model ID to use
            team_id: Optional team ID for usage tracking
            embedding_dimension: Optional embedding dimension (detected from model if not provided)
        """
        self.embedding_model_id = embedding_model_id
        self.team_id = team_id
        self.embedding_dimension = embedding_dimension
        self._detected_dimension: int | None = None

    async def _store_embedding(
        self,
        chunk_id: UUID,
        embedding: list[float],
        dimension: int | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        """
        Store embedding vector in Qdrant.

        Args:
            chunk_id: Chunk ID
            embedding: Embedding vector
            dimension: Embedding dimension (uses detected/configured dimension if not provided)
            payload: Optional payload (e.g., kb_id/document_id)
        """
        dim = dimension or self.embedding_dimension or self._detected_dimension
        if not dim:
            dim = len(embedding)
            self._detected_dimension = dim

        collection = await _ensure_collection(dim)
        client = await _get_qdrant_client()
        result = await client.upsert(
            collection_name=collection,
            points=[
                qmodels.PointStruct(
                    id=str(chunk_id),
                    vector=embedding,
                    payload=payload or {},
                )
            ],
        )
        logger.info(
            f"Qdrant upsert: collection={collection}, chunk_id={chunk_id}, result={result.status}"
        )

    async def _batch_store_embeddings(
        self,
        chunk_ids: list[UUID],
        embeddings: list[list[float]],
        dimension: int | None = None,
        payloads: list[dict[str, Any]] | None = None,
    ) -> None:
        """
        Batch store embedding vectors in Qdrant.

        Args:
            chunk_ids: List of chunk IDs
            embeddings: List of embedding vectors
            dimension: Embedding dimension (uses detected/configured dimension if not provided)
            payloads: Optional list of payloads per vector
        """
        if not chunk_ids or not embeddings:
            return

        # Detect dimension from embeddings
        dim = dimension or self.embedding_dimension or self._detected_dimension
        if not dim and embeddings:
            dim = len(embeddings[0])
            self._detected_dimension = dim

        if not dim:
            raise ValueError("Cannot determine embedding dimension")

        collection = await _ensure_collection(dim)
        client = await _get_qdrant_client()
        points = []
        for idx, (chunk_id, embedding) in enumerate(zip(chunk_ids, embeddings)):
            payload = payloads[idx] if payloads and idx < len(payloads) else {}
            points.append(
                qmodels.PointStruct(
                    id=str(chunk_id),
                    vector=embedding,
                    payload=payload,
                )
            )
        try:
            result = await client.upsert(collection_name=collection, points=points)
        except Exception as e:
            logger.error(f"Failed to batch upsert embeddings to Qdrant: {e}")
            raise
        logger.info(
            f"Qdrant batch upsert: collection={collection}, points={len(points)}, result={result.status}"
        )

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embeddings for texts.

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors
        """
        if not texts:
            return []

        model_manager = _get_model_manager()

        try:
            # Use team-level embedding if team_id is provided
            if self.team_id and self.embedding_model_id:
                embeddings = await model_manager.team_embed(
                    team_id=self.team_id,
                    texts=texts,
                    model_id=self.embedding_model_id,
                )
            else:
                embeddings = await model_manager.embed(
                    texts, model_id=self.embedding_model_id
                )
            return embeddings
        except QuotaExceededError:
            logger.error(f"Team {self.team_id} quota exceeded for embedding")
            raise
        except Exception as e:
            logger.error(f"Error generating embeddings: {e}")
            raise

    async def embed_query(self, query: str) -> list[float]:
        """
        Generate embedding for a single query.

        Args:
            query: Query text

        Returns:
            Embedding vector
        """
        model_manager = _get_model_manager()

        try:
            # Use team-level embedding if team_id is provided
            if self.team_id and self.embedding_model_id:
                embeddings = await model_manager.team_embed(
                    team_id=self.team_id,
                    texts=[query],
                    model_id=self.embedding_model_id,
                )
                return embeddings[0]
            else:
                embedding = await model_manager.embed_query(
                    query, model_id=self.embedding_model_id
                )
                return embedding
        except QuotaExceededError:
            logger.error(f"Team {self.team_id} quota exceeded for query embedding")
            raise
        except Exception as e:
            logger.error(f"Error generating query embedding: {e}")
            raise

    async def store_chunks(
        self,
        document: Document,
        chunks: list[dict[str, Any]],
        kb_id: UUID | None = None,
    ) -> list[DocumentChunk]:
        """
        Store document chunks with embeddings in Qdrant.

        On first document processing, detects embedding dimension and records it
        in the knowledge base. Subsequent documents must use the same dimension.

        Args:
            document: Parent document
            chunks: List of chunk dicts with content, index, etc.
            kb_id: Optional knowledge base ID for dimension management

        Returns:
            List of created DocumentChunk objects

        Raises:
            DimensionMismatchError: If embedding dimension doesn't match KB dimension
        """
        if not chunks:
            return []

        # Generate embeddings for all chunks
        texts = [c["content"] for c in chunks]
        embeddings = await self.embed_texts(texts)

        # Detect dimension
        detected_dim = len(embeddings[0]) if embeddings else None
        if detected_dim:
            self._detected_dimension = detected_dim

        resolved_kb_id = kb_id or document.knowledge_base_id

        # Handle KB dimension management
        if resolved_kb_id:
            await _ensure_kb_dimension(resolved_kb_id, detected_dim)

        # Create chunk records
        created_chunks = []
        chunk_ids = []
        for chunk_data, embedding in zip(chunks, embeddings):
            embedding_id = f"doc_{document.id}_chunk_{chunk_data['chunk_index']}"

            chunk = await DocumentChunk.create(
                document=document,
                content=chunk_data["content"],
                chunk_index=chunk_data["chunk_index"],
                token_count=chunk_data.get("token_count", 0),
                metadata=chunk_data.get("metadata"),
                embedding_id=embedding_id,
            )

            created_chunks.append(chunk)
            chunk_ids.append(chunk.id)

        # Batch store embeddings in Qdrant
        try:
            payloads = []
            for _ in chunk_ids:
                payloads.append(
                    {
                        "kb_id": str(resolved_kb_id) if resolved_kb_id else "",
                        "document_id": str(document.id),
                    }
                )
            await self._batch_store_embeddings(
                chunk_ids, embeddings, detected_dim, payloads=payloads
            )
            logger.info(
                f"Stored {len(embeddings)} embeddings (dim={detected_dim}) for document {document.id}"
            )
        except Exception as e:
            logger.error(f"Error storing embeddings for document {document.id}: {e}")
            # Re-raise so we know there's a problem
            raise

        return created_chunks

    async def search(
        self,
        kb_id: UUID,
        query: str,
        search_mode: str = "hybrid",
        top_k: int = 5,
        score_threshold: float = 0.0,
        filter_doc_ids: list[UUID] | None = None,
        embedding_dimension: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Search knowledge base using specified search mode.

        Args:
            kb_id: Knowledge base ID
            query: Search query
            search_mode: Search mode - "vector", "fulltext", or "hybrid"
            top_k: Number of results to return
            score_threshold: Minimum similarity score (0-1)
            filter_doc_ids: Optional list of document IDs to filter
            embedding_dimension: Optional embedding dimension (auto-detected from KB if not provided)

        Returns:
            List of search results with chunk info and scores
        """
        # Get KB dimension if not provided
        if embedding_dimension is None:
            embedding_dimension = await get_kb_embedding_dimension(kb_id)

        # Store dimension for vector operations
        if embedding_dimension:
            self.embedding_dimension = embedding_dimension

        results: list[dict[str, Any]] = []

        logger.debug(
            f"Search KB {kb_id}: mode={search_mode}, query='{query[:50]}...', "
            f"top_k={top_k}, threshold={score_threshold}"
        )

        if search_mode == "vector":
            results = await self._vector_search(
                kb_id, query, top_k * 2, filter_doc_ids, embedding_dimension
            )
        elif search_mode == "fulltext":
            results = await self._fulltext_search(
                kb_id, query, top_k * 2, filter_doc_ids
            )
        else:  # hybrid
            # Get results from both methods
            try:
                vector_results = await self._vector_search(
                    kb_id, query, top_k, filter_doc_ids, embedding_dimension
                )
            except DimensionMismatchError as e:
                logger.warning(f"Vector search dimension mismatch for KB {kb_id}: {e}")
                vector_results = []
            except Exception as e:
                logger.warning(f"Vector search failed for KB {kb_id}: {e}")
                vector_results = []
            fulltext_results = await self._fulltext_search(
                kb_id, query, top_k, filter_doc_ids
            )

            # Merge results using RRF (Reciprocal Rank Fusion)
            results = self._merge_results_rrf(vector_results, fulltext_results)
            logger.debug(
                f"Hybrid search: vector={len(vector_results)}, fulltext={len(fulltext_results)}, "
                f"merged={len(results)}"
            )

        # Log scores before filtering
        if results:
            scores = [r.get("score", 0) for r in results]
            logger.debug(
                f"Search scores before filter: min={min(scores):.4f}, max={max(scores):.4f}, "
                f"threshold={score_threshold}"
            )

        # Filter by score threshold
        pre_filter_count = len(results)
        if score_threshold > 0:
            results = [r for r in results if r.get("score", 0) >= score_threshold]
            logger.debug(f"Score filter: {pre_filter_count} -> {len(results)} results")

        # Return top_k
        return results[:top_k]

    async def _vector_search(
        self,
        kb_id: UUID,
        query: str,
        limit: int,
        filter_doc_ids: list[UUID] | None = None,
        embedding_dimension: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Vector similarity search using Qdrant.

        Args:
            kb_id: Knowledge base ID
            query: Search query
            limit: Max results to return
            filter_doc_ids: Optional document ID filter
            embedding_dimension: Embedding dimension for column selection

        Returns:
            List of search results with similarity scores
        """
        # Get dimension from KB if not provided
        dim = (
            embedding_dimension or self.embedding_dimension or self._detected_dimension
        )
        if not dim:
            dim = await get_kb_embedding_dimension(kb_id)

        if not dim:
            logger.warning(
                f"No embedding dimension for KB {kb_id}, vector search disabled"
            )
            return []

        try:
            # Generate query embedding
            query_embedding = await self.embed_query(query)
        except Exception as e:
            logger.warning(f"Failed to generate embedding for vector search: {e}")
            return []

        # Validate dimension match
        if len(query_embedding) != dim:
            raise DimensionMismatchError(
                f"Query embedding dimension {len(query_embedding)} doesn't match "
                f"KB dimension {dim}"
            )

        logger.debug(
            f"Vector search: query length={len(query)}, embedding dim={len(query_embedding)}"
        )

        collection = await _ensure_collection(dim)
        query_filter = _build_qdrant_filter(kb_id, filter_doc_ids)

        points = await _qdrant_search(
            collection=collection,
            query_embedding=query_embedding,
            limit=limit,
            query_filter=query_filter,
        )

        logger.info(
            f"Qdrant search: collection={collection}, kb_id={kb_id}, dim={dim}, "
            f"filter_doc_ids={len(filter_doc_ids) if filter_doc_ids else 0}, hits={len(points)}"
        )

        if not points:
            logger.info(
                f"No vectors found for kb {kb_id}, vector search returned empty"
            )
            return []

        chunk_ids = [str(point.id) for point in points]
        chunks = await DocumentChunk.filter(id__in=chunk_ids).prefetch_related(
            "document"
        )
        chunk_map = {str(chunk.id): chunk for chunk in chunks}

        results = []
        for point in points:
            chunk = chunk_map.get(str(point.id))
            if not chunk:
                continue
            metadata = chunk.metadata
            if isinstance(metadata, str):
                try:
                    metadata = json.loads(metadata)
                except (json.JSONDecodeError, TypeError):
                    metadata = None

            raw_score = float(point.score)
            score = _normalize_qdrant_score(raw_score)
            logger.debug(
                f"Qdrant score: raw={raw_score:.6f}, normalized={score:.6f}, chunk_id={chunk.id}"
            )

            results.append(
                {
                    "chunk_id": chunk.id,
                    "document_id": chunk.document_id,
                    "document_name": chunk.document.name if chunk.document else None,
                    "content": chunk.content,
                    "score": round(score, 4),
                    "metadata": metadata,
                    "search_type": "vector",
                }
            )

        return results

    async def _fulltext_search(
        self,
        kb_id: UUID,
        query: str,
        limit: int,
        filter_doc_ids: list[UUID] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Full-text search using database-level filtering and keyword matching.
        """
        # Extract key terms from query
        query_terms = self._extract_search_terms(query)

        # Build base query
        from tortoise.expressions import Q

        query_filter = DocumentChunk.filter(
            document__knowledge_base_id=kb_id
        ).prefetch_related("document")

        if filter_doc_ids:
            query_filter = query_filter.filter(document_id__in=filter_doc_ids)

        # Use database-level filtering
        if query_terms:
            or_conditions = Q()
            for term in query_terms[:5]:
                or_conditions |= Q(content__icontains=term)
            query_filter = query_filter.filter(or_conditions)

        # Get filtered chunks
        chunks = await query_filter.limit(limit * 3)

        query_lower = query.lower()
        results = []
        for chunk in chunks:
            # Quick scoring
            score = self._quick_similarity_score(
                query_lower, query_terms, chunk.content.lower()
            )

            if score > 0:
                results.append(
                    {
                        "chunk_id": chunk.id,
                        "document_id": chunk.document.id,
                        "document_name": chunk.document.name,
                        "content": chunk.content,
                        "score": min(1.0, score),
                        "metadata": chunk.metadata,
                        "search_type": "fulltext",
                    }
                )

        # Sort by score
        results.sort(
            key=lambda x: float(x.get("score") or 0.0),
            reverse=True,
        )
        return results[:limit]

    def _extract_search_terms(self, query: str) -> list[str]:
        """
        Extract search terms from query using jieba for Chinese segmentation.
        """
        # Use jieba for word segmentation (works for both Chinese and English)
        words = jieba.lcut(query)

        # Filter: keep words with length >= 2, remove pure punctuation
        terms = []
        for word in words:
            word = word.strip()
            # Skip empty, single char (unless Chinese), and pure punctuation
            if not word:
                continue
            if len(word) == 1 and not ("\u4e00" <= word <= "\u9fff"):
                continue
            if re.match(r"^[\s\W]+$", word):
                continue
            terms.append(word.lower() if word.isascii() else word)

        # Remove duplicates while preserving order
        seen = set()
        unique_terms = []
        for t in terms:
            if t not in seen:
                seen.add(t)
                unique_terms.append(t)

        return unique_terms

    def _quick_similarity_score(
        self, query: str, query_terms: list[str], content: str
    ) -> float:
        """
        Quick similarity scoring based on term matches.
        """
        if not query_terms:
            return 0.0

        content_lower = content.lower()

        # Count how many terms match
        matches = sum(
            1
            for term in query_terms
            if term in content_lower or term.lower() in content_lower
        )
        if matches == 0:
            return 0.0

        # Base score from match ratio
        base_score = matches / len(query_terms)

        # Bonus for exact phrase match
        query_clean = query.replace(" ", "").lower()
        content_clean = content_lower.replace(" ", "")
        if query_clean in content_clean:
            return min(1.0, base_score + 0.3)

        # Bonus for high match ratio
        if base_score >= 0.8:
            return min(1.0, base_score + 0.1)

        return min(1.0, base_score * 0.9)

    def _estimate_semantic_similarity(self, query: str, content: str) -> float:
        """
        Estimate semantic similarity (placeholder for actual vector similarity).
        Uses character/word overlap and substring matching.
        Supports both Chinese and English text.
        """
        if not query or not content:
            return 0.0

        # Tokenize: for Chinese, use character-level; for English, use word-level
        query_tokens = self._tokenize(query)
        content_tokens = self._tokenize(content)

        if not query_tokens:
            return 0.0

        # Token overlap ratio
        overlap = query_tokens & content_tokens
        overlap_ratio = len(overlap) / len(query_tokens)

        # Substring matching bonus (check if query or parts of it appear in content)
        substring_bonus = 0.0
        if query in content:
            substring_bonus = 0.4
        else:
            # Check for partial matches (sliding window for longer queries)
            query_chars = list(query.replace(" ", ""))
            if len(query_chars) >= 2:
                # Check 2-grams and 3-grams
                matches = 0
                total = 0
                for n in [2, 3, 4]:
                    for i in range(len(query_chars) - n + 1):
                        ngram = "".join(query_chars[i : i + n])
                        total += 1
                        if ngram in content:
                            matches += 1
                if total > 0:
                    substring_bonus = (matches / total) * 0.3

        # Calculate final score (0-1 range)
        score = min(1.0, overlap_ratio * 0.6 + substring_bonus)
        return round(score, 4)

    def _tokenize(self, text: str) -> set[str]:
        """
        Tokenization using jieba for Chinese and space-split for English.
        """
        # Use jieba for segmentation
        words = jieba.lcut(text)

        tokens = set()
        for word in words:
            word = word.strip()
            if not word:
                continue
            # Skip pure punctuation and whitespace
            if re.match(r"^[\s\W]+$", word) and not any(
                "\u4e00" <= c <= "\u9fff" for c in word
            ):
                continue
            # Normalize: lowercase for ASCII
            tokens.add(word.lower() if word.isascii() else word)

        return tokens

    def _calculate_fulltext_score(
        self, query: str, query_terms: list[str], content: str
    ) -> float:
        """
        Calculate full-text search score using jieba tokenization.
        """
        if not query_terms:
            return 0.0

        # Tokenize content
        content_tokens = self._tokenize(content)
        query_token_set = set(query_terms)

        # Check exact phrase match first
        query_clean = query.replace(" ", "").lower()
        content_clean = content.replace(" ", "").lower()
        if query_clean in content_clean:
            return 1.0

        # Token overlap
        matches = query_token_set & content_tokens
        if not matches:
            # Also check case-insensitive
            content_tokens_lower = {t.lower() for t in content_tokens}
            matches = {t for t in query_terms if t.lower() in content_tokens_lower}

        if not matches:
            return 0.0

        # Score based on match ratio
        score = len(matches) / len(query_terms)
        return round(min(1.0, score), 4)

    def _merge_results_rrf(
        self,
        vector_results: list[dict],
        fulltext_results: list[dict],
        k: int = 60,
    ) -> list[dict[str, Any]]:
        """
        Merge results using Reciprocal Rank Fusion (RRF).
        """
        scores: dict[str, float] = {}
        result_map: dict[str, dict] = {}

        # Process vector results
        for rank, result in enumerate(vector_results):
            chunk_id = str(result["chunk_id"])
            rrf_score = 1.0 / (k + rank + 1)
            scores[chunk_id] = scores.get(chunk_id, 0) + rrf_score
            if chunk_id not in result_map:
                result_map[chunk_id] = result

        # Process fulltext results
        for rank, result in enumerate(fulltext_results):
            chunk_id = str(result["chunk_id"])
            rrf_score = 1.0 / (k + rank + 1)
            scores[chunk_id] = scores.get(chunk_id, 0) + rrf_score
            if chunk_id not in result_map:
                result_map[chunk_id] = result

        # Sort by RRF score and update result scores
        sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)

        merged_results = []
        for chunk_id in sorted_ids:
            result = result_map[chunk_id].copy()
            # Normalize RRF score to 0-1 range
            max_rrf = 2.0 / (k + 1)  # Max possible RRF score (rank 0 in both)
            result["score"] = round(min(1.0, scores[chunk_id] / max_rrf), 4)
            result["search_type"] = "hybrid"
            merged_results.append(result)

        return merged_results

    async def delete_document_vectors(self, document_id: UUID) -> int:
        """
        Delete all vectors for a document.

        Args:
            document_id: Document ID

        Returns:
            Number of deleted vectors
        """
        kb_ids = await Document.filter(id=document_id).values_list(
            "knowledge_base_id", flat=True
        )
        kb_id = kb_ids[0] if kb_ids else None
        if kb_id:
            dim = await get_kb_embedding_dimension(kb_id)
            if dim and await _collection_exists(_collection_name(dim)):
                q_filter = qmodels.Filter(
                    must=[
                        qmodels.FieldCondition(
                            key="document_id",
                            match=qmodels.MatchValue(value=str(document_id)),
                        )
                    ]
                )
                await _delete_qdrant_filter(_collection_name(dim), q_filter)

        # Delete chunks (vectors stored in Qdrant)
        deleted = await DocumentChunk.filter(document_id=document_id).delete()
        return deleted

    async def delete_chunk_vector(self, chunk_id: UUID) -> bool:
        """
        Delete vector for a single chunk.

        Args:
            chunk_id: Chunk ID

        Returns:
            True if deleted
        """
        doc_ids = await DocumentChunk.filter(id=chunk_id).values_list(
            "document_id", flat=True
        )
        if doc_ids:
            kb_ids = await Document.filter(id=doc_ids[0]).values_list(
                "knowledge_base_id", flat=True
            )
            kb_id = kb_ids[0] if kb_ids else None
            if kb_id:
                dim = await get_kb_embedding_dimension(kb_id)
                if dim and await _collection_exists(_collection_name(dim)):
                    await _delete_qdrant_points(_collection_name(dim), [str(chunk_id)])

        # Chunk deletion handles embedding deletion
        deleted = await DocumentChunk.filter(id=chunk_id).delete()
        return deleted > 0

    async def update_chunk_vector(
        self, chunk: DocumentChunk, kb_id: UUID | None = None
    ) -> bool:
        """
        Update vector embedding for a chunk.

        Args:
            chunk: DocumentChunk object with updated content
            kb_id: Optional knowledge base ID for dimension validation

        Returns:
            True if updated
        """
        try:
            # Generate new embedding
            embedding = await self.embed_query(chunk.content)
            if kb_id is None:
                kb_ids = await Document.filter(id=chunk.document_id).values_list(
                    "knowledge_base_id", flat=True
                )
                kb_id = kb_ids[0] if kb_ids else None
            if kb_id:
                await _ensure_kb_dimension(kb_id, len(embedding))

            # Update embedding reference
            chunk.embedding_id = f"chunk_{chunk.id}_updated"
            await chunk.save()

            # Store actual embedding vector in Qdrant
            await self._store_embedding(
                chunk.id,
                embedding,
                dimension=len(embedding),
                payload={
                    "kb_id": str(kb_id) if kb_id else "",
                    "document_id": str(chunk.document_id),
                },
            )

            logger.info(f"Updated vector for chunk {chunk.id}")
            return True
        except Exception as e:
            logger.error(f"Error updating chunk vector: {e}")
            return False

    async def add_chunk_vector(self, kb_id: UUID, chunk: DocumentChunk) -> bool:
        """
        Add vector embedding for a new chunk.

        Args:
            kb_id: Knowledge base ID
            chunk: DocumentChunk object

        Returns:
            True if added

        Raises:
            Exception: If embedding generation or storage fails
        """
        # Generate embedding
        embedding = await self.embed_query(chunk.content)
        await _ensure_kb_dimension(kb_id, len(embedding))

        # Store embedding reference
        chunk.embedding_id = f"kb_{kb_id}_chunk_{chunk.id}"
        await chunk.save()

        # Store actual embedding vector in Qdrant
        await self._store_embedding(
            chunk.id,
            embedding,
            dimension=len(embedding),
            payload={
                "kb_id": str(kb_id),
                "document_id": str(chunk.document_id),
            },
        )

        logger.info(f"Added vector for chunk {chunk.id}")
        return True

    async def delete_kb_vectors(self, kb_id: UUID) -> int:
        """
        Delete all vectors for a knowledge base.

        Args:
            kb_id: Knowledge base ID

        Returns:
            Number of deleted vectors
        """
        dim = await get_kb_embedding_dimension(kb_id)
        if dim and await _collection_exists(_collection_name(dim)):
            await _delete_qdrant_filter(
                _collection_name(dim),
                _build_qdrant_filter(kb_id, None),
            )

        # Get all documents in KB
        documents = await Document.filter(knowledge_base_id=kb_id).values_list(
            "id", flat=True
        )

        if not documents:
            return 0

        # Delete all chunks
        deleted = await DocumentChunk.filter(document_id__in=documents).delete()

        return deleted

    async def migrate_existing_chunks(
        self,
        batch_size: int = 100,
        kb_id: UUID | None = None,
    ) -> dict[str, int]:
        """
        Migrate existing chunks that don't have embeddings stored.
        This is useful for updating old data after enabling vector storage.

        Args:
            batch_size: Number of chunks to process at a time
            kb_id: Optional knowledge base ID to limit migration

        Returns:
            Dict with migration statistics
        """
        stats = {"processed": 0, "success": 0, "failed": 0, "skipped": 0}

        logger.info("Qdrant backend: migration is not required")
        return stats

    async def get_embedding_stats(self, kb_id: UUID | None = None) -> dict[str, int]:
        """
        Get statistics about embeddings in the database.

        Args:
            kb_id: Optional knowledge base ID to limit stats

        Returns:
            Dict with stats (total, with_embedding, without_embedding, dimension)
        """
        conn = Tortoise.get_connection("default")

        # Get KB dimension
        dim = None
        if kb_id:
            dim = await get_kb_embedding_dimension(kb_id)

        if kb_id:
            query = """
                SELECT COUNT(*) as total
                FROM document_chunks dc
                JOIN documents d ON dc.document_id = d.id
                WHERE d.knowledge_base_id = $1
            """
            params = [str(kb_id)]
        else:
            query = """
                SELECT COUNT(*) as total
                FROM document_chunks
            """
            params = []

        _, rows = await conn.execute_query(query, params)
        row = rows[0] if rows else {"total": 0}
        total = int(row.get("total", 0))

        with_embedding = 0
        if kb_id and dim:
            if await _collection_exists(_collection_name(dim)):
                client = await _get_qdrant_client()
                count_result = await client.count(
                    collection_name=_collection_name(dim),
                    count_filter=_build_qdrant_filter(kb_id, None),
                    exact=True,
                )
                with_embedding = int(count_result.count)

        result = {
            "total": total,
            "with_embedding": with_embedding,
            "without_embedding": total - with_embedding,
        }

        if dim:
            result["dimension"] = dim

        return result


# Global instance
vector_store = VectorStore()
