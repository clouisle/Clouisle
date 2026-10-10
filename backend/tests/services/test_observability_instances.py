import hashlib
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services import observability_instances as service

OBSERVED_MS = 1_791_547_200_000
INSTANCE_ID = "0123456789abcdef"


def _payload(**changes):
    sample = {
        "instance_id": INSTANCE_ID,
        "name": "API Pod A",
        "role": "api",
        "cpu_percent": 25.0,
        "memory_percent": 50.0,
        "metric_scope": "host",
        "observed_at_ms": OBSERVED_MS,
    }
    sample.update(changes)
    return json.dumps(sample)


def test_hostname_workers_share_identity_without_exposing_raw_hostname():
    first = service._resolve_identity(None, None, "api-pod-a")
    second = service._resolve_identity("", "", "api-pod-a")
    assert (
        first
        == second
        == (
            hashlib.sha256(b"api-pod-a").hexdigest()[:16],
            "api-pod-a",
        )
    )
    assert len(first[0]) == 16
    assert "api-pod-a" not in first[0]


def test_distinct_pods_enumerate_with_distinct_visible_identities():
    first = service._resolve_identity(None, None, "api-pod-a")
    second = service._resolve_identity(None, None, "api-pod-b")
    assert first[0] != second[0]
    assert first[1] == "api-pod-a"
    assert second[1] == "api-pod-b"


def test_configured_identity_is_independent_of_hostname_and_display_name():
    first = service._resolve_identity("deployment-a", "API A", "old-host")
    renamed = service._resolve_identity("deployment-a", "Renamed API", "new-host")
    assert first[0] == renamed[0] == hashlib.sha256(b"deployment-a").hexdigest()[:16]
    assert first[1] == "API A"
    assert renamed[1] == "Renamed API"
    assert service._resolve_identity("deployment-b", "API A", "old-host")[0] != first[0]


@pytest.mark.parametrize(
    ("cpu", "memory", "expected"),
    [
        (0, 0, "healthy"),
        (69.999, 79.999, "healthy"),
        (70, 79.999, "warning"),
        (69.999, 80, "warning"),
        (100, 100, "warning"),
        (None, 50, "unavailable"),
        (25, None, "unavailable"),
        (None, 100, "unavailable"),
        (100, None, "unavailable"),
        (None, None, "unavailable"),
    ],
)
def test_current_resource_state_uses_legacy_warning_thresholds(cpu, memory, expected):
    assert service._sample_state(cpu, memory) == expected


@pytest.mark.parametrize(
    ("age_ms", "expected"),
    [
        (0, "healthy"),
        (30_000, "healthy"),
        (30_001, "stale"),
        (60_000, "stale"),
        (60_001, "offline"),
        (299_999, "offline"),
    ],
)
def test_server_time_aging_keeps_last_metrics_and_observation(age_ms, expected):
    row = service._decode_instance(INSTANCE_ID, _payload(), OBSERVED_MS + age_ms)
    assert row == {
        "instance_id": INSTANCE_ID,
        "name": "API Pod A",
        "role": "api",
        "cpu_percent": 25.0,
        "memory_percent": 50.0,
        "metric_scope": "host",
        "observed_at": datetime.fromtimestamp(OBSERVED_MS / 1000, UTC).isoformat(),
        "state": expected,
    }


@pytest.mark.parametrize("age_ms", [300_000, 300_001, 600_000])
def test_five_minute_retention_omits_expired_samples(age_ms):
    assert (
        service._decode_instance(INSTANCE_ID, _payload(), OBSERVED_MS + age_ms) is None
    )


@pytest.mark.parametrize(
    ("age_ms", "expected"),
    [(0, "warning"), (30_000, "warning"), (30_001, "stale"), (60_001, "offline")],
)
def test_age_overrides_last_resource_warning_without_erasing_value(age_ms, expected):
    row = service._decode_instance(
        INSTANCE_ID, _payload(cpu_percent=95), OBSERVED_MS + age_ms
    )
    assert row["state"] == expected
    assert row["cpu_percent"] == 95


@pytest.mark.parametrize(
    ("age_ms", "expected"),
    [
        (0, "unavailable"),
        (30_000, "unavailable"),
        (30_001, "stale"),
        (60_001, "offline"),
    ],
)
def test_missing_metric_does_not_hide_presence_age(age_ms, expected):
    row = service._decode_instance(
        INSTANCE_ID, _payload(cpu_percent=None), OBSERVED_MS + age_ms
    )
    assert row["state"] == expected
    assert row["cpu_percent"] is None
    assert row["memory_percent"] == 50
    assert row["observed_at"] is not None


@pytest.mark.parametrize(
    "value",
    [
        None,
        True,
        False,
        "50",
        {},
        [],
        -0.01,
        100.01,
        float("nan"),
        float("inf"),
        float("-inf"),
        10**400,
    ],
)
def test_invalid_metric_is_unavailable_not_a_fake_resource_measurement(value):
    row = service._decode_instance(
        INSTANCE_ID, _payload(cpu_percent=value), OBSERVED_MS
    )
    assert row["cpu_percent"] is None
    assert row["memory_percent"] == 50
    assert row["state"] == "unavailable"


@pytest.mark.parametrize("value", [0, 0.1, 70, 99.9, 100])
def test_valid_metrics_preserve_inclusive_percentage_range(value):
    assert service._percent(value) == value


@pytest.mark.parametrize(
    "payload",
    [None, {}, b"\xff", "{", "[]", "null", "123", '"sample"'],
)
def test_malformed_record_is_not_presented_as_an_instance(payload):
    assert service._decode_instance(INSTANCE_ID, payload, OBSERVED_MS) is None


@pytest.mark.parametrize(
    "changes",
    [
        {"instance_id": "fedcba9876543210"},
        {"role": "worker"},
        {"metric_scope": "container"},
        {"metric_scope": None},
        {"name": ""},
        {"name": None},
        {"name": 42},
        {"observed_at_ms": None},
        {"observed_at_ms": True},
        {"observed_at_ms": "1791547200000"},
        {"observed_at_ms": 1.5},
        {"observed_at_ms": -1},
        {"observed_at_ms": OBSERVED_MS + 1},
        {"observed_at_ms": float("nan")},
        {"observed_at_ms": float("inf")},
    ],
)
def test_records_with_untrusted_identity_scope_or_timestamp_are_omitted(changes):
    assert (
        service._decode_instance(INSTANCE_ID, _payload(**changes), OBSERVED_MS) is None
    )


@pytest.mark.parametrize(
    "instance_id",
    [None, 42, "", "0123456789abcde", "0123456789abcdefg", "0123456789abcdeG", b"\xff"],
)
def test_invalid_index_identity_cannot_create_an_instance(instance_id):
    assert service._decode_instance(instance_id, _payload(), OBSERVED_MS) is None


def test_missing_metric_field_is_unavailable_with_other_value_retained():
    payload = json.loads(_payload())
    del payload["memory_percent"]
    row = service._decode_instance(INSTANCE_ID, json.dumps(payload), OBSERVED_MS)
    assert row["cpu_percent"] == 25
    assert row["memory_percent"] is None
    assert row["state"] == "unavailable"


def test_observed_timestamp_is_utc_with_millisecond_precision():
    row = service._decode_instance(
        INSTANCE_ID,
        _payload(observed_at_ms=OBSERVED_MS + 123),
        OBSERVED_MS + 456,
    )
    observed = datetime.fromisoformat(row["observed_at"])
    assert observed.tzinfo == UTC
    assert observed.microsecond == 123_000
    assert row["state"] == "healthy"


def test_multiple_retained_instances_sort_stably_and_skip_invalid_records():
    identities = ["1111111111111111", "2222222222222222", "3333333333333333"]
    entries = [
        [identities[2], _payload(instance_id=identities[2], name="Beta")],
        [identities[1], _payload(instance_id=identities[1], name="alpha")],
        [
            identities[0].encode(),
            _payload(instance_id=identities[0], name="Alpha").encode(),
        ],
        [
            "4444444444444444",
            _payload(
                instance_id="4444444444444444", observed_at_ms=OBSERVED_MS - 300_000
            ),
        ],
        [INSTANCE_ID, "{"],
        None,
        [INSTANCE_ID],
    ]
    rows = service._decode_instances(entries, OBSERVED_MS)
    reversed_rows = service._decode_instances(list(reversed(entries)), OBSERVED_MS)
    assert [row["instance_id"] for row in rows] == identities
    assert rows == reversed_rows


def test_missing_psutil_reports_no_measurements(monkeypatch):
    monkeypatch.setattr(service, "psutil", None)
    assert service._sample_host_metrics() == (None, None)


@pytest.mark.parametrize("failed_metric", ["cpu", "memory"])
def test_failed_host_metric_preserves_other_measurement(monkeypatch, failed_metric):
    def cpu_percent(*, interval):
        if failed_metric == "cpu":
            raise OSError("CPU measurement failed")
        return 25

    def virtual_memory():
        if failed_metric == "memory":
            raise OSError("Memory measurement failed")
        return SimpleNamespace(percent=50)

    monkeypatch.setattr(
        service,
        "psutil",
        SimpleNamespace(cpu_percent=cpu_percent, virtual_memory=virtual_memory),
    )
    expected = (None, 50) if failed_metric == "cpu" else (25, None)
    assert service._sample_host_metrics() == expected


@pytest.mark.asyncio
async def test_reporter_skips_closed_and_unowned_instances():
    closed_redis = SimpleNamespace(eval=AsyncMock(return_value=1))
    closed = service.ApiInstanceReporter(redis=closed_redis)
    closed._closed.set()
    assert await closed.refresh_once() is False
    closed_redis.eval.assert_not_awaited()

    unowned_redis = SimpleNamespace(eval=AsyncMock(return_value=0))
    unowned = service.ApiInstanceReporter(redis=unowned_redis)
    assert await unowned.refresh_once() is False
    unowned_redis.eval.assert_awaited_once()


@pytest.mark.asyncio
async def test_reporter_publishes_fresh_host_sample_after_election(monkeypatch):
    redis = SimpleNamespace(eval=AsyncMock(side_effect=[1, 1]))
    monkeypatch.setattr(service, "_sample_host_metrics", lambda: (25, 50))
    reporter = service.ApiInstanceReporter(
        identity="service-a", name="API A", redis=redis
    )

    assert await reporter.refresh_once() is True

    publish = redis.eval.await_args_list[1]
    sample = json.loads(publish.args[6])
    assert sample["instance_id"] == reporter.instance_id
    assert sample["name"] == "API A"
    assert sample["cpu_percent"] == 25
    assert sample["memory_percent"] == 50


@pytest.mark.asyncio
async def test_reporter_does_not_publish_after_close_during_sampling(monkeypatch):
    redis = SimpleNamespace(eval=AsyncMock(return_value=1))
    reporter = service.ApiInstanceReporter(redis=redis)

    async def close_during_sampling(*_args):
        reporter._closed.set()
        return 25, 50

    monkeypatch.setattr(service.asyncio, "to_thread", close_during_sampling)

    assert await reporter.refresh_once() is False
    assert redis.eval.await_count == 1


@pytest.mark.asyncio
async def test_reporter_run_exits_cleanly_when_closed(monkeypatch):
    redis = SimpleNamespace(eval=AsyncMock(return_value=1))
    reporter = service.ApiInstanceReporter(redis=redis)

    async def stop_after_refresh():
        reporter._closed.set()
        return False

    monkeypatch.setattr(reporter, "refresh_once", stop_after_refresh)

    await reporter.run()

    redis.eval.assert_awaited_once_with(
        service._RELEASE_SCRIPT, 1, reporter._lease_key, reporter.owner_id
    )


@pytest.mark.parametrize(
    ("reply", "available"),
    [([str(OBSERVED_MS), []], True), ([str(OBSERVED_MS), None], False)],
)
@pytest.mark.asyncio
async def test_list_instances_validates_registry_reply(reply, available):
    redis = SimpleNamespace(eval=AsyncMock(return_value=reply))

    result = await service.list_api_instances(redis=redis)

    assert result["available"] is available
    assert result["instances"] == []
