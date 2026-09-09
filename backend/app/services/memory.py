"""
Memory service for user memory graph.
Handles entity and relation CRUD, vector embeddings, and graph traversal.
"""

import importlib
import logging
import math
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from app.models.memory import MemoryEntity, MemoryRelation, EntityType, RelationType
from app.models.user import User
from app.core.config import settings
from app.core.i18n import t
from app.services.audit_log import AuditLogService

AsyncQdrantClient: Any = None
qmodels: Any = None

try:
    AsyncQdrantClient = importlib.import_module("qdrant_client").AsyncQdrantClient
    qmodels = importlib.import_module("qdrant_client.http.models")
except Exception:
    pass

logger = logging.getLogger(__name__)


def _memory_tool_error() -> str:
    return t("memory_tool_execution_failed")


def _format_entity_date(dt: Any) -> str | None:
    """Format datetime or date-like value to YYYY-MM-DD string."""
    if dt is None:
        return None
    if isinstance(dt, datetime):
        return dt.strftime("%Y-%m-%d")
    if isinstance(dt, str):
        return dt[:10]
    return str(dt)


def _calculate_recency_score(
    entity: Any, now: datetime, half_life_days: float = 30.0
) -> float:
    """Calculate exponential recency decay score in [0.0, 1.0]."""
    entity_time = getattr(entity, "updated_at", None) or getattr(
        entity, "created_at", None
    )
    if not entity_time:
        return 1.0
    if isinstance(entity_time, str):
        try:
            entity_time = datetime.fromisoformat(entity_time)
        except Exception:
            return 1.0
    if entity_time.tzinfo is None:
        entity_time = entity_time.replace(tzinfo=UTC)
    delta_seconds = max(0.0, (now - entity_time).total_seconds())
    delta_days = delta_seconds / 86400.0
    decay_rate = math.log(2) / max(half_life_days, 1.0)
    return math.exp(-decay_rate * delta_days)


def _calculate_combined_score(
    similarity: float,
    recency: float,
    recency_weight: float = 0.15,
) -> float:
    """Combine vector similarity and recency decay score."""
    sim = max(0.0, min(1.0, float(similarity)))
    w = max(0.0, min(1.0, float(recency_weight)))
    return (1.0 - w) * sim + w * recency


_qdrant_client: Any = None
_memory_collections: set[str] = set()

_MEMORY_MIGRATION_SCROLL_LIMIT = 256


def _coerce_timestamp(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return None
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return int(value.timestamp())


async def _backfill_memory_timestamps(client: Any, collection: str) -> None:
    scroll = getattr(client, "scroll", None)
    set_payload = getattr(client, "set_payload", None)
    if scroll is None or set_payload is None:
        return

    offset: Any = None
    try:
        while True:
            points, next_offset = await scroll(
                collection_name=collection,
                limit=_MEMORY_MIGRATION_SCROLL_LIMIT,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            legacy_points = []
            entity_ids: list[UUID] = []
            for point in points or []:
                payload = getattr(point, "payload", None) or {}
                if payload.get("updated_at_ts") is not None:
                    continue
                try:
                    entity_id = UUID(str(point.id))
                except (TypeError, ValueError):
                    continue
                legacy_points.append((point, entity_id, payload))
                entity_ids.append(entity_id)

            if entity_ids:
                entities = await MemoryEntity.filter(id__in=entity_ids).all()
                entity_by_id = {entity.id: entity for entity in entities}
                for point, entity_id, payload in legacy_points:
                    timestamp = _coerce_timestamp(
                        payload.get("updated_at") or payload.get("created_at")
                    )
                    if timestamp is None:
                        entity = entity_by_id.get(entity_id)
                        timestamp = _coerce_timestamp(
                            getattr(entity, "updated_at", None)
                            or getattr(entity, "created_at", None)
                        )
                    if timestamp is None:
                        continue
                    await set_payload(
                        collection_name=collection,
                        payload={"updated_at_ts": timestamp},
                        points=[point.id],
                    )

            if next_offset is None or next_offset == offset:
                break
            offset = next_offset
    except Exception:
        logger.warning(
            "Failed to backfill updated_at_ts for memory collection %s",
            collection,
            exc_info=True,
        )


async def _ensure_memory_timestamp_index(client: Any, collection: str) -> None:
    try:
        await client.create_payload_index(
            collection_name=collection,
            field_name="updated_at_ts",
            field_schema=getattr(qmodels.PayloadSchemaType, "INTEGER", "integer"),
        )
    except Exception as exc:
        logger.debug(
            "Payload index updated_at_ts already exists or not supported: %s", exc
        )


def _memory_collection_name(dimension: int) -> str:
    """Get collection name for memory entities."""
    return f"memory_entities_dim_{dimension}"


async def _get_qdrant_client() -> Any:
    """Get or create Qdrant client."""
    global _qdrant_client
    if AsyncQdrantClient is None:
        raise RuntimeError("qdrant-client is not installed")
    if _qdrant_client is None:
        _qdrant_client = AsyncQdrantClient(
            url=settings.QDRANT_URL,
            api_key=settings.QDRANT_API_KEY,
            prefer_grpc=False,  # Use HTTP to suppress security warning for local dev
        )
    return _qdrant_client


async def _ensure_memory_collection(dimension: int) -> str:
    """Ensure memory collection exists and migrate legacy payloads."""
    if qmodels is None:
        raise RuntimeError("qdrant-client is not installed")

    collection = _memory_collection_name(dimension)
    if collection in _memory_collections:
        return collection

    client = await _get_qdrant_client()
    try:
        await client.get_collection(collection)
    except Exception:
        await client.create_collection(
            collection_name=collection,
            vectors_config=qmodels.VectorParams(
                size=dimension,
                distance=qmodels.Distance.COSINE,
            ),
        )
        # Create payload index for user_id (critical for user isolation).
        await client.create_payload_index(
            collection_name=collection,
            field_name="user_id",
            field_schema=qmodels.PayloadSchemaType.KEYWORD,
        )
        logger.info("Created memory collection: %s", collection)

    await _ensure_memory_timestamp_index(client, collection)
    await _backfill_memory_timestamps(client, collection)
    _memory_collections.add(collection)
    return collection


class MemoryService:
    """Service for managing user memory graph."""

    @staticmethod
    async def create_entity(
        user_id: UUID,
        name: str,
        entity_type: EntityType | str,
        description: str | None = None,
        properties: dict | None = None,
        source_conversation_id: UUID | None = None,
        source_message_id: UUID | None = None,
        embedding_model_id: UUID | None = None,
    ) -> MemoryEntity:
        """
        Create a new memory entity with vector embedding.

        Args:
            user_id: User ID (for data isolation)
            name: Entity name
            entity_type: Entity type
            description: Entity description
            properties: Additional properties
            source_conversation_id: Source conversation ID
            source_message_id: Source message ID
            embedding_model_id: Embedding model ID

        Returns:
            Created entity
        """
        # Convert string to enum if needed
        if isinstance(entity_type, str):
            entity_type = EntityType(entity_type)

        # Check if entity already exists
        existing = await MemoryEntity.filter(
            user_id=user_id,
            name=name,
            entity_type=entity_type,
        ).first()

        if existing:
            # Update existing entity
            return await MemoryService.update_entity(
                user_id=user_id,
                entity_id=existing.id,
                description=description,
                properties=properties,
            )

        # Create entity
        entity = await MemoryEntity.create(
            user_id=user_id,
            name=name,
            entity_type=entity_type,
            description=description or "",
            properties=properties or {},
            source_conversation_id=source_conversation_id,
            source_message_id=source_message_id,
            embedding_model_id=embedding_model_id,
        )

        # Generate and store embedding
        await MemoryService._add_entity_embedding(entity)

        logger.info(
            f"Created memory entity: {entity.name} ({entity.entity_type}) for user {user_id}"
        )
        return entity

    @staticmethod
    async def update_entity(
        user_id: UUID,
        entity_id: UUID,
        description: str | None = None,
        properties: dict | None = None,
    ) -> MemoryEntity:
        """
        Update an existing memory entity.

        Args:
            user_id: User ID (for authorization)
            entity_id: Entity ID
            description: New description (merged with existing)
            properties: Properties to update/add

        Returns:
            Updated entity
        """
        entity = await MemoryEntity.filter(id=entity_id, user_id=user_id).first()
        if not entity:
            raise ValueError("memory_entity_not_found")

        # Merge description
        if description:
            if entity.description:
                entity.description = f"{entity.description}\n{description}"
            else:
                entity.description = description

        # Merge properties
        if properties:
            entity.properties = {**entity.properties, **properties}

        entity.updated_at = datetime.now(UTC)
        await entity.save()

        # Re-generate embedding
        await MemoryService._update_entity_embedding(entity)

        logger.info(f"Updated memory entity: {entity.name} for user {user_id}")
        return entity

    @staticmethod
    async def delete_entity(user_id: UUID, entity_id: UUID) -> None:
        """
        Delete a memory entity and its relations.

        Args:
            user_id: User ID (for authorization)
            entity_id: Entity ID
        """
        entity = await MemoryEntity.filter(id=entity_id, user_id=user_id).first()
        if not entity:
            raise ValueError("memory_entity_not_found")

        # Delete embedding from Qdrant
        if entity.embedding_id:
            await MemoryService._delete_entity_embedding(
                entity.embedding_id, entity.embedding_model_id
            )

        # Delete entity (relations will be cascade deleted)
        await entity.delete()

        logger.info(f"Deleted memory entity: {entity.name} for user {user_id}")

    @staticmethod
    async def create_relation(
        user_id: UUID,
        source_entity_id: UUID,
        target_entity_id: UUID,
        relation_type: RelationType | str,
        description: str | None = None,
        properties: dict | None = None,
        source_conversation_id: UUID | None = None,
        source_message_id: UUID | None = None,
    ) -> MemoryRelation:
        """
        Create a relation between two entities.

        Args:
            user_id: User ID (for data isolation)
            source_entity_id: Source entity ID
            target_entity_id: Target entity ID
            relation_type: Relation type
            description: Relation description
            properties: Additional properties
            source_conversation_id: Source conversation ID
            source_message_id: Source message ID

        Returns:
            Created relation
        """
        # Convert string to enum if needed
        if isinstance(relation_type, str):
            relation_type = RelationType(relation_type)

        # Verify entities exist and belong to user
        source = await MemoryEntity.filter(id=source_entity_id, user_id=user_id).first()
        target = await MemoryEntity.filter(id=target_entity_id, user_id=user_id).first()

        if not source:
            raise ValueError("memory_source_entity_not_found")
        if not target:
            raise ValueError("memory_target_entity_not_found")

        # Check if relation already exists
        existing = await MemoryRelation.filter(
            user_id=user_id,
            source_entity_id=source_entity_id,
            target_entity_id=target_entity_id,
            relation_type=relation_type,
        ).first()

        if existing:
            return existing

        # Create relation
        relation = await MemoryRelation.create(
            user_id=user_id,
            source_entity_id=source_entity_id,
            target_entity_id=target_entity_id,
            relation_type=relation_type,
            description=description,
            properties=properties or {},
            source_conversation_id=source_conversation_id,
            source_message_id=source_message_id,
        )

        logger.info(
            f"Created memory relation: {source.name} --[{relation_type}]--> {target.name} for user {user_id}"
        )
        return relation

    @staticmethod
    async def delete_relation(user_id: UUID, relation_id: UUID) -> None:
        """
        Delete a memory relation.

        Args:
            user_id: User ID (for authorization)
            relation_id: Relation ID
        """
        relation = await MemoryRelation.filter(id=relation_id, user_id=user_id).first()
        if not relation:
            raise ValueError("memory_relation_not_found")

        await relation.delete()
        logger.info(f"Deleted memory relation for user {user_id}")

    @staticmethod
    async def search_entities(
        user_id: UUID,
        query: str,
        top_k: int = 10,
        entity_type: EntityType | None = None,
        time_window_days: int | None = None,
        recency_weight: float = 0.15,
    ) -> list[MemoryEntity]:
        """
        Search entities using vector similarity, with optional time window filtering and recency decay scoring.

        Args:
            user_id: User ID (for data isolation)
            query: Search query
            top_k: Number of results
            entity_type: Filter by entity type
            time_window_days: Filter to entities updated within last N days
            recency_weight: Weight [0.0, 1.0] for recency decay in final ranking

        Returns:
            List of matching entities in ranked order
        """
        logger.info(
            f"Searching memory for user {user_id}, query: '{query}', top_k: {top_k}"
        )

        # Get embedding for query
        from app.llm import model_manager

        try:
            embedding_result = await model_manager.get_embedding(query, user_id=user_id)
            query_embedding = embedding_result["embedding"]
            dimension = len(query_embedding)
            model_id = embedding_result.get("model_id")
            logger.info(
                f"Generated query embedding: dimension={dimension}, model_id={model_id}"
            )
        except Exception as e:
            logger.error(f"Failed to get embedding for query: {e}")
            return []

        # Ensure collection exists
        collection = await _ensure_memory_collection(dimension)
        logger.info(f"Using Qdrant collection: {collection}")

        # Build filter (CRITICAL: must include user_id)
        if qmodels is None:
            raise RuntimeError("qdrant-client is not installed")

        conditions: list[Any] = [
            qmodels.FieldCondition(
                key="user_id",
                match=qmodels.MatchValue(value=str(user_id)),
            )
        ]

        if entity_type:
            conditions.append(
                qmodels.FieldCondition(
                    key="entity_type",
                    match=qmodels.MatchValue(value=entity_type.value),
                )
            )

        if time_window_days and time_window_days > 0:
            cutoff_ts = int(
                (datetime.now(UTC) - timedelta(days=time_window_days)).timestamp()
            )
            range_cls = getattr(qmodels, "Range", None)
            if range_cls is not None:
                conditions.append(
                    qmodels.FieldCondition(
                        key="updated_at_ts",
                        range=range_cls(gte=cutoff_ts),
                    )
                )
        query_filter = qmodels.Filter(must=conditions)

        # Search in Qdrant
        client = await _get_qdrant_client()
        try:
            response = await client.query_points(
                collection_name=collection,
                query=query_embedding,
                limit=top_k,
                query_filter=query_filter,
            )
            results = response.points
            for i, result in enumerate(results):
                logger.info(
                    f"  Result {i + 1}: id={getattr(result, 'id', None)}, score={getattr(result, 'score', None)}, payload={getattr(result, 'payload', None)}"
                )
        except Exception as e:
            logger.error(f"Qdrant search failed: {e}")
            return []

        # Fetch entities from database
        entity_ids = [UUID(str(point.id)) for point in results]
        entities = await MemoryEntity.filter(
            id__in=entity_ids,
            user_id=user_id,  # Double-check user isolation
        ).all()

        logger.info(f"Found {len(entities)} entities in database")

        # Map entities by ID to preserve candidate order and apply recency scoring
        entity_map = {getattr(e, "id", None): e for e in entities}
        ordered_candidates = [
            entity_map[eid] for eid in entity_ids if eid in entity_map
        ]
        # Preserve any unmapped entities (e.g. mocked entities without ID in unit tests)
        if len(ordered_candidates) < len(entities):
            for e in entities:
                if e not in ordered_candidates:
                    ordered_candidates.append(e)

        now = datetime.now(UTC)

        # Time window filter at entity level (safeguard against missing Qdrant timestamps)
        if time_window_days and time_window_days > 0:
            cutoff_dt = now - timedelta(days=time_window_days)
            filtered = []
            for e in ordered_candidates:
                e_time = (
                    getattr(e, "updated_at", None)
                    or getattr(e, "created_at", None)
                    or now
                )
                if isinstance(e_time, str):
                    try:
                        e_time = datetime.fromisoformat(e_time)
                    except Exception:
                        e_time = now
                if e_time.tzinfo is None:
                    e_time = e_time.replace(tzinfo=UTC)
                if e_time >= cutoff_dt:
                    filtered.append(e)
            ordered_candidates = filtered

        # Compute combined score for recency decay re-ranking
        score_by_id = {
            UUID(str(point.id)): getattr(point, "score", 0.0)
            for point in results
            if getattr(point, "id", None) is not None
        }

        def sort_key(entity: Any) -> float:
            eid = getattr(entity, "id", None)
            sim = score_by_id.get(eid, 0.0) if eid else 0.0
            if recency_weight > 0:
                recency = _calculate_recency_score(entity, now)
                return _calculate_combined_score(sim, recency, recency_weight)
            return float(sim)

        ordered_candidates.sort(key=sort_key, reverse=True)
        final_entities = ordered_candidates[:top_k]

        # Update access tracking for returned entities
        for entity in final_entities:
            entity.access_count += 1
            entity.last_accessed_at = now
            await entity.save()

        return final_entities

    @staticmethod
    async def get_entity_subgraph(
        user_id: UUID,
        entity_ids: list[UUID],
        max_depth: int = 1,
        direction: str = "both",
        relation_types: list[str] | None = None,
        max_nodes: int = 30,
        max_relations: int = 100,
    ) -> dict[str, Any]:
        """Return a bounded, user-scoped subgraph around seed entities."""
        if direction not in {"incoming", "outgoing", "both"}:
            raise ValueError("invalid_graph_direction")

        max_depth = max(0, min(int(max_depth), 3))
        max_nodes = max(1, min(int(max_nodes), 100))
        max_relations = max(1, min(int(max_relations), 500))
        seed_ids = list(dict.fromkeys(entity_ids))
        if not seed_ids:
            return {
                "entities": [],
                "relations": [],
                "entity_depth": {},
                "truncated": False,
            }

        seed_entities = await MemoryEntity.filter(
            user_id=user_id,
            id__in=seed_ids,
        ).all()
        entity_map = {entity.id: entity for entity in seed_entities}
        entity_depth: dict[str, int] = {str(entity.id): 0 for entity in seed_entities}
        frontier = list(entity_map)
        relation_map: dict[Any, MemoryRelation] = {}
        allowed_relation_types = {
            str(getattr(value, "value", value)) for value in (relation_types or [])
        }
        truncated = len(entity_map) < len(seed_ids)

        for depth in range(max_depth):
            if not frontier or len(entity_map) >= max_nodes:
                break

            relation_queries = []
            if direction in {"outgoing", "both"}:
                relation_queries.append(
                    MemoryRelation.filter(
                        user_id=user_id,
                        source_entity_id__in=frontier,
                    )
                )
            if direction in {"incoming", "both"}:
                relation_queries.append(
                    MemoryRelation.filter(
                        user_id=user_id,
                        target_entity_id__in=frontier,
                    )
                )

            candidate_relations: list[MemoryRelation] = []
            seen_candidate_keys: set[Any] = set()
            for query in relation_queries:
                for relation in await query.all():
                    relation_key = getattr(relation, "id", None) or (
                        relation.source_entity_id,
                        relation.target_entity_id,
                        str(
                            getattr(
                                relation.relation_type, "value", relation.relation_type
                            )
                        ),
                    )
                    if relation_key in seen_candidate_keys:
                        continue
                    seen_candidate_keys.add(relation_key)
                    relation_type = getattr(relation, "relation_type", None)
                    relation_type_value = getattr(relation_type, "value", relation_type)
                    if (
                        allowed_relation_types
                        and str(relation_type_value) not in allowed_relation_types
                    ):
                        continue
                    candidate_relations.append(relation)

            endpoint_ids = {
                endpoint_id
                for relation in candidate_relations
                for endpoint_id in (
                    relation.source_entity_id,
                    relation.target_entity_id,
                )
            }
            endpoint_entities = await MemoryEntity.filter(
                user_id=user_id,
                id__in=list(endpoint_ids),
            ).all()
            endpoint_map = {entity.id: entity for entity in endpoint_entities}
            next_frontier: list[UUID] = []

            for relation in candidate_relations:
                source_id = relation.source_entity_id
                target_id = relation.target_entity_id
                if source_id not in endpoint_map or target_id not in endpoint_map:
                    continue

                new_endpoint_ids = [
                    endpoint_id
                    for endpoint_id in (source_id, target_id)
                    if endpoint_id not in entity_map
                ]
                if len(entity_map) + len(new_endpoint_ids) > max_nodes:
                    truncated = True
                    continue
                if len(relation_map) >= max_relations:
                    truncated = True
                    break

                for endpoint_id in new_endpoint_ids:
                    entity_map[endpoint_id] = endpoint_map[endpoint_id]
                    entity_depth[str(endpoint_id)] = depth + 1
                    next_frontier.append(endpoint_id)

                relation_key = getattr(relation, "id", None) or (
                    source_id,
                    target_id,
                    str(
                        getattr(relation.relation_type, "value", relation.relation_type)
                    ),
                )
                relation_map[relation_key] = relation

            frontier = list(dict.fromkeys(next_frontier))
            if len(relation_map) >= max_relations:
                truncated = True
                break

        return {
            "entities": list(entity_map.values()),
            "relations": list(relation_map.values()),
            "entity_depth": entity_depth,
            "truncated": truncated,
        }

    @staticmethod
    async def _add_entity_embedding(entity: MemoryEntity) -> None:
        """Add entity embedding to Qdrant."""
        from app.llm import model_manager

        # Generate embedding content
        content = f"{entity.name}: {entity.description or ''}"
        logger.info(
            f"Generating embedding for entity {entity.id} ({entity.name}), content: '{content}'"
        )

        try:
            embedding_result = await model_manager.get_embedding(
                content, user_id=entity.user_id
            )
            embedding = embedding_result["embedding"]
            dimension = len(embedding)
            model_id = embedding_result.get("model_id")
            logger.info(
                f"Generated embedding: dimension={dimension}, model_id={model_id}"
            )
        except Exception as e:
            logger.error(f"Failed to generate embedding for entity {entity.id}: {e}")
            raise RuntimeError(
                f"Failed to generate embedding: {str(e)}. Please configure a default embedding model in settings."
            )

        # Ensure collection exists
        collection = await _ensure_memory_collection(dimension)
        logger.info(f"Using Qdrant collection: {collection}")

        # Store in Qdrant
        if qmodels is None:
            raise RuntimeError("qdrant-client is not installed")

        client = await _get_qdrant_client()
        point_id = str(entity.id)

        updated_at = getattr(entity, "updated_at", None) or datetime.now(UTC)
        if isinstance(updated_at, str):
            try:
                updated_at = datetime.fromisoformat(updated_at)
            except Exception:
                updated_at = datetime.now(UTC)
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=UTC)
        updated_at_ts = int(updated_at.timestamp())

        payload = {
            "user_id": str(entity.user_id),
            "entity_type": (
                entity.entity_type.value
                if hasattr(entity.entity_type, "value")
                else str(entity.entity_type)
            ),
            "name": entity.name,
            "updated_at_ts": updated_at_ts,
        }

        logger.info(f"Upserting to Qdrant: point_id={point_id}, payload={payload}")

        await client.upsert(
            collection_name=collection,
            points=[
                qmodels.PointStruct(
                    id=point_id,
                    vector=embedding,
                    payload=payload,
                )
            ],
        )

        logger.info(f"Successfully stored embedding in Qdrant for entity {entity.id}")

        # Update entity with embedding info
        entity.embedding_id = point_id
        entity.embedding_model_id = model_id
        await entity.save()
        logger.info(f"Updated entity {entity.id} with embedding_id={point_id}")

    @staticmethod
    async def _update_entity_embedding(entity: MemoryEntity) -> None:
        """Update entity embedding in Qdrant."""
        if entity.embedding_id:
            # Delete old embedding
            await MemoryService._delete_entity_embedding(
                entity.embedding_id, entity.embedding_model_id
            )

        # Add new embedding
        await MemoryService._add_entity_embedding(entity)

    @staticmethod
    async def _delete_entity_embedding(embedding_id: str, model_id: str | None) -> None:
        """Delete entity embedding from Qdrant."""
        if not model_id:
            return

        try:
            # Get model dimension
            from app.llm import model_manager
            from app.models.model import ModelType

            model_config = await model_manager._get_model_config(
                model_id, ModelType.EMBEDDING
            )
            dimension = getattr(model_config, "dimensions", None) or 1536
            collection = _memory_collection_name(dimension)

            client = await _get_qdrant_client()
            await client.delete(
                collection_name=collection,
                points_selector=qmodels.PointIdsList(points=[embedding_id]),
            )
        except Exception as e:
            logger.warning(f"Failed to delete embedding {embedding_id}: {e}")

    @staticmethod
    async def handle_create_entity(
        user_id: UUID,
        name: str,
        entity_type: str,
        description: str | None = None,
        properties: dict | None = None,
    ) -> dict[str, Any]:
        """
        Tool handler for creating memory entity.
        Checks for similar entities and provides warning if found.

        Returns:
            Result dict for LLM
        """
        user = None
        entity = None
        try:
            # Get user for audit log
            user = await User.get(id=user_id)

            # Search for similar entities with same type
            similar_entities = await MemoryEntity.filter(
                user_id=user_id,
                entity_type=entity_type,
            ).all()

            # Check for exact or very similar names
            similar_names = []
            for entity in similar_entities:
                # Exact match or one contains the other
                if (
                    entity.name.lower() == name.lower()
                    or name.lower() in entity.name.lower()
                    or entity.name.lower() in name.lower()
                ):
                    similar_names.append(entity.name)

            # Create entity (will auto-update if exact match exists)
            entity = await MemoryService.create_entity(
                user_id=user_id,
                name=name,
                entity_type=entity_type,
                description=description,
                properties=properties,
            )

            # Log audit
            await AuditLogService.log(
                user=user,
                action="agent_create_memory_entity",
                resource_type="memory_entity",
                resource_id=entity.id,
                resource_name=entity.name,
                operation="create",
                status="success",
                metadata={
                    "entity_type": entity_type,
                    "description": description,
                    "source": "agent_tool",
                },
            )

            # Add warning if similar entities found
            message = t("memory_entity_created_tool", entity_name=entity.name)
            if similar_names:
                message += t(
                    "memory_similar_entities_notice",
                    similar_entities=", ".join(similar_names),
                )

            return {
                "success": True,
                "entity_id": str(entity.id),
                "message": message,
                "similar_entities": similar_names if similar_names else None,
            }
        except Exception as e:
            logger.error(f"Failed to create entity: {e}")

            # Log failed audit
            if user:
                await AuditLogService.log(
                    user=user,
                    action="agent_create_memory_entity",
                    resource_type="memory_entity",
                    resource_id=entity.id if entity else None,
                    resource_name=name,
                    operation="create",
                    status="failed",
                    error_message=str(e),
                    metadata={
                        "entity_type": entity_type,
                        "source": "agent_tool",
                    },
                )

            return {
                "success": False,
                "error": _memory_tool_error(),
            }

    @staticmethod
    async def handle_create_relation(
        user_id: UUID,
        source_entity_name: str,
        target_entity_name: str,
        relation_type: str,
        description: str | None = None,
    ) -> dict[str, Any]:
        """
        Tool handler for creating memory relation.

        Returns:
            Result dict for LLM
        """
        user = None
        relation = None
        try:
            # Get user for audit log
            user = await User.get(id=user_id)

            # Find entities by name
            source = await MemoryEntity.filter(
                user_id=user_id, name=source_entity_name
            ).first()
            target = await MemoryEntity.filter(
                user_id=user_id, name=target_entity_name
            ).first()

            if not source:
                # Log failed audit
                await AuditLogService.log(
                    user=user,
                    action="agent_create_memory_relation",
                    resource_type="memory_relation",
                    resource_id=None,
                    resource_name=f"{source_entity_name} -> {target_entity_name}",
                    operation="create",
                    status="failed",
                    error_message=f"Source entity '{source_entity_name}' not found",
                    metadata={
                        "relation_type": relation_type,
                        "source": "agent_tool",
                    },
                )
                return {
                    "success": False,
                    "error": t(
                        "memory_source_entity_not_found",
                        entity_name=source_entity_name,
                    ),
                }

            if not target:
                # Log failed audit
                await AuditLogService.log(
                    user=user,
                    action="agent_create_memory_relation",
                    resource_type="memory_relation",
                    resource_id=None,
                    resource_name=f"{source_entity_name} -> {target_entity_name}",
                    operation="create",
                    status="failed",
                    error_message=f"Target entity '{target_entity_name}' not found",
                    metadata={
                        "relation_type": relation_type,
                        "source": "agent_tool",
                    },
                )
                return {
                    "success": False,
                    "error": t(
                        "memory_target_entity_not_found",
                        entity_name=target_entity_name,
                    ),
                }

            relation = await MemoryService.create_relation(
                user_id=user_id,
                source_entity_id=source.id,
                target_entity_id=target.id,
                relation_type=relation_type,
                description=description,
            )

            # Log audit
            await AuditLogService.log(
                user=user,
                action="agent_create_memory_relation",
                resource_type="memory_relation",
                resource_id=relation.id,
                resource_name=f"{source.name} -> {target.name}",
                operation="create",
                status="success",
                metadata={
                    "relation_type": relation_type,
                    "source_entity": source.name,
                    "target_entity": target.name,
                    "description": description,
                    "source": "agent_tool",
                },
            )

            return {
                "success": True,
                "relation_id": str(relation.id),
                "message": t(
                    "memory_relation_created_tool",
                    source_name=source.name,
                    relation_type=relation_type,
                    target_name=target.name,
                ),
            }
        except Exception as e:
            logger.error(f"Failed to create relation: {e}")

            # Log failed audit
            if user:
                await AuditLogService.log(
                    user=user,
                    action="agent_create_memory_relation",
                    resource_type="memory_relation",
                    resource_id=relation.id if relation else None,
                    resource_name=f"{source_entity_name} -> {target_entity_name}",
                    operation="create",
                    status="failed",
                    error_message=str(e),
                    metadata={
                        "relation_type": relation_type,
                        "source": "agent_tool",
                    },
                )

            return {
                "success": False,
                "error": _memory_tool_error(),
            }

    @staticmethod
    async def handle_update_entity(
        user_id: UUID,
        entity_name: str,
        description: str | None = None,
        properties: dict | None = None,
    ) -> dict[str, Any]:
        """
        Tool handler for updating memory entity.

        Returns:
            Result dict for LLM
        """
        user = None
        entity = None
        try:
            # Get user for audit log
            user = await User.get(id=user_id)

            # Find entity by name
            entity = await MemoryEntity.filter(
                user_id=user_id, name=entity_name
            ).first()

            if not entity:
                # Log failed audit
                await AuditLogService.log(
                    user=user,
                    action="agent_update_memory_entity",
                    resource_type="memory_entity",
                    resource_id=None,
                    resource_name=entity_name,
                    operation="update",
                    status="failed",
                    error_message=f"Entity '{entity_name}' not found",
                    metadata={
                        "source": "agent_tool",
                    },
                )
                return {
                    "success": False,
                    "error": t(
                        "memory_entity_named_not_found",
                        entity_name=entity_name,
                    ),
                }

            # Store old values for audit
            old_description = entity.description
            old_properties = entity.properties

            entity = await MemoryService.update_entity(
                user_id=user_id,
                entity_id=entity.id,
                description=description,
                properties=properties,
            )

            # Log audit
            changes = {}
            if description is not None and description != old_description:
                changes["description"] = {
                    "before": old_description,
                    "after": description,
                }
            if properties is not None and properties != old_properties:
                changes["properties"] = {
                    "before": str(old_properties),
                    "after": str(properties),
                }

            await AuditLogService.log(
                user=user,
                action="agent_update_memory_entity",
                resource_type="memory_entity",
                resource_id=entity.id,
                resource_name=entity.name,
                operation="update",
                status="success",
                changes=changes if changes else None,
                metadata={
                    "entity_type": entity.entity_type,
                    "source": "agent_tool",
                },
            )

            return {
                "success": True,
                "entity_id": str(entity.id),
                "message": t("memory_entity_updated_tool", entity_name=entity.name),
            }
        except Exception as e:
            logger.error(f"Failed to update entity: {e}")

            # Log failed audit
            if user:
                await AuditLogService.log(
                    user=user,
                    action="agent_update_memory_entity",
                    resource_type="memory_entity",
                    resource_id=entity.id if entity else None,
                    resource_name=entity_name,
                    operation="update",
                    status="failed",
                    error_message=str(e),
                    metadata={
                        "source": "agent_tool",
                    },
                )

            return {
                "success": False,
                "error": _memory_tool_error(),
            }

    @staticmethod
    async def handle_search_memory(
        user_id: UUID,
        query: str,
        top_k: int = 5,
        time_window_days: int | None = None,
        entity_type: str | None = None,
    ) -> dict[str, Any]:
        """
        Tool handler for searching memory.

        Returns:
            Result dict for LLM
        """
        try:
            parsed_entity_type = None
            if entity_type:
                try:
                    parsed_entity_type = EntityType(entity_type)
                except ValueError:
                    parsed_entity_type = None

            parsed_days = None
            if time_window_days is not None:
                try:
                    parsed_days = int(time_window_days)
                    if parsed_days <= 0:
                        parsed_days = None
                except (ValueError, TypeError):
                    parsed_days = None

            entities = await MemoryService.search_entities(
                user_id=user_id,
                query=query,
                top_k=top_k,
                entity_type=parsed_entity_type,
                time_window_days=parsed_days,
            )

            results = [
                {
                    "id": str(e.id),
                    "name": e.name,
                    "type": (
                        e.entity_type.value
                        if hasattr(e.entity_type, "value")
                        else str(e.entity_type)
                    ),
                    "description": e.description,
                    "properties": e.properties or {},
                    "updated_at": _format_entity_date(getattr(e, "updated_at", None)),
                }
                for e in entities
            ]

            if not results:
                return {
                    "success": True,
                    "results": [],
                    "count": 0,
                    "message": t("memory_search_empty"),
                }

            return {
                "success": True,
                "results": results,
                "count": len(results),
                "message": t("memory_search_results_found", count=len(results)),
            }
        except Exception as e:
            logger.error(f"Failed to search memory: {e}")
            return {
                "success": False,
                "error": _memory_tool_error(),
            }

    @staticmethod
    async def handle_get_memory_subgraph(
        user_id: UUID,
        entity_ids: list[str] | list[UUID],
        max_depth: int = 1,
        direction: str = "both",
        relation_types: list[str] | None = None,
    ) -> dict[str, Any]:
        """Return a model-friendly, user-scoped memory subgraph."""
        try:
            all_entity_ids = list(entity_ids)
            requested_entities = all_entity_ids[:5]
            input_truncated = len(all_entity_ids) > len(requested_entities)
            references: list[tuple[str, UUID | str]] = []
            requested_names: list[str] = []
            for raw_entity_id in requested_entities:
                if isinstance(raw_entity_id, UUID):
                    references.append(("id", raw_entity_id))
                    continue
                if not isinstance(raw_entity_id, str):
                    raise ValueError("invalid_entity_reference")
                value = raw_entity_id.strip()
                if not value:
                    raise ValueError("invalid_entity_reference")
                try:
                    references.append(("id", UUID(value)))
                except ValueError:
                    requested_names.append(value)
                    references.append(("name", value))

            entities_by_name: dict[str, MemoryEntity] = {}
            if requested_names:
                named_entities = await MemoryEntity.filter(
                    user_id=user_id,
                    name__in=list(dict.fromkeys(requested_names)),
                ).all()
                for entity in named_entities:
                    entities_by_name.setdefault(entity.name, entity)

            parsed_ids = [
                value if reference_type == "id" else entities_by_name[value].id
                for reference_type, value in references
                if reference_type == "id" or value in entities_by_name
            ]
            graph = await MemoryService.get_entity_subgraph(
                user_id=user_id,
                entity_ids=parsed_ids,
                max_depth=max_depth,
                direction=direction,
                relation_types=relation_types,
                max_nodes=30,
                max_relations=100,
            )
            entities_by_id = {str(entity.id): entity for entity in graph["entities"]}
            depths = graph.get("entity_depth", {})
            entities = [
                {
                    "id": str(entity.id),
                    "name": entity.name,
                    "type": (
                        entity.entity_type.value
                        if hasattr(entity.entity_type, "value")
                        else str(entity.entity_type)
                    ),
                    "description": entity.description,
                    "properties": entity.properties or {},
                    "depth": depths.get(str(entity.id), 0),
                }
                for entity in graph["entities"]
            ]
            relations = []
            for relation in graph["relations"]:
                source = entities_by_id.get(str(relation.source_entity_id))
                target = entities_by_id.get(str(relation.target_entity_id))
                if source is None or target is None:
                    continue
                relation_type = getattr(
                    relation.relation_type, "value", relation.relation_type
                )
                relations.append(
                    {
                        "id": str(relation.id),
                        "source_entity_id": str(relation.source_entity_id),
                        "source_name": source.name,
                        "relation_type": str(relation_type),
                        "target_entity_id": str(relation.target_entity_id),
                        "target_name": target.name,
                        "description": relation.description,
                        "properties": relation.properties or {},
                    }
                )
            return {
                "success": True,
                "entities": entities,
                "relations": relations,
                "truncated": input_truncated or bool(graph.get("truncated", False)),
            }
        except (TypeError, ValueError):
            return {
                "success": False,
                "error": t("memory_subgraph_invalid_request"),
            }
        except Exception as e:
            logger.error(f"Failed to get memory subgraph: {e}")
            return {
                "success": False,
                "error": _memory_tool_error(),
            }
