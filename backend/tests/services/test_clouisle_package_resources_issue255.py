from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest

from app.schemas.clouisle_package import ClouisleDependencyStatus
from app.services import clouisle_package_resources as resources


class Query:
    def __init__(self, result):
        self.result = result

    def prefetch_related(self, *_args):
        return self

    async def first(self):
        return self.result

    def __await__(self):
        async def resolve():
            return self.result

        return resolve().__await__()


def dependency(**overrides):
    values = {
        "type": "tool",
        "source_id": None,
        "name": None,
        "hints": {},
        "status": None,
        "matched_id": None,
        "message": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
async def test_model_dependency_matches_all_hints_and_reports_missing(monkeypatch):
    team_id = uuid4()
    matched_id = uuid4()
    team_models = [
        SimpleNamespace(
            id=uuid4(),
            model=SimpleNamespace(model_type="chat", provider="other", model_id="one"),
        ),
        SimpleNamespace(
            id=matched_id,
            model=SimpleNamespace(model_type="chat", provider="openai", model_id="one"),
        ),
    ]
    model_filter = Mock(return_value=Query(team_models))
    monkeypatch.setattr(resources.TeamModel, "filter", model_filter)

    matched = dependency(
        type="model",
        hints={"model_type": "chat", "provider": "openai", "model_id": "one"},
    )
    assert await resources._resolve_model_dependency(matched, team_id) is matched
    assert matched.status == ClouisleDependencyStatus.RESOLVED
    assert matched.matched_id == matched_id
    model_filter.assert_called_once_with(team_id=team_id, is_enabled=True)

    missing = dependency(type="model")
    assert await resources._resolve_model_dependency(missing, team_id) is missing
    assert missing.status == ClouisleDependencyStatus.MISSING
    assert missing.message == "clouisle_dependency_missing"
    model_filter.assert_called_once()


@pytest.mark.asyncio
async def test_resource_dependency_uses_id_then_name_and_handles_terminal_states(
    monkeypatch,
):
    team_id = uuid4()
    source_id = uuid4()
    resolved_id = uuid4()
    calls = []

    def tool_filter(**kwargs):
        calls.append(kwargs)
        if kwargs.get("id") == source_id:
            return Query(None)
        if kwargs.get("name") == "fallback":
            return Query(SimpleNamespace(id=resolved_id))
        return Query(None)

    monkeypatch.setattr(resources.Tool, "filter", tool_filter)

    resolved = dependency(source_id=str(source_id), hints={"name": "fallback"})
    assert await resources._resolve_resource_dependency(resolved, team_id) is resolved
    assert resolved.status == ClouisleDependencyStatus.RESOLVED
    assert resolved.matched_id == resolved_id
    assert calls == [
        {"id": source_id, "team_id": team_id},
        {"name": "fallback", "team_id": team_id},
    ]

    missing = dependency(source_id="not-a-uuid", name="absent")
    await resources._resolve_resource_dependency(missing, team_id)
    assert missing.status == ClouisleDependencyStatus.MISSING
    assert missing.message == "clouisle_dependency_missing"

    unsupported = dependency(type="unknown")
    await resources._resolve_resource_dependency(unsupported, team_id)
    assert unsupported.status == ClouisleDependencyStatus.UNSUPPORTED
    assert unsupported.message == "clouisle_dependency_missing"
