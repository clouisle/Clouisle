"""
Memory service for user memory graph.
Handles entity and relation CRUD, vector embeddings, and graph traversal.
"""

import importlib
import logging
from datetime import datetime
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

_qdrant_client: Any = None
_memory_collections: set[str] = set()


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
    """Ensure memory collection exists in Qdrant."""
    if qmodels is None:
        raise RuntimeError("qdrant-client is not installed")

    collection = _memory_collection_name(dimension)
    if collection in _memory_collections:
        return collection

    client = await _get_qdrant_client()
    try:
        await client.get_collection(collection)
    except Exception:
        # Create collection
        await client.create_collection(
            collection_name=collection,
            vectors_config=qmodels.VectorParams(
                size=dimension,
                distance=qmodels.Distance.COSINE,
            ),
        )
        # Create payload index for user_id (critical for user isolation)
        await client.create_payload_index(
            collection_name=collection,
            field_name="user_id",
            field_schema=qmodels.PayloadSchemaType.KEYWORD,
        )
        logger.info(f"Created memory collection: {collection}")

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
            raise ValueError("Entity not found")

        # Merge description
        if description:
            if entity.description:
                entity.description = f"{entity.description}\n{description}"
            else:
                entity.description = description

        # Merge properties
        if properties:
            entity.properties = {**entity.properties, **properties}

        entity.updated_at = datetime.utcnow()
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
            raise ValueError("Entity not found")

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

        if not source or not target:
            raise ValueError("Source or target entity not found")

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
            raise ValueError("Relation not found")

        await relation.delete()
        logger.info(f"Deleted memory relation for user {user_id}")

    @staticmethod
    async def search_entities(
        user_id: UUID,
        query: str,
        top_k: int = 10,
        entity_type: EntityType | None = None,
    ) -> list[MemoryEntity]:
        """
        Search entities using vector similarity.

        Args:
            user_id: User ID (for data isolation)
            query: Search query
            top_k: Number of results
            entity_type: Filter by entity type

        Returns:
            List of matching entities
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
            logger.info(f"Qdrant search returned {len(results)} results")
            for i, result in enumerate(results):
                logger.info(
                    f"  Result {i + 1}: id={result.id}, score={result.score}, payload={result.payload}"
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

        # Update access tracking
        for entity in entities:
            entity.access_count += 1
            entity.last_accessed_at = datetime.utcnow()
            await entity.save()

        return entities

    @staticmethod
    async def get_entity_subgraph(
        user_id: UUID,
        entity_ids: list[UUID],
        max_depth: int = 1,
    ) -> dict[str, Any]:
        """
        Get subgraph around given entities.

        Args:
            user_id: User ID (for data isolation)
            entity_ids: Starting entity IDs
            max_depth: Maximum traversal depth (1 = direct neighbors only)

        Returns:
            Dict with entities and relations
        """
        # Fetch starting entities
        entities = await MemoryEntity.filter(
            user_id=user_id,
            id__in=entity_ids,
        ).all()

        # Fetch outgoing relations (1-hop)
        relations = (
            await MemoryRelation.filter(
                user_id=user_id,
                source_entity_id__in=entity_ids,
            )
            .prefetch_related("source_entity", "target_entity")
            .all()
        )

        # Collect neighbor entity IDs
        neighbor_ids = [r.target_entity_id for r in relations]

        # Fetch neighbor entities
        neighbors = await MemoryEntity.filter(
            user_id=user_id,
            id__in=neighbor_ids,
        ).all()

        return {
            "entities": entities + neighbors,
            "relations": relations,
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

        payload = {
            "user_id": str(entity.user_id),
            "entity_type": entity.entity_type.value,
            "name": entity.name,
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
                "error": str(e),
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
                "error": str(e),
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
                "error": str(e),
            }

    @staticmethod
    async def handle_search_memory(
        user_id: UUID,
        query: str,
        top_k: int = 5,
    ) -> dict[str, Any]:
        """
        Tool handler for searching memory.

        Returns:
            Result dict for LLM
        """
        try:
            entities = await MemoryService.search_entities(
                user_id=user_id,
                query=query,
                top_k=top_k,
            )

            results = [
                {
                    "name": e.name,
                    "type": e.entity_type.value,
                    "description": e.description,
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
                "error": str(e),
            }
