"""
Vector store service for knowledge base.
Uses pgvector for vector storage and similarity search.

Supports dynamic embedding dimensions - each knowledge base can use a different
embedding model with different dimensions. Embedding columns are created dynamically
as needed (embedding_768, embedding_1024, embedding_1536, etc.).
"""

import json
import logging
import re
from typing import Any, TYPE_CHECKING
from uuid import UUID

import jieba
from tortoise import Tortoise

from app.models.knowledge_base import DocumentChunk, Document, KnowledgeBase
from app.services.usage_tracker import QuotaExceededError

# Avoid circular import - import model_manager lazily
if TYPE_CHECKING:
    from app.llm import model_manager as _model_manager

logger = logging.getLogger(__name__)

# Initialize jieba (disable verbose output)
jieba.setLogLevel(logging.WARNING)

# Cache for existing embedding columns to avoid repeated DB queries
_existing_columns: set[int] = set()

# pgvector HNSW index maximum dimension limit
HNSW_MAX_DIMENSION = 2000


def _get_model_manager():
    """Get model manager lazily to avoid circular import."""
    from app.llm import model_manager
    return model_manager


async def ensure_embedding_column(dimension: int) -> str:
    """
    Ensure embedding column for specified dimension exists.
    Creates the column and HNSW index if they don't exist.
    
    Args:
        dimension: Embedding dimension (768, 1024, 1536, etc.)
        
    Returns:
        Column name (e.g., "embedding_768")
    """
    global _existing_columns
    
    col_name = f"embedding_{dimension}"
    
    # Check cache first
    if dimension in _existing_columns:
        return col_name
    
    conn = Tortoise.get_connection("default")
    
    # Check if column exists in database
    _, rows = await conn.execute_query(f"""
        SELECT column_name FROM information_schema.columns 
        WHERE table_name = 'document_chunks' AND column_name = '{col_name}'
    """)
    
    if rows:
        _existing_columns.add(dimension)
        logger.debug(f"Column {col_name} already exists")
        return col_name
    
    # Create column
    try:
        await conn.execute_query(f"""
            ALTER TABLE document_chunks 
            ADD COLUMN {col_name} vector({dimension})
        """)
        logger.info(f"Created embedding column: {col_name}")
    except Exception as e:
        # Column might have been created by another process
        logger.warning(f"Could not create column {col_name}: {e}")
    
    # Create HNSW index for this dimension (only if <= 2000)
    if dimension <= HNSW_MAX_DIMENSION:
        index_name = f"document_chunks_{col_name}_hnsw_idx"
        try:
            await conn.execute_query(f"""
                CREATE INDEX IF NOT EXISTS {index_name}
                ON document_chunks 
                USING hnsw ({col_name} vector_cosine_ops)
            """)
            logger.info(f"Created HNSW index: {index_name}")
        except Exception as e:
            logger.warning(f"Could not create index {index_name}: {e}")
    else:
        logger.info(f"Skipping HNSW index for {col_name} (dimension {dimension} > {HNSW_MAX_DIMENSION})")
    
    _existing_columns.add(dimension)
    return col_name


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
    pass


class VectorStore:
    """
    Vector store service using pgvector.

    Handles:
    - Embedding generation
    - Vector storage in PostgreSQL with pgvector
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

    def _get_column_name(self, dimension: int | None = None) -> str:
        """Get the embedding column name for the given dimension."""
        dim = dimension or self.embedding_dimension or self._detected_dimension
        if not dim:
            raise ValueError("Embedding dimension not set")
        return f"embedding_{dim}"

    def _format_vector(self, embedding: list[float]) -> str:
        """
        Format embedding vector for pgvector.

        Args:
            embedding: List of floats

        Returns:
            pgvector formatted string "[0.1,0.2,...]"
        """
        return "[" + ",".join(str(x) for x in embedding) + "]"

    async def _store_embedding(
        self, chunk_id: UUID, embedding: list[float], dimension: int | None = None
    ) -> None:
        """
        Store embedding vector in pgvector column.

        Args:
            chunk_id: Chunk ID
            embedding: Embedding vector
            dimension: Embedding dimension (uses detected/configured dimension if not provided)
        """
        dim = dimension or self.embedding_dimension or self._detected_dimension
        if not dim:
            dim = len(embedding)
            self._detected_dimension = dim
        
        # Ensure column exists
        col_name = await ensure_embedding_column(dim)
        
        conn = Tortoise.get_connection("default")
        vector_str = self._format_vector(embedding)
        await conn.execute_query(
            f"UPDATE document_chunks SET {col_name} = $1::vector WHERE id = $2",
            [vector_str, str(chunk_id)],
        )

    async def _batch_store_embeddings(
        self, chunk_ids: list[UUID], embeddings: list[list[float]], dimension: int | None = None
    ) -> None:
        """
        Batch store embedding vectors in pgvector column.

        Args:
            chunk_ids: List of chunk IDs
            embeddings: List of embedding vectors
            dimension: Embedding dimension (uses detected/configured dimension if not provided)
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
        
        # Ensure column exists
        col_name = await ensure_embedding_column(dim)

        conn = Tortoise.get_connection("default")

        # Use simple individual updates - more reliable than complex CASE WHEN
        for chunk_id, embedding in zip(chunk_ids, embeddings):
            vector_str = self._format_vector(embedding)
            try:
                await conn.execute_query(
                    f"UPDATE document_chunks SET {col_name} = $1::vector WHERE id = $2::uuid",
                    [vector_str, str(chunk_id)],
                )
            except Exception as e:
                logger.error(f"Failed to store embedding for chunk {chunk_id}: {e}")
                raise

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
        Store document chunks with embeddings in pgvector.
        
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
        
        # Handle KB dimension management
        if kb_id:
            kb_dim = await get_kb_embedding_dimension(kb_id)
            
            if kb_dim is None:
                # First document - set KB dimension
                await set_kb_embedding_dimension(kb_id, detected_dim)
                logger.info(f"Set KB {kb_id} embedding dimension to {detected_dim}")
            elif kb_dim != detected_dim:
                # Dimension mismatch
                raise DimensionMismatchError(
                    f"Embedding dimension mismatch: KB uses {kb_dim}, "
                    f"but model produces {detected_dim}. "
                    f"Please use a model with {kb_dim}-dimensional embeddings."
                )

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

        # Batch store embeddings in pgvector
        try:
            await self._batch_store_embeddings(chunk_ids, embeddings, detected_dim)
            logger.info(f"Stored {len(embeddings)} embeddings (dim={detected_dim}) for document {document.id}")
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
            results = await self._vector_search(kb_id, query, top_k * 2, filter_doc_ids, embedding_dimension)
        elif search_mode == "fulltext":
            results = await self._fulltext_search(
                kb_id, query, top_k * 2, filter_doc_ids
            )
        else:  # hybrid
            # Get results from both methods
            vector_results = await self._vector_search(
                kb_id, query, top_k, filter_doc_ids, embedding_dimension
            )
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
        Vector similarity search using pgvector cosine distance.

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
        dim = embedding_dimension or self.embedding_dimension or self._detected_dimension
        if not dim:
            dim = await get_kb_embedding_dimension(kb_id)
        
        if not dim:
            logger.warning(f"No embedding dimension for KB {kb_id}, using fulltext search")
            return await self._fulltext_search(kb_id, query, limit, filter_doc_ids)
        
        col_name = f"embedding_{dim}"
        
        try:
            # Generate query embedding
            query_embedding = await self.embed_query(query)
        except Exception as e:
            logger.warning(f"Failed to generate embedding for vector search: {e}")
            # Fall back to fulltext search
            return await self._fulltext_search(kb_id, query, limit, filter_doc_ids)
        
        # Validate dimension match
        if len(query_embedding) != dim:
            logger.warning(
                f"Query embedding dimension {len(query_embedding)} doesn't match "
                f"KB dimension {dim}, falling back to fulltext search"
            )
            return await self._fulltext_search(kb_id, query, limit, filter_doc_ids)

        conn = Tortoise.get_connection("default")
        vector_str = self._format_vector(query_embedding)

        logger.debug(f"Vector search: query length={len(query)}, embedding dim={len(query_embedding)}, column={col_name}")

        # Build the query with optional document filter
        if filter_doc_ids:
            doc_ids_str = ", ".join(f"'{str(did)}'" for did in filter_doc_ids)
            filter_clause = f"AND dc.document_id IN ({doc_ids_str})"
        else:
            filter_clause = ""

        # Use cosine distance (<=>) for similarity search
        # pgvector cosine distance = 1 - cosine_similarity
        # So: cosine_similarity = 1 - cosine_distance
        # cosine_distance range is [0, 2], cosine_similarity range is [-1, 1]
        # We normalize to [0, 1] for practical use: (1 - distance + 1) / 2 = 1 - distance/2
        # But for better scoring, we use: max(0, 1 - distance) to get [0, 1] range
        query_sql = f"""
            SELECT 
                dc.id as chunk_id,
                dc.document_id,
                dc.content,
                dc.chunk_index,
                dc.metadata,
                d.name as document_name,
                GREATEST(0, 1 - (dc.{col_name} <=> $1::vector)) as similarity
            FROM document_chunks dc
            JOIN documents d ON dc.document_id = d.id
            WHERE d.knowledge_base_id = $2
                AND dc.{col_name} IS NOT NULL
                {filter_clause}
            ORDER BY dc.{col_name} <=> $1::vector
            LIMIT $3
        """

        try:
            _, rows = await conn.execute_query(
                query_sql, [vector_str, str(kb_id), limit]
            )
            logger.debug(f"Vector search returned {len(rows)} results")
        except Exception as e:
            logger.error(f"Vector search query failed: {e}")
            # Fall back to fulltext search
            return await self._fulltext_search(kb_id, query, limit, filter_doc_ids)

        # If no results with embeddings, fall back to fulltext
        if not rows:
            logger.info(f"No vectors found for kb {kb_id}, falling back to fulltext search")
            return await self._fulltext_search(kb_id, query, limit, filter_doc_ids)

        results = []
        for row in rows:
            # Parse metadata JSON if present
            metadata = row.get("metadata")
            if isinstance(metadata, str):
                try:
                    metadata = json.loads(metadata)
                except (json.JSONDecodeError, TypeError):
                    metadata = None

            similarity = float(row.get("similarity", 0))

            results.append(
                {
                    "chunk_id": row["chunk_id"],
                    "document_id": row["document_id"],
                    "document_name": row["document_name"],
                    "content": row["content"],
                    "score": round(similarity, 4),
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
        # Delete chunks (vectors stored with chunks in embedding column)
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
        # Chunk deletion handles embedding deletion since embedding is a column
        deleted = await DocumentChunk.filter(id=chunk_id).delete()
        return deleted > 0

    async def update_chunk_vector(self, chunk: DocumentChunk) -> bool:
        """
        Update vector embedding for a chunk.

        Args:
            chunk: DocumentChunk object with updated content

        Returns:
            True if updated
        """
        try:
            # Generate new embedding
            embedding = await self.embed_query(chunk.content)

            # Update embedding reference
            chunk.embedding_id = f"chunk_{chunk.id}_updated"
            await chunk.save()

            # Store actual embedding vector in pgvector
            await self._store_embedding(chunk.id, embedding)

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

        # Store embedding reference
        chunk.embedding_id = f"kb_{kb_id}_chunk_{chunk.id}"
        await chunk.save()

        # Store actual embedding vector in pgvector
        await self._store_embedding(chunk.id, embedding)

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
        This is useful for updating old data after enabling pgvector.

        Args:
            batch_size: Number of chunks to process at a time
            kb_id: Optional knowledge base ID to limit migration

        Returns:
            Dict with migration statistics
        """
        stats = {"processed": 0, "success": 0, "failed": 0, "skipped": 0}

        # Get KB dimension if specified
        dim = None
        if kb_id:
            dim = await get_kb_embedding_dimension(kb_id)
        
        col_name = f"embedding_{dim}" if dim else None

        # Build query for chunks without embeddings
        conn = Tortoise.get_connection("default")

        if kb_id and col_name:
            # Get chunks for specific KB using the KB's dimension column
            query = f"""
                SELECT dc.id, dc.content
                FROM document_chunks dc
                JOIN documents d ON dc.document_id = d.id
                WHERE d.knowledge_base_id = $1
                    AND dc.{col_name} IS NULL
                ORDER BY dc.created_at
                LIMIT $2
            """
            params = [str(kb_id), batch_size]
        else:
            # For general migration, we need to detect dimension per chunk
            logger.warning("General migration without KB ID not supported in dynamic dimension mode")
            return stats

        while True:
            _, rows = await conn.execute_query(query, params)

            if not rows:
                break

            chunk_ids = []
            contents = []

            for row in rows:
                chunk_ids.append(row["id"])
                contents.append(row["content"])

            stats["processed"] += len(rows)

            try:
                # Generate embeddings
                embeddings = await self.embed_texts(contents)
                
                # Validate dimension
                if embeddings and dim and len(embeddings[0]) != dim:
                    logger.error(
                        f"Embedding dimension mismatch in migration: "
                        f"expected {dim}, got {len(embeddings[0])}"
                    )
                    stats["failed"] += len(rows)
                    break

                # Store embeddings
                await self._batch_store_embeddings(chunk_ids, embeddings, dim)

                stats["success"] += len(rows)
                logger.info(f"Migrated {len(rows)} chunks")
            except Exception as e:
                logger.error(f"Error migrating batch: {e}")
                stats["failed"] += len(rows)

            # If we got fewer rows than batch_size, we're done
            if len(rows) < batch_size:
                break

        logger.info(
            f"Migration complete: {stats['success']} success, "
            f"{stats['failed']} failed, {stats['skipped']} skipped"
        )
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
        
        col_name = f"embedding_{dim}" if dim else None

        if kb_id and col_name:
            query = f"""
                SELECT 
                    COUNT(*) as total,
                    COUNT(dc.{col_name}) as with_embedding
                FROM document_chunks dc
                JOIN documents d ON dc.document_id = d.id
                WHERE d.knowledge_base_id = $1
            """
            params = [str(kb_id)]
        elif kb_id:
            # KB exists but no dimension set yet - count all chunks
            query = """
                SELECT 
                    COUNT(*) as total,
                    0 as with_embedding
                FROM document_chunks dc
                JOIN documents d ON dc.document_id = d.id
                WHERE d.knowledge_base_id = $1
            """
            params = [str(kb_id)]
        else:
            # General stats - just count total chunks
            query = """
                SELECT 
                    COUNT(*) as total,
                    0 as with_embedding
                FROM document_chunks
            """
            params = []

        _, rows = await conn.execute_query(query, params)
        row = rows[0] if rows else {"total": 0, "with_embedding": 0}

        total = int(row.get("total", 0))
        with_embedding = int(row.get("with_embedding", 0))

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
