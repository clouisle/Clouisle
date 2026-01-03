"""
Workflow version control system.

Provides version management for workflows including:
- Version creation and history
- Diff generation between versions
- Rollback capabilities
- Branch/fork support
"""

import json
import hashlib
import logging
from typing import Any
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4
from enum import Enum

from tortoise.transactions import in_transaction

from app.models.workflow import Workflow

logger = logging.getLogger(__name__)


class VersionStatus(str, Enum):
    """Version status."""

    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"
    DEPRECATED = "deprecated"


@dataclass
class WorkflowVersion:
    """Represents a workflow version."""

    version_id: str
    workflow_id: str
    version_number: int
    name: str
    description: str
    definition: dict
    status: VersionStatus
    created_by: str
    created_at: datetime
    published_at: datetime | None = None
    parent_version_id: str | None = None
    content_hash: str = ""
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.content_hash:
            self.content_hash = self._compute_hash()

    def _compute_hash(self) -> str:
        """Compute content hash for the definition."""
        content = json.dumps(self.definition, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "version_id": self.version_id,
            "workflow_id": self.workflow_id,
            "version_number": self.version_number,
            "name": self.name,
            "description": self.description,
            "status": self.status.value,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat(),
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "parent_version_id": self.parent_version_id,
            "content_hash": self.content_hash,
            "metadata": self.metadata,
        }


@dataclass
class VersionDiff:
    """Represents differences between two versions."""

    from_version: str
    to_version: str
    nodes_added: list[dict] = field(default_factory=list)
    nodes_removed: list[dict] = field(default_factory=list)
    nodes_modified: list[dict] = field(default_factory=list)
    edges_added: list[dict] = field(default_factory=list)
    edges_removed: list[dict] = field(default_factory=list)
    config_changes: dict = field(default_factory=dict)

    @property
    def has_changes(self) -> bool:
        """Check if there are any changes."""
        return bool(
            self.nodes_added or
            self.nodes_removed or
            self.nodes_modified or
            self.edges_added or
            self.edges_removed or
            self.config_changes
        )

    @property
    def change_summary(self) -> str:
        """Get a human-readable change summary."""
        parts = []
        if self.nodes_added:
            parts.append(f"+{len(self.nodes_added)} nodes")
        if self.nodes_removed:
            parts.append(f"-{len(self.nodes_removed)} nodes")
        if self.nodes_modified:
            parts.append(f"~{len(self.nodes_modified)} nodes modified")
        if self.edges_added:
            parts.append(f"+{len(self.edges_added)} edges")
        if self.edges_removed:
            parts.append(f"-{len(self.edges_removed)} edges")
        if self.config_changes:
            parts.append(f"{len(self.config_changes)} config changes")
        return ", ".join(parts) if parts else "No changes"

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "from_version": self.from_version,
            "to_version": self.to_version,
            "nodes_added": self.nodes_added,
            "nodes_removed": self.nodes_removed,
            "nodes_modified": self.nodes_modified,
            "edges_added": self.edges_added,
            "edges_removed": self.edges_removed,
            "config_changes": self.config_changes,
            "has_changes": self.has_changes,
            "change_summary": self.change_summary,
        }


class WorkflowVersionManager:
    """
    Manages workflow versions.

    Provides version control operations:
    - Create new versions
    - List version history
    - Compare versions (diff)
    - Rollback to previous versions
    - Publish/archive versions

    Example:
        manager = WorkflowVersionManager()

        # Create a new version
        version = await manager.create_version(
            workflow_id=uuid,
            definition=new_definition,
            name="v2.0",
            description="Added new LLM node",
            user_id=user_uuid,
        )

        # Get version history
        history = await manager.get_history(workflow_id)

        # Compare versions
        diff = await manager.diff(version_id_1, version_id_2)

        # Rollback
        await manager.rollback(workflow_id, version_id)
    """

    # In-memory storage for versions (in production, use database)
    _versions: dict[str, list[WorkflowVersion]] = {}

    async def create_version(
        self,
        workflow_id: UUID,
        definition: dict,
        user_id: UUID,
        name: str | None = None,
        description: str = "",
        auto_publish: bool = False,
    ) -> WorkflowVersion:
        """
        Create a new workflow version.

        Args:
            workflow_id: Workflow UUID
            definition: Workflow definition
            user_id: User creating the version
            name: Optional version name
            description: Version description
            auto_publish: Whether to publish immediately

        Returns:
            Created WorkflowVersion
        """
        workflow_key = str(workflow_id)

        # Get existing versions
        versions = self._versions.get(workflow_key, [])

        # Calculate version number
        version_number = len(versions) + 1

        # Get parent version
        parent_version_id = versions[-1].version_id if versions else None

        # Generate version name if not provided
        if not name:
            name = f"v{version_number}.0"

        # Create version
        version = WorkflowVersion(
            version_id=str(uuid4()),
            workflow_id=workflow_key,
            version_number=version_number,
            name=name,
            description=description,
            definition=definition,
            status=VersionStatus.PUBLISHED if auto_publish else VersionStatus.DRAFT,
            created_by=str(user_id),
            created_at=datetime.utcnow(),
            published_at=datetime.utcnow() if auto_publish else None,
            parent_version_id=parent_version_id,
        )

        # Store version
        if workflow_key not in self._versions:
            self._versions[workflow_key] = []
        self._versions[workflow_key].append(version)

        # Update workflow in database if published
        if auto_publish:
            await self._update_workflow(workflow_id, definition, version.version_id)

        logger.info(f"Created version {version.version_id} for workflow {workflow_id}")
        return version

    async def get_version(
        self,
        version_id: str,
    ) -> WorkflowVersion | None:
        """Get a specific version by ID."""
        for versions in self._versions.values():
            for version in versions:
                if version.version_id == version_id:
                    return version
        return None

    async def get_history(
        self,
        workflow_id: UUID,
        limit: int = 50,
        offset: int = 0,
        status: VersionStatus | None = None,
    ) -> list[WorkflowVersion]:
        """
        Get version history for a workflow.

        Args:
            workflow_id: Workflow UUID
            limit: Maximum versions to return
            offset: Offset for pagination
            status: Filter by status

        Returns:
            List of versions (newest first)
        """
        workflow_key = str(workflow_id)
        versions = self._versions.get(workflow_key, [])

        # Filter by status
        if status:
            versions = [v for v in versions if v.status == status]

        # Sort by version number (descending)
        versions = sorted(versions, key=lambda v: v.version_number, reverse=True)

        # Paginate
        return versions[offset:offset + limit]

    async def get_latest_version(
        self,
        workflow_id: UUID,
        published_only: bool = False,
    ) -> WorkflowVersion | None:
        """Get the latest version of a workflow."""
        workflow_key = str(workflow_id)
        versions = self._versions.get(workflow_key, [])

        if published_only:
            versions = [v for v in versions if v.status == VersionStatus.PUBLISHED]

        if not versions:
            return None

        return max(versions, key=lambda v: v.version_number)

    async def publish_version(
        self,
        version_id: str,
        user_id: UUID,
    ) -> WorkflowVersion:
        """
        Publish a draft version.

        Args:
            version_id: Version to publish
            user_id: User publishing the version

        Returns:
            Updated version
        """
        version = await self.get_version(version_id)
        if not version:
            raise ValueError(f"Version not found: {version_id}")

        if version.status == VersionStatus.PUBLISHED:
            return version

        # Update status
        version.status = VersionStatus.PUBLISHED
        version.published_at = datetime.utcnow()

        # Update workflow in database
        await self._update_workflow(
            UUID(version.workflow_id),
            version.definition,
            version.version_id,
        )

        logger.info(f"Published version {version_id}")
        return version

    async def archive_version(
        self,
        version_id: str,
    ) -> WorkflowVersion:
        """Archive a version."""
        version = await self.get_version(version_id)
        if not version:
            raise ValueError(f"Version not found: {version_id}")

        version.status = VersionStatus.ARCHIVED
        logger.info(f"Archived version {version_id}")
        return version

    async def rollback(
        self,
        workflow_id: UUID,
        version_id: str,
        user_id: UUID,
        create_backup: bool = True,
    ) -> WorkflowVersion:
        """
        Rollback workflow to a previous version.

        Args:
            workflow_id: Workflow UUID
            version_id: Version to rollback to
            user_id: User performing rollback
            create_backup: Whether to create a backup version first

        Returns:
            New version created from rollback
        """
        # Get target version
        target_version = await self.get_version(version_id)
        if not target_version:
            raise ValueError(f"Version not found: {version_id}")

        if target_version.workflow_id != str(workflow_id):
            raise ValueError("Version does not belong to this workflow")

        # Create backup of current state if requested
        if create_backup:
            current = await self.get_latest_version(workflow_id)
            if current:
                current.status = VersionStatus.ARCHIVED
                current.metadata["archived_reason"] = "rollback_backup"

        # Create new version from target
        new_version = await self.create_version(
            workflow_id=workflow_id,
            definition=target_version.definition,
            user_id=user_id,
            name=f"Rollback to {target_version.name}",
            description=f"Rolled back from {target_version.name} (version {target_version.version_number})",
            auto_publish=True,
        )

        new_version.metadata["rollback_from"] = version_id
        logger.info(f"Rolled back workflow {workflow_id} to version {version_id}")

        return new_version

    async def diff(
        self,
        from_version_id: str,
        to_version_id: str,
    ) -> VersionDiff:
        """
        Generate diff between two versions.

        Args:
            from_version_id: Source version
            to_version_id: Target version

        Returns:
            VersionDiff with all changes
        """
        from_version = await self.get_version(from_version_id)
        to_version = await self.get_version(to_version_id)

        if not from_version or not to_version:
            raise ValueError("Version not found")

        return self._compute_diff(
            from_version.definition,
            to_version.definition,
            from_version_id,
            to_version_id,
        )

    async def diff_with_current(
        self,
        workflow_id: UUID,
        version_id: str,
    ) -> VersionDiff:
        """Generate diff between a version and current draft."""
        workflow = await Workflow.filter(id=workflow_id).first()
        if not workflow or not workflow.definition:
            raise ValueError("Workflow not found")

        version = await self.get_version(version_id)
        if not version:
            raise ValueError("Version not found")

        return self._compute_diff(
            version.definition,
            workflow.definition,
            version_id,
            "current",
        )

    def _compute_diff(
        self,
        from_def: dict,
        to_def: dict,
        from_id: str,
        to_id: str,
    ) -> VersionDiff:
        """Compute diff between two workflow definitions."""
        diff = VersionDiff(from_version=from_id, to_version=to_id)

        # Extract nodes and edges
        from_nodes = {n["id"]: n for n in from_def.get("nodes", [])}
        to_nodes = {n["id"]: n for n in to_def.get("nodes", [])}
        from_edges = {self._edge_key(e): e for e in from_def.get("edges", [])}
        to_edges = {self._edge_key(e): e for e in to_def.get("edges", [])}

        # Find added nodes
        for node_id, node in to_nodes.items():
            if node_id not in from_nodes:
                diff.nodes_added.append({
                    "id": node_id,
                    "type": node.get("type"),
                    "label": node.get("data", {}).get("label", ""),
                })

        # Find removed nodes
        for node_id, node in from_nodes.items():
            if node_id not in to_nodes:
                diff.nodes_removed.append({
                    "id": node_id,
                    "type": node.get("type"),
                    "label": node.get("data", {}).get("label", ""),
                })

        # Find modified nodes
        for node_id in set(from_nodes.keys()) & set(to_nodes.keys()):
            from_node = from_nodes[node_id]
            to_node = to_nodes[node_id]

            changes = self._node_changes(from_node, to_node)
            if changes:
                diff.nodes_modified.append({
                    "id": node_id,
                    "type": to_node.get("type"),
                    "changes": changes,
                })

        # Find added edges
        for edge_key, edge in to_edges.items():
            if edge_key not in from_edges:
                diff.edges_added.append({
                    "source": edge.get("source"),
                    "target": edge.get("target"),
                    "sourceHandle": edge.get("sourceHandle"),
                })

        # Find removed edges
        for edge_key, edge in from_edges.items():
            if edge_key not in to_edges:
                diff.edges_removed.append({
                    "source": edge.get("source"),
                    "target": edge.get("target"),
                    "sourceHandle": edge.get("sourceHandle"),
                })

        # Config changes (non-node/edge properties)
        for key in set(from_def.keys()) | set(to_def.keys()):
            if key in ("nodes", "edges"):
                continue
            from_val = from_def.get(key)
            to_val = to_def.get(key)
            if from_val != to_val:
                diff.config_changes[key] = {
                    "from": from_val,
                    "to": to_val,
                }

        return diff

    def _edge_key(self, edge: dict) -> str:
        """Generate unique key for an edge."""
        return f"{edge.get('source')}:{edge.get('sourceHandle', '')}:{edge.get('target')}"

    def _node_changes(self, from_node: dict, to_node: dict) -> list[dict]:
        """Find changes between two nodes."""
        changes = []

        # Check position
        from_pos = from_node.get("position", {})
        to_pos = to_node.get("position", {})
        if from_pos != to_pos:
            changes.append({"field": "position", "type": "moved"})

        # Check data
        from_data = from_node.get("data", {})
        to_data = to_node.get("data", {})

        for key in set(from_data.keys()) | set(to_data.keys()):
            from_val = from_data.get(key)
            to_val = to_data.get(key)
            if from_val != to_val:
                changes.append({
                    "field": f"data.{key}",
                    "from": from_val,
                    "to": to_val,
                })

        return changes

    async def _update_workflow(
        self,
        workflow_id: UUID,
        definition: dict,
        version_id: str,
    ) -> None:
        """Update workflow in database."""
        async with in_transaction():
            workflow = await Workflow.filter(id=workflow_id).first()
            if workflow:
                workflow.definition = definition
                workflow.current_version_id = version_id
                workflow.updated_at = datetime.utcnow()
                await workflow.save()

    async def fork(
        self,
        workflow_id: UUID,
        version_id: str | None,
        new_workflow_id: UUID,
        user_id: UUID,
    ) -> WorkflowVersion:
        """
        Fork a workflow version to a new workflow.

        Args:
            workflow_id: Source workflow
            version_id: Version to fork (latest if None)
            new_workflow_id: Target workflow UUID
            user_id: User creating the fork

        Returns:
            New version in forked workflow
        """
        if version_id:
            source_version = await self.get_version(version_id)
        else:
            source_version = await self.get_latest_version(workflow_id, published_only=True)

        if not source_version:
            raise ValueError("Source version not found")

        # Create version in new workflow
        new_version = await self.create_version(
            workflow_id=new_workflow_id,
            definition=source_version.definition,
            user_id=user_id,
            name="v1.0 (forked)",
            description=f"Forked from workflow {workflow_id}, version {source_version.name}",
            auto_publish=False,
        )

        new_version.metadata["forked_from"] = {
            "workflow_id": str(workflow_id),
            "version_id": source_version.version_id,
        }

        logger.info(f"Forked workflow {workflow_id} to {new_workflow_id}")
        return new_version

    async def get_stats(self, workflow_id: UUID) -> dict:
        """Get version statistics for a workflow."""
        workflow_key = str(workflow_id)
        versions = self._versions.get(workflow_key, [])

        return {
            "total_versions": len(versions),
            "published_versions": len([v for v in versions if v.status == VersionStatus.PUBLISHED]),
            "draft_versions": len([v for v in versions if v.status == VersionStatus.DRAFT]),
            "archived_versions": len([v for v in versions if v.status == VersionStatus.ARCHIVED]),
            "first_version_date": min((v.created_at for v in versions), default=None),
            "latest_version_date": max((v.created_at for v in versions), default=None),
        }


# Global instance
_version_manager: WorkflowVersionManager | None = None


def get_version_manager() -> WorkflowVersionManager:
    """Get global version manager instance."""
    global _version_manager
    if _version_manager is None:
        _version_manager = WorkflowVersionManager()
    return _version_manager
