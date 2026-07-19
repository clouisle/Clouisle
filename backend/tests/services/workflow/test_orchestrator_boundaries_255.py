"""Boundary coverage for workflow orchestration helpers."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.services.workflow.orchestrator import WorkflowOrchestrator


class TestWorkflowDefinitionCache:
    @pytest.mark.asyncio
    async def test_cached_definition_skips_cache_write(self):
        orchestrator = WorkflowOrchestrator(enable_cache=False, enable_metrics=False)
        cache = MagicMock()
        cache.get_workflow = AsyncMock(return_value={"nodes": ["cached"]})
        cache.set_workflow = AsyncMock()
        orchestrator._cache = cache

        workflow = MagicMock(id=uuid4(), definition={"nodes": ["database"]})
        workflow.updated_at = datetime(2026, 1, 2, 3, 4, 5)

        assert await orchestrator._get_workflow_definition(workflow) == {
            "nodes": ["cached"]
        }
        cache.get_workflow.assert_awaited_once_with(
            str(workflow.id), version=str(workflow.updated_at.timestamp())
        )
        cache.set_workflow.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_definition_without_timestamp_is_cached_without_version(self):
        orchestrator = WorkflowOrchestrator(enable_cache=False, enable_metrics=False)
        cache = MagicMock()
        cache.get_workflow = AsyncMock(return_value=None)
        cache.set_workflow = AsyncMock()
        orchestrator._cache = cache

        definition = {"nodes": []}
        workflow = MagicMock(id=uuid4(), definition=definition, updated_at=None)

        assert await orchestrator._get_workflow_definition(workflow) is definition
        cache.get_workflow.assert_awaited_once_with(str(workflow.id), version=None)
        cache.set_workflow.assert_awaited_once_with(
            str(workflow.id), definition, version=None
        )


class TestChildNodes:
    def test_child_nodes_follow_plan_execution_order_and_exclude_siblings(self):
        orchestrator = WorkflowOrchestrator(enable_cache=False, enable_metrics=False)
        plan = MagicMock()
        plan.nodes = {
            "first": MagicMock(node_data={"parentId": "loop"}),
            "sibling": MagicMock(node_data={"parentId": "other"}),
            "second": MagicMock(node_data={"parentId": "loop"}),
        }
        plan.get_execution_order.return_value = ["second", "sibling", "first"]

        assert orchestrator._get_child_nodes(plan, "loop") == ["second", "first"]
