from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.models.tool import CustomToolType, ToolType
from app.schemas.clouisle_package import (
    ClouisleDependencyStatus,
    ClouislePackageDependency,
    ClouisleResourceType,
)
from app.schemas.response import BusinessError
from app.services import clouisle_package_resources as resources


class Query:
    def __init__(self, *, first=None, items=()):
        self.first_value = first
        self.items = list(items)

    def prefetch_related(self, *_args):
        return self

    async def first(self):
        return self.first_value

    def __await__(self):
        async def resolve():
            return self.items

        return resolve().__await__()


def test_permissions_and_serialization_helpers():
    permission = SimpleNamespace(code="tool:read")
    wildcard = SimpleNamespace(code="*")
    user = SimpleNamespace(
        is_superuser=False,
        roles=[SimpleNamespace(permissions=[permission])],
    )

    assert resources._has_permission(SimpleNamespace(is_superuser=True), "anything")
    assert resources._has_permission(user, "tool:read")
    assert resources._has_permission(
        SimpleNamespace(
            is_superuser=False, roles=[SimpleNamespace(permissions=[wildcard])]
        ),
        "agent:read",
    )
    assert not resources._has_permission(
        SimpleNamespace(is_superuser=False), "tool:read"
    )
    with pytest.raises(BusinessError):
        resources._require_permission(user, "tool:update")

    identifier = uuid4()
    assert resources._uuid(identifier) == identifier
    assert resources._uuid(None) is None
    assert resources._uuid("invalid") is None
    assert resources._enum_value(None) is None
    assert resources._enum_value(ClouisleResourceType.TOOL) == "tool"
    assert resources._enum_value(12) == "12"
    assert resources._copy_json(None) is None
    original = {"items": [1]}
    copied = resources._copy_json(original)
    copied["items"].append(2)
    assert original == {"items": [1]}


def test_sanitize_dict_recurses_and_removes_secret_variants():
    value = {
        "safe": [{"name": "kept", "access_token": "removed"}],
        "PASSWORD": "removed",
        "apiKey": "removed",
        "authorization": "removed",
        "credentials": "removed",
        7: "kept",
    }

    assert resources._sanitize_dict(value) == {
        "safe": [{"name": "kept"}],
        7: "kept",
    }
    assert resources._sanitize_dict("plain") == "plain"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (
            "/api/v1/upload/files/icons/2026/07/logo.png",
            "assets/avatar-url/icons/2026/07/logo.png",
        ),
        ("https://example.test/not-an-upload.png", None),
        ("/api/v1/upload/files/icons/2026/logo.png", None),
    ],
)
def test_asset_path_validation(value, expected):
    assert resources._asset_package_path("avatar_url", value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("assets/icon/icons/2026/07/logo.png", ("icons", "2026/07", "logo.png")),
        ("documents/doc.txt", None),
        ("assets/icon/too/short", None),
    ],
)
def test_upload_path_validation(value, expected):
    assert resources._upload_path_from_asset_path(value) == expected


def test_asset_source_path_uses_upload_root(monkeypatch, tmp_path):
    monkeypatch.setattr("app.api.v1.endpoints.upload.UPLOAD_ROOT", tmp_path)

    assert resources._asset_source_path("invalid") is None
    assert (
        resources._asset_source_path("assets/icon/icons/2026/07/logo.png")
        == (tmp_path / "icons/2026/07/logo.png").resolve()
    )


def test_collect_payload_assets_skips_invalid_and_missing_files(tmp_path, monkeypatch):
    source = tmp_path / "logo.png"
    source.write_bytes(b"logo")
    monkeypatch.setattr(
        resources,
        "_asset_source_path",
        lambda path: (
            source if path.startswith("assets/icon/") else tmp_path / "missing"
        ),
    )
    payload = {
        "icon": "/api/v1/upload/files/icons/2026/07/logo.png",
        "avatar_url": "/api/v1/upload/files/icons/2026/07/missing.png",
        "other": 3,
    }

    assert resources._collect_payload_assets(
        payload, ("icon", "avatar_url", "other")
    ) == {"assets/icon/icons/2026/07/logo.png": b"logo"}
    assert payload["assets"] == {"icon": "assets/icon/icons/2026/07/logo.png"}
    untouched = {"icon": "external"}
    assert resources._collect_payload_assets(untouched, ("icon",)) == {}
    assert "assets" not in untouched


@pytest.mark.asyncio
async def test_restore_payload_assets_validates_metadata_and_paths(
    tmp_path, monkeypatch
):
    payload = {"icon": "original"}
    assert await resources._restore_payload_assets(payload, None) is payload
    assert await resources._restore_payload_assets({"assets": []}, tmp_path) == {
        "assets": []
    }

    package = tmp_path / "package"
    valid = package / "assets/icon/logo.bin"
    valid.parent.mkdir(parents=True)
    valid.write_bytes(b"asset")
    upload = AsyncMock(return_value={"url": "/restored/logo.bin"})
    monkeypatch.setattr(resources, "save_generated_upload", upload)
    payload = {
        "icon": "original",
        "assets": {
            1: "assets/icon/logo.bin",
            "bad_value": 2,
            "outside": "../outside.bin",
            "missing": "assets/missing.bin",
            "icon": "assets/icon/logo.bin",
        },
    }

    restored = await resources._restore_payload_assets(payload, package)

    assert restored["icon"] == "/restored/logo.bin"
    assert payload["icon"] == "original"
    assert upload.await_args.kwargs["content_type"] == "application/octet-stream"


@pytest.mark.asyncio
async def test_model_dependency_resolution_filters_candidates(monkeypatch):
    candidates = [
        SimpleNamespace(
            id=uuid4(),
            model=SimpleNamespace(model_type="image", provider="p", model_id="m"),
        ),
        SimpleNamespace(
            id=uuid4(),
            model=SimpleNamespace(model_type="llm", provider="other", model_id="m"),
        ),
        SimpleNamespace(
            id=uuid4(),
            model=SimpleNamespace(model_type="llm", provider="p", model_id="other"),
        ),
        SimpleNamespace(
            id=uuid4(),
            model=SimpleNamespace(model_type="llm", provider="p", model_id="m"),
        ),
    ]
    monkeypatch.setattr(
        resources.TeamModel, "filter", lambda **_kwargs: Query(items=candidates)
    )
    dep = ClouislePackageDependency(
        type="model", hints={"model_type": "llm", "provider": "p", "model_id": "m"}
    )

    resolved = await resources._resolve_model_dependency(dep, uuid4())

    assert resolved.status == ClouisleDependencyStatus.RESOLVED
    assert resolved.matched_id == candidates[-1].id

    monkeypatch.setattr(
        resources.TeamModel, "filter", lambda **_kwargs: Query(items=[])
    )
    missing = await resources._resolve_model_dependency(dep, uuid4())
    assert missing.status == ClouisleDependencyStatus.MISSING


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("dep_type", "model_name"),
    [("agent", "Agent"), ("workflow", "Workflow"), ("knowledge_base", "KnowledgeBase")],
)
async def test_resource_dependency_resolves_each_supported_type(
    monkeypatch, dep_type, model_name
):
    item = SimpleNamespace(id=uuid4())
    model = getattr(resources, model_name)
    monkeypatch.setattr(model, "filter", lambda **_kwargs: Query(first=item))

    dep = ClouislePackageDependency(type=dep_type, source_id=str(uuid4()))
    resolved = await resources._resolve_resource_dependency(dep, uuid4())

    assert resolved.status == ClouisleDependencyStatus.RESOLVED
    assert resolved.matched_id == item.id


@pytest.mark.asyncio
async def test_resource_dependency_uses_name_and_marks_invalid_missing(monkeypatch):
    calls = []

    def query(**kwargs):
        calls.append(kwargs)
        return Query()

    monkeypatch.setattr(resources.Tool, "filter", query)
    dep = ClouislePackageDependency(
        type="tool", source_id="bad", hints={"name": "Tool"}
    )

    resolved = await resources._resolve_resource_dependency(dep, uuid4())

    assert len(calls) == 1
    assert calls[0]["name"] == "Tool"
    assert resolved.status == ClouisleDependencyStatus.MISSING
    unsupported = await resources._resolve_resource_dependency(
        ClouislePackageDependency(type="dataset"), uuid4()
    )
    assert unsupported.status == ClouisleDependencyStatus.UNSUPPORTED


def test_resource_field_serialization_rewrites_only_mapped_ids():
    mapped_tool, mapped_model = uuid4(), uuid4()
    payload = {
        "tools_config": [
            {"tool_id": "source-tool"},
            {"tool_id": "unmapped"},
            {"name": "no id"},
        ],
        "model": {"id": "source-model"},
        "max_iterations": "7",
        "hide_tool_calls": True,
        "enable_memory": True,
    }

    fields = resources._agent_fields(
        payload, {"source-tool": mapped_tool, "source-model": mapped_model}
    )

    assert fields["tools_config"][0]["tool_id"] == str(mapped_tool)
    assert fields["tools_config"][1]["tool_id"] == "unmapped"
    assert fields["model_id"] == mapped_model
    assert fields["max_iterations"] == 7
    assert fields["enable_memory"] is True
    assert payload["tools_config"][0]["tool_id"] == "source-tool"

    defaults = resources._tool_fields({"name": "Tool"})
    assert defaults["display_name"] == "Tool"
    assert defaults["type"] == ToolType.CUSTOM
    assert defaults["custom_type"] is None
    configured = resources._tool_fields(
        {"type": ToolType.CUSTOM.value, "custom_type": CustomToolType.HTTP.value}
    )
    assert configured["display_name"] == "Imported Tool"
    assert configured["custom_type"] == CustomToolType.HTTP


def test_recursive_reference_serialization_and_workflow_defaults():
    target = uuid4()
    value = {
        "nodes": [{"id": "source"}, "source", 3],
        "nested": {"value": "unchanged"},
    }

    assert resources._find_values(
        {"toolId": "a", "nested": [{"tool_id": "b"}, {"toolId": None}]},
        ("toolId", "tool_id"),
    ) == ["a", "b"]
    assert resources._find_values("scalar", ("id",)) == []
    rewritten = resources._rewrite_references(value, {"source": target})
    assert rewritten["nodes"][0]["id"] == str(target)
    assert rewritten["nodes"][1] == str(target)
    assert rewritten["nodes"][2] == 3

    manual = resources._workflow_fields({}, {})
    webhook = resources._workflow_fields({"trigger_type": "webhook"}, {})
    assert manual["trigger_type"].value == "manual"
    assert webhook["trigger_type"].value == "manual"


@pytest.mark.asyncio
async def test_model_mapping_refs_and_summaries(monkeypatch):
    model_id, team_model_id = uuid4(), uuid4()
    model = SimpleNamespace(
        id=model_id,
        name="Model",
        provider="provider",
        model_id="slug",
        model_type="llm",
    )
    team_model = SimpleNamespace(id=team_model_id, model_id=model_id, model=model)

    assert await resources._mapped_model_id(None) is None
    monkeypatch.setattr(
        resources.TeamModel, "filter", lambda **_kwargs: Query(first=team_model)
    )
    assert await resources._mapped_model_id(team_model_id) == model_id
    monkeypatch.setattr(resources.TeamModel, "filter", lambda **_kwargs: Query())
    assert await resources._mapped_model_id(team_model_id) == team_model_id

    assert resources._model_hints(model) == {
        "provider": "provider",
        "model_id": "slug",
        "model_type": "llm",
    }
    assert resources._model_summary(team_model)["team_model_id"] == str(team_model_id)
    assert await resources._model_ref(None) is None
    monkeypatch.setattr(resources.Model, "filter", lambda **_kwargs: Query())
    assert await resources._model_ref(model_id) is None
    monkeypatch.setattr(resources.Model, "filter", lambda **_kwargs: Query(first=model))
    assert (await resources._model_ref(model_id))["name"] == "Model"


@pytest.mark.asyncio
async def test_lookup_dependency_summary_all_resource_outcomes(monkeypatch):
    team_id = uuid4()
    assert await resources._lookup_dependency_summary("tool", "bad", team_id) == {
        "name": None,
        "hints": {},
    }
    assert await resources._lookup_dependency_summary("unknown", uuid4(), team_id) == {
        "name": None,
        "hints": {},
    }

    tool = SimpleNamespace(name="tool", display_name="Tool")
    monkeypatch.setattr(resources.Tool, "filter", lambda **_kwargs: Query(first=tool))
    assert await resources._lookup_dependency_summary("tool", uuid4(), team_id) == {
        "name": "Tool",
        "hints": {"name": "tool"},
    }
    for dep_type, model in (
        ("agent", resources.Agent),
        ("workflow", resources.Workflow),
        ("knowledge_base", resources.KnowledgeBase),
    ):
        monkeypatch.setattr(model, "filter", lambda **_kwargs: Query())
        assert await resources._lookup_dependency_summary(
            dep_type, uuid4(), team_id
        ) == {
            "name": None,
            "hints": {},
        }


@pytest.mark.asyncio
async def test_workflow_dependencies_deduplicates_references(monkeypatch):
    lookup = AsyncMock(return_value={"name": "Tool", "hints": {"name": "tool"}})
    monkeypatch.setattr(resources, "_lookup_dependency_summary", lookup)
    definition = {
        "nodes": [
            {"data": {"toolId": "same", "nested": {"tool_id": "same"}}},
            {"data": None},
        ]
    }

    dependencies = await resources._workflow_dependencies(definition, uuid4())

    assert dependencies == [
        {
            "type": "tool",
            "source_id": "same",
            "name": "Tool",
            "required": True,
            "hints": {"name": "tool"},
        }
    ]
    assert lookup.await_count == 2


def test_document_filename_and_restore_validation(tmp_path, monkeypatch):
    assert resources._safe_package_filename("../../doc.txt") == "doc.txt"
    assert resources._safe_package_filename("..") == "document.bin"
    assert resources._safe_package_filename("folder\\name.txt") == "folder_name.txt"

    assert resources._kb_document_package_path(SimpleNamespace(file_path=None)) is None
    missing = SimpleNamespace(file_path=str(tmp_path / "missing"), id=uuid4(), name="x")
    assert resources._kb_document_package_path(missing) is None
    source = tmp_path / "source.txt"
    source.write_bytes(b"document")
    doc = SimpleNamespace(file_path=str(source), id=uuid4(), name="../safe.txt")
    assert resources._kb_document_package_path(doc).endswith("/safe.txt")

    package = tmp_path / "package"
    package.mkdir()
    assert resources._restore_kb_document_file(None, uuid4(), "doc", "name") is None
    assert resources._restore_kb_document_file(package, uuid4(), None, "name") is None
    assert (
        resources._restore_kb_document_file(package, uuid4(), "../source.txt", "name")
        is None
    )
    assert (
        resources._restore_kb_document_file(package, uuid4(), "missing", "name") is None
    )

    packaged = package / "documents/doc.txt"
    packaged.parent.mkdir()
    packaged.write_bytes(b"document")
    target = tmp_path / "storage/doc.txt"
    monkeypatch.setattr(
        resources.document_processor, "get_storage_path", lambda *_args: str(target)
    )
    assert resources._restore_kb_document_file(
        package, uuid4(), "documents/doc.txt", "doc.txt"
    ) == str(target)
    assert target.read_bytes() == b"document"


def test_adapter_registry_contains_each_resource_type():
    assert set(resources._ADAPTERS) == set(ClouisleResourceType)
    for resource_type in ClouisleResourceType:
        assert resources.get_adapter(resource_type).resource_type == resource_type
