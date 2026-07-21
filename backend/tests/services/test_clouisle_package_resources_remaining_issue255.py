from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.schemas.clouisle_package import ClouislePackageDependency
from app.services import clouisle_package_resources as resources


class Query:
    def __init__(self, first=None):
        self.value = first

    def prefetch_related(self, *_args):
        return self

    async def first(self):
        return self.value


@pytest.mark.asyncio
async def test_base_adapter_defaults_and_dependency_dispatch(monkeypatch):
    adapter = resources.ToolPackageAdapter()
    assert await adapter.export_files({}) == {}
    payload = {}
    assert (
        await resources.ResourcePackageAdapter.materialize_files(adapter, payload, None)
        is payload
    )

    model_result = SimpleNamespace(kind="model")
    resource_result = SimpleNamespace(kind="resource")
    resolve_model = AsyncMock(return_value=model_result)
    resolve_resource = AsyncMock(return_value=resource_result)
    monkeypatch.setattr(resources, "_resolve_model_dependency", resolve_model)
    monkeypatch.setattr(resources, "_resolve_resource_dependency", resolve_resource)
    manifest = SimpleNamespace(
        dependencies=[
            ClouislePackageDependency(type="model"),
            ClouislePackageDependency(type="tool"),
        ]
    )

    assert await adapter.resolve_dependencies(manifest, uuid4(), SimpleNamespace()) == [
        model_result,
        resource_result,
    ]


@pytest.mark.asyncio
async def test_abstract_adapter_methods_raise_when_called_directly():
    adapter = resources.ToolPackageAdapter()
    calls = (
        resources.ResourcePackageAdapter.export(adapter, uuid4(), SimpleNamespace()),
        resources.ResourcePackageAdapter.detect_conflict(adapter, {}, uuid4()),
        resources.ResourcePackageAdapter.install(
            adapter,
            manifest=None,
            resource_payload={},
            team=SimpleNamespace(),
            user=SimpleNamespace(),
            install_in=SimpleNamespace(),
        ),
    )
    for call in calls:
        with pytest.raises(NotImplementedError):
            await call


@pytest.mark.asyncio
async def test_asset_adapter_delegates_and_empty_conflicts(monkeypatch):
    collect = Mock(return_value={})
    restore = AsyncMock(return_value={"restored": True})
    monkeypatch.setattr(resources, "_collect_payload_assets", collect)
    monkeypatch.setattr(resources, "_restore_payload_assets", restore)

    adapters = (
        (resources.AgentPackageAdapter(), ("icon", "avatar_url")),
        (resources.WorkflowPackageAdapter(), ("icon",)),
        (resources.KnowledgeBasePackageAdapter(), ("icon",)),
    )
    payload = {"icon": "value"}
    package_dir = SimpleNamespace()
    for adapter, fields in adapters:
        await adapter.export_files(payload)
        assert collect.call_args.args == (payload, fields)
        assert await adapter.materialize_files(payload, package_dir) == {
            "restored": True
        }

    for adapter, model in (
        (resources.AgentPackageAdapter(), resources.Agent),
        (resources.WorkflowPackageAdapter(), resources.Workflow),
        (resources.KnowledgeBasePackageAdapter(), resources.KnowledgeBase),
    ):
        monkeypatch.setattr(model, "filter", lambda **_kwargs: Query())
        assert (await adapter.detect_conflict({"name": "new"}, uuid4())).type == "none"


@pytest.mark.asyncio
async def test_lookup_model_dependency_summary(monkeypatch):
    model = SimpleNamespace(
        name="Model", provider="local", model_id="model-v1", model_type="llm"
    )
    team_model = SimpleNamespace(model=model)
    monkeypatch.setattr(
        resources.TeamModel, "filter", lambda **_kwargs: Query(team_model)
    )

    assert await resources._lookup_dependency_summary("model", uuid4(), uuid4()) == {
        "name": "Model",
        "hints": {
            "provider": "local",
            "model_id": "model-v1",
            "model_type": "llm",
        },
    }

    monkeypatch.setattr(resources.TeamModel, "filter", lambda **_kwargs: Query())
    assert await resources._lookup_dependency_summary("model", uuid4(), uuid4()) == {
        "name": None,
        "hints": {},
    }
