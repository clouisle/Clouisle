"""Consumer-visible logical metadata and canonical binding CAS behavior."""

import time
from datetime import timedelta

from app.services.sandbox import recovery
from app.services.sandbox.session_store import _redis_text


def test_session_create_conversation_and_configured_touch_retention(sandbox_runtime):
    r = sandbox_runtime
    session = r.run(
        r.sessions.create(
            session_id="session", conversation_id="conversation", ttl_hours=2
        )
    )
    found = r.run(r.sessions.get_by_conversation("conversation"))
    assert found.session_id == session.session_id
    original_creation = session.created_at
    touched = r.run(r.sessions.touch("session", disk_usage_bytes=128))
    assert touched.created_at == original_creation
    assert touched.expires_at == touched.last_accessed_at + timedelta(hours=2)
    assert touched.disk_usage_bytes == 128
    assert r.run(r.sessions.touch("missing")) is None


def test_get_worker_derives_from_single_canonical_binding(sandbox_runtime):
    r = sandbox_runtime
    before = r.bind_session()
    # A record left by pre-versioned releases cannot override canonical placement.
    r.redis.set("sandbox:session-worker:session", "wrong-worker")
    assert r.run(r.sessions.get_worker("session")) == before.worker_id
    assert r.run(r.sessions.get_binding("missing")) is None


def test_recovery_lock_coalesces_and_expired_holder_cannot_commit(sandbox_runtime):
    r = sandbox_runtime
    before = r.bind_session()
    owned = r.run(r.sessions.acquire_recovery("session", before, "one", 1))
    assert owned.status == "RECOVERING"
    assert r.run(r.sessions.acquire_recovery("session", owned, "two", 1)) is None
    r.redis.delete("sandbox:session-recovery:session")
    replacement_owner = r.run(r.sessions.acquire_recovery("session", owned, "two", 1))
    ready = replacement_owner.model_copy(
        update={
            "epoch": replacement_owner.epoch + 1,
            "status": "READY",
            "recovery_id": None,
            "recovery_started_at": None,
        }
    )
    assert not r.run(r.sessions.commit_recovery("session", owned, "one", ready))
    assert r.run(r.sessions.commit_recovery("session", replacement_owner, "two", ready))


def test_stale_metadata_and_round_writes_cannot_regress_rebound_session(
    sandbox_runtime,
):
    r = sandbox_runtime
    before = r.bind_session()
    stale_metadata = r.run(r.sessions.get("session"))
    r.run(r.sessions.begin_round("session", "round", 60))
    r.run(r.sessions.mark_workspace_round("session", "round", expected_binding=before))
    r.registry.remove(r.redis, r.workers["a"])
    r.register(instance_id="new-instance")
    after = r.run(recovery.ensure_ready("session", time.time() + 2))
    stale_metadata.disk_usage_bytes = 999
    assert not r.run(r.sessions.save(stale_metadata))
    assert (
        r.run(
            r.sessions.touch("session", disk_usage_bytes=999, expected_binding=before)
        )
        is None
    )
    assert not r.run(
        r.sessions.mark_workspace_round("session", "stale", expected_binding=before)
    )
    assert not r.run(
        r.sessions.finish_round("session", "round", expected_binding=before)
    )
    assert r.run(r.sessions.get_active_round("session")) == "round"
    assert (
        r.run(
            r.sessions.touch("session", disk_usage_bytes=5, expected_binding=after)
        ).disk_usage_bytes
        == 5
    )
    assert r.run(r.sessions.finish_round("session", "round", expected_binding=after))
    assert r.run(r.sessions.get("session")).disk_usage_bytes == 5


def test_expired_cleanup_keeps_epoch_tombstone_and_removes_indexes(sandbox_runtime):
    r = sandbox_runtime
    before = r.bind_session()
    r.redis.delete("sandbox:session:session")
    r.redis.zadd(r.sessions.INDEX_KEY, {"session": time.time() - 1})
    assert r.run(r.sessions.expired_session_ids(limit=1)) == ["session"]
    assert r.run(r.sessions.cleanup_expired(limit=1)) == 1
    tombstone = r.run(r.sessions.get_binding("session"))
    assert tombstone.status == "UNAVAILABLE" and tombstone.epoch > before.epoch
    assert r.run(r.sessions.expired_session_ids()) == []
    assert not r.run(r.sessions.delete("session", expected_binding=before))
    assert not before.matches(tombstone)


def test_expired_only_cleanup_cannot_delete_refreshed_retention(sandbox_runtime):
    r = sandbox_runtime
    before = r.bind_session()
    assert not r.run(
        r.sessions.delete("session", expected_binding=before, expired_only=True)
    )
    assert r.run(r.sessions.get("session")) is not None
    assert r.run(r.sessions.get_binding("session")) == before


def test_round_finish_is_compare_and_delete(sandbox_runtime):
    r = sandbox_runtime
    r.bind_session()
    r.run(r.sessions.begin_round("session", "round", 60))
    assert not r.run(r.sessions.finish_round("session", "stale"))
    assert r.run(r.sessions.get_active_round("session")) == "round"
    assert r.run(r.sessions.finish_round("session", "round"))
    assert r.run(r.sessions.get_active_round("session")) is None
    assert _redis_text(b"session") == _redis_text("session")
