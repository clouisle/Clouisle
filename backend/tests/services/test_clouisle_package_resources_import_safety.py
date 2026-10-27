"""Behavioral import/export safety tests for `.clouisle` resource adapters.

The tests assert what package consumers can observe:

* unauthorized exports fail closed even when internal callers skip the cheap
  role check or ask to skip scope resolution;
* name collisions are reported and resolved only inside the target team;
* imports reject inline secrets and keep only declared connection fields;
* legacy database packages map onto builtin definitions and tell the operator
  that a connection must be bound afterwards.
"""

import sys
from contextlib import asynccontextmanager
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.schemas.clouisle_package import (
    ClouisleConflictAction,
    ClouisleImportInstallRequest,
)
from app.schemas.response import BusinessError, ResponseCode
from app.services import clouisle_package_resources as resources


class Query:
    """Minimal awaitable query double for adapter ORM calls."""

    def __init__(self, *, first=None, exists=False):
        self._first = first
        self._exists = exists

    def prefetch_related(self, *_args):
        return self

    async def first(self):
        return self._first

    async def exists(self):
        return self._exists


class UpdateQuery:
    async def update(self, **_kwargs):
        return 1


@asynccontextmanager
async def transaction():
    yield


def install_request(action=ClouisleConflictAction.INSTALL, **kwargs):
    return ClouisleImportInstallRequest(action=action, **kwargs)


def stub_tools_scope(monkeypatch, side_effect=None):
    module = ModuleType("app.api.v1.endpoints.tools")
    module.check_team_access = AsyncMock(side_effect=side_effect)
    monkeypatch.setitem(sys.modules, module.__name__, module)


def stub_agent_scope(monkeypatch, side_effect=None):
    module = ModuleType("app.api.v1.endpoints.agents")
    module.check_agent_access = AsyncMock(side_effect=side_effect)
    monkeypatch.setitem(sys.modules, module.__name__, module)


def tool(**overrides):
    values = {
        "id": uuid4(),
        "team_id": uuid4(),
        "name": "weather",
        "display_name": "Weather",
        "description": "Forecasts",
        "icon": None,
        "category": "other",
        "type": "custom",
        "custom_type": None,
        "parameters": [],
        "http_config": {"url": "https://example.test"},
        "code_config": {},
        "mcp_config": {},
        "is_enabled": True,
        "approval_policy": {},
    }
    values.update(overrides)
    return SimpleNamespace(**values)


# ---------------------------------------------------------------------------
# Permission isolation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_internal_export_still_enforces_team_scope(monkeypatch):
    existing = tool()
    monkeypatch.setattr(
        resources.Tool, "filter", lambda **_kwargs: Query(first=existing)
    )
    denied = BusinessError(
        code=ResponseCode.PERMISSION_DENIED,
        msg_key="team_access_denied",
        status_code=403,
    )
    stub_tools_scope(monkeypatch, side_effect=denied)

    with pytest.raises(BusinessError) as exc_info:
        await resources.ToolPackageAdapter().export(
            existing.id,
            SimpleNamespace(is_superuser=False, roles=[]),
            check_permission=False,
        )

    assert exc_info.value.msg_key == "team_access_denied"


@pytest.mark.asyncio
async def test_export_without_read_permission_is_denied_even_when_scope_is_skipped():
    with pytest.raises(BusinessError) as exc_info:
        await resources.ToolPackageAdapter().export(
            uuid4(),
            SimpleNamespace(is_superuser=False, roles=[]),
            check_scope=False,
        )

    assert exc_info.value.msg_key == "operation_not_permitted"
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_scope_skip_exports_the_payload(monkeypatch):
    existing = tool(name="internal")
    monkeypatch.setattr(
        resources.Tool, "filter", lambda **_kwargs: Query(first=existing)
    )

    payload, dependencies, name = await resources.ToolPackageAdapter().export(
        existing.id,
        SimpleNamespace(is_superuser=True, roles=[]),
        check_scope=False,
    )

    assert (name, dependencies) == ("internal", [])
    assert payload["name"] == "internal"


@pytest.mark.asyncio
async def test_agent_export_cannot_skip_access_checks(monkeypatch):
    denied = BusinessError(
        code=ResponseCode.PERMISSION_DENIED,
        msg_key="agent_access_denied",
        status_code=403,
    )
    stub_agent_scope(monkeypatch, side_effect=denied)

    with pytest.raises(BusinessError) as exc_info:
        await resources.AgentPackageAdapter().export(
            uuid4(),
            SimpleNamespace(is_superuser=False, roles=[]),
            check_permission=False,
        )

    assert exc_info.value.msg_key == "agent_access_denied"


# ---------------------------------------------------------------------------
# Collisions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("same_name_in_target_team", "expected_type"),
    [(True, "name_exists"), (False, "none")],
)
async def test_conflict_detection_is_limited_to_the_target_team(
    monkeypatch, same_name_in_target_team, expected_type
):
    team_id = uuid4()
    existing = SimpleNamespace(id=uuid4(), name="weather")

    def team_scoped_filter(**kwargs):
        if kwargs.get("team_id") == team_id and same_name_in_target_team:
            return Query(first=existing)
        return Query()

    monkeypatch.setattr(resources.Tool, "filter", team_scoped_filter)

    conflict = await resources.ToolPackageAdapter().detect_conflict(
        {"name": "weather"}, team_id
    )

    assert conflict.type == expected_type
    if same_name_in_target_team:
        assert conflict.existing_id == existing.id
    else:
        assert conflict.existing_id is None


@pytest.mark.asyncio
async def test_update_does_not_touch_a_same_named_tool_in_another_team(monkeypatch):
    monkeypatch.setattr(resources, "in_transaction", transaction)
    target_team = uuid4()
    foreign = tool(name="shared-name", display_name="Foreign")

    def team_scoped_filter(**kwargs):
        if kwargs.get("team_id") == target_team:
            return Query()
        return Query(first=foreign)

    monkeypatch.setattr(resources.Tool, "filter", team_scoped_filter)

    with pytest.raises(BusinessError) as exc_info:
        await resources.ToolPackageAdapter().install(
            manifest=None,
            resource_payload={"name": foreign.name},
            team=SimpleNamespace(id=target_team),
            user=SimpleNamespace(is_superuser=True, roles=[]),
            install_in=install_request(ClouisleConflictAction.UPDATE),
        )

    assert exc_info.value.msg_key == "tool_not_found"
    assert foreign.display_name == "Foreign"


@pytest.mark.asyncio
async def test_install_rejects_a_name_that_already_exists_in_the_team(monkeypatch):
    monkeypatch.setattr(resources, "in_transaction", transaction)
    monkeypatch.setattr(resources.Tool, "filter", lambda **_kwargs: Query(exists=True))

    with pytest.raises(BusinessError) as exc_info:
        await resources.ToolPackageAdapter().install(
            manifest=None,
            resource_payload={"name": "taken"},
            team=SimpleNamespace(id=uuid4()),
            user=SimpleNamespace(is_superuser=True, roles=[]),
            install_in=install_request(),
        )

    assert exc_info.value.msg_key == "clouisle_name_conflict"


@pytest.mark.asyncio
async def test_rename_install_creates_a_new_private_draft(monkeypatch):
    monkeypatch.setattr(resources, "in_transaction", transaction)
    created = SimpleNamespace(id=uuid4())
    create = AsyncMock(return_value=created)

    class ExistsQuery:
        def __init__(self, value):
            self._value = value

        async def exists(self):
            return self._value

    probes = []

    def fake_filter(**kwargs):
        probes.append(kwargs["name"])
        # The base name is taken; the suffixed candidate and the final
        # existence check are free.
        return ExistsQuery(len(probes) == 1)

    monkeypatch.setattr(resources.Workflow, "filter", fake_filter)
    monkeypatch.setattr(resources.Workflow, "create", create)

    result = await resources.WorkflowPackageAdapter().install(
        manifest=None,
        resource_payload={
            "name": "flow",
            "definition": {"nodes": []},
            "trigger_type": "webhook",
        },
        team=SimpleNamespace(id=uuid4()),
        user=SimpleNamespace(is_superuser=True, roles=[]),
        install_in=install_request(ClouisleConflictAction.RENAME),
    )

    assert result.installed == created.id
    stored = create.await_args.kwargs
    assert stored["name"] == "flow_import_1"
    assert stored["status"] == resources.WorkflowStatus.DRAFT
    assert stored["visibility"] == resources.WorkflowVisibility.PRIVATE


# ---------------------------------------------------------------------------
# Safe import
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_import_rejects_inline_secrets():
    with pytest.raises(BusinessError) as exc_info:
        await resources.ToolPackageAdapter().install(
            manifest=None,
            resource_payload={
                "name": "leaky",
                "credentials": {"api_key": "literal"},
                "http_config": {"headers": {"Authorization": "Bearer literal"}},
                "connection_fields": [{"name": "api_key"}],
            },
            team=SimpleNamespace(id=uuid4()),
            user=SimpleNamespace(is_superuser=True, roles=[]),
            install_in=install_request(),
        )

    assert exc_info.value.msg_key == "tool_secret_inline_not_allowed"


@pytest.mark.asyncio
async def test_import_persists_declared_connection_fields_without_literals(
    monkeypatch,
):
    monkeypatch.setattr(resources, "in_transaction", transaction)
    created = SimpleNamespace(id=uuid4())
    create = AsyncMock(return_value=created)
    monkeypatch.setattr(resources.Tool, "filter", lambda **_kwargs: Query(exists=False))
    monkeypatch.setattr(resources.Tool, "create", create)

    result = await resources.ToolPackageAdapter().install(
        manifest=None,
        resource_payload={
            "name": "weather-api",
            "display_name": "Weather API",
            "type": "custom",
            "custom_type": "http",
            "http_config": {
                "url": "https://api.example.test",
                "headers": {"X-Api-Key": "{{api_key}}"},
            },
            "connection_fields": [
                {
                    "name": " api_key ",
                    "label": "API key",
                    "input_type": "password",
                    "value": "must-not-persist",
                }
            ],
        },
        team=SimpleNamespace(id=uuid4()),
        user=SimpleNamespace(is_superuser=True, roles=[]),
        install_in=install_request(),
    )

    assert result.installed == created.id
    stored = create.await_args.kwargs
    assert stored["credentials"] == {}
    assert stored["is_enabled"] is False
    declared = stored["connection_fields"]
    assert [field["name"] for field in declared] == ["api_key"]
    assert "value" not in declared[0]


@pytest.mark.asyncio
async def test_agent_import_rejects_duplicate_builtin_tools():
    with pytest.raises(BusinessError) as exc_info:
        await resources.AgentPackageAdapter().install(
            manifest=None,
            resource_payload={
                "name": "duplicate-builtins",
                "tools_config": [
                    {"type": "builtin", "name": "web_search"},
                    {"type": "builtin", "name": "web_search"},
                ],
            },
            team=SimpleNamespace(id=uuid4()),
            user=SimpleNamespace(is_superuser=True, roles=[]),
            install_in=install_request(),
        )

    assert exc_info.value.msg_key == "clouisle_builtin_tool_duplicate"


# ---------------------------------------------------------------------------
# Legacy database packages
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_legacy_database_import_installs_builtin_and_requests_connection(
    monkeypatch,
):
    definition = SimpleNamespace(
        id=uuid4(),
        approval_policy={"default_decision": "allow"},
        is_enabled=True,
        definition_version=1,
    )
    monkeypatch.setattr(
        "app.services.builtin_tools.get_builtin_definition",
        AsyncMock(return_value=definition),
    )

    def fake_filter(**kwargs):
        if "id" in kwargs:
            return UpdateQuery()
        return Query()

    monkeypatch.setattr(resources.Tool, "filter", fake_filter)

    result = await resources.ToolPackageAdapter().install(
        manifest=None,
        resource_payload={
            "type": "custom",
            "custom_type": "database",
            "name": "legacy-db",
            "database_config": {"db_type": "postgres"},
            "approval_policy": {"default_decision": "allow"},
        },
        team=SimpleNamespace(id=uuid4()),
        user=SimpleNamespace(is_superuser=True, roles=[]),
        install_in=install_request(),
    )

    assert result.installed == definition.id
    assert result.warnings == ["clouisle_database_connection_required"]


@pytest.mark.asyncio
async def test_legacy_database_import_rejects_an_unknown_engine():
    with pytest.raises(BusinessError) as exc_info:
        await resources.ToolPackageAdapter().install(
            manifest=None,
            resource_payload={
                "type": "custom",
                "custom_type": "database",
                "name": "legacy-db",
                "database_config": {"db_type": "oracle"},
            },
            team=SimpleNamespace(id=uuid4()),
            user=SimpleNamespace(is_superuser=True, roles=[]),
            install_in=install_request(),
        )

    assert exc_info.value.msg_key == "database_engine_unsupported"
