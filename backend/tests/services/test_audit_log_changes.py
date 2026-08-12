import json
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from types import SimpleNamespace

from app.services import audit_log


class _SampleEnum(Enum):
    DRAFT = "draft"
    PUBLISHED = "published"


class _RaisingStub:
    @property
    def name(self) -> str:
        raise RuntimeError("boom")


def test_json_safe_converts_special_types() -> None:
    svc = audit_log.AuditLogService
    assert svc._json_safe(_SampleEnum.PUBLISHED) == "published"
    assert svc._json_safe(uuid.UUID("12345678-1234-5678-1234-567812345678")) == (
        "12345678-1234-5678-1234-567812345678"
    )
    assert svc._json_safe(datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)) == (
        "2026-01-02T03:04:05+00:00"
    )
    assert svc._json_safe(date(2026, 1, 2)) == "2026-01-02"
    assert svc._json_safe(Decimal("3.14")) == "3.14"


def test_json_safe_truncates_long_strings() -> None:
    svc = audit_log.AuditLogService
    assert svc._json_safe("short") == "short"
    long_str = "x" * 1000
    truncated = svc._json_safe(long_str)
    assert truncated == "x" * 500 + "..."
    assert len(truncated) == 503


def test_json_safe_passthrough_scalars() -> None:
    svc = audit_log.AuditLogService
    assert svc._json_safe(True) is True
    assert svc._json_safe(42) == 42
    assert svc._json_safe(1.5) == 1.5
    assert svc._json_safe(None) is None


def test_json_safe_large_dict_becomes_preview_string() -> None:
    svc = audit_log.AuditLogService
    big = {"nodes": [{"id": f"node-{i}", "label": "y" * 100} for i in range(200)]}
    result = svc._json_safe(big)
    assert isinstance(result, str)
    assert result == json.dumps(big, separators=(",", ":"))[:500] + "..."


def test_json_safe_large_list_becomes_preview_string() -> None:
    svc = audit_log.AuditLogService
    big = ["x" * 600 for _ in range(50)]
    result = svc._json_safe(big)
    assert isinstance(result, str)
    assert result == json.dumps(big, separators=(",", ":"))[:500] + "..."


def test_json_safe_small_dict_recurses_and_converts_nested_values() -> None:
    svc = audit_log.AuditLogService
    uid = uuid.UUID("12345678-1234-5678-1234-567812345678")
    result = svc._json_safe(
        {"chunk_size": 512, "state": _SampleEnum.DRAFT, "ids": [uid, 1]}
    )
    assert result == {"chunk_size": 512, "state": "draft", "ids": [str(uid), 1]}


def test_json_safe_size_bound_holds_for_worst_case_blob() -> None:
    svc = audit_log.AuditLogService
    blob = {"definition": {"payload": "y" * 100_000}}
    result = svc._json_safe(blob)
    assert len(json.dumps(result)) < 2000


def test_snapshot_returns_registry_fields_with_values() -> None:
    svc = audit_log.AuditLogService
    team = SimpleNamespace(name="alpha", description="desc", avatar_url="url")
    assert svc.snapshot(team, "team") == {
        "name": "alpha",
        "description": "desc",
        "avatar_url": "url",
    }


def test_snapshot_missing_attribute_becomes_none() -> None:
    svc = audit_log.AuditLogService
    partial = SimpleNamespace(name="alpha")
    assert svc.snapshot(partial, "team") == {
        "name": "alpha",
        "description": None,
        "avatar_url": None,
    }


def test_snapshot_unknown_resource_type_returns_empty_dict() -> None:
    svc = audit_log.AuditLogService
    assert svc.snapshot(SimpleNamespace(name="x"), "no_such_type") == {}


def test_snapshot_skips_fields_that_raise() -> None:
    svc = audit_log.AuditLogService
    result = svc.snapshot(_RaisingStub(), "team")
    assert result == {"description": None, "avatar_url": None}


def test_snapshot_converts_enum_and_uuid_columns() -> None:
    svc = audit_log.AuditLogService
    agent = SimpleNamespace(
        name="a", status=_SampleEnum.PUBLISHED, model_id=uuid.uuid4()
    )
    snap = svc.snapshot(agent, "agent")
    assert snap["name"] == "a"
    assert snap["status"] == "published"
    assert isinstance(snap["model_id"], str)


def test_json_safe_masks_nested_sensitive_keys_in_small_values() -> None:
    svc = audit_log.AuditLogService
    result = svc._json_safe({"nodes": [{"token": "secret-value-123", "label": "ok"}]})
    assert result == {"nodes": [{"token": "secret-v***", "label": "ok"}]}


def test_json_safe_masks_sensitive_keys_inside_lists() -> None:
    svc = audit_log.AuditLogService
    result = svc._json_safe([{"api_key": "sk-very-long-value", "name": "x"}])
    assert result == [{"api_key": "sk-very-***", "name": "x"}]


def test_json_safe_masks_nested_email_in_small_values() -> None:
    svc = audit_log.AuditLogService
    result = svc._json_safe({"profile": {"email": "alice@example.com"}})
    assert result == {"profile": {"email": "a***e@example.com"}}


def test_json_safe_masks_nested_sensitive_keys_in_oversized_values() -> None:
    svc = audit_log.AuditLogService
    big = {
        "nodes": [
            {"token": "ultra-secret-value", "label": "y" * 600} for _ in range(80)
        ]
    }
    result = svc._json_safe(big)
    assert isinstance(result, str)
    assert "ultra-secret" not in result
    assert "***" in result


def test_build_changes_only_contains_changed_keys() -> None:
    svc = audit_log.AuditLogService
    before = {"name": "old", "description": "same", "status": "draft"}
    after = {"name": "new", "description": "same", "status": "published"}
    assert svc.build_changes(before, after) == {
        "before": {"name": "old", "status": "draft"},
        "after": {"name": "new", "status": "published"},
    }


def test_build_changes_identical_returns_none() -> None:
    svc = audit_log.AuditLogService
    assert svc.build_changes({"a": 1}, {"a": 1}) is None


def test_build_changes_records_key_present_on_one_side() -> None:
    svc = audit_log.AuditLogService
    assert svc.build_changes({"name": "old"}, {}) == {
        "before": {"name": "old"},
        "after": {"name": None},
    }
    assert svc.build_changes({}, {"name": "new"}) == {
        "before": {"name": None},
        "after": {"name": "new"},
    }


def test_build_changes_records_none_vs_value() -> None:
    svc = audit_log.AuditLogService
    assert svc.build_changes({"expires_at": None}, {"expires_at": "2027-01-01"}) == {
        "before": {"expires_at": None},
        "after": {"expires_at": "2027-01-01"},
    }


def test_build_changes_ignores_both_none() -> None:
    svc = audit_log.AuditLogService
    assert svc.build_changes({"a": None}, {"a": None}) is None
