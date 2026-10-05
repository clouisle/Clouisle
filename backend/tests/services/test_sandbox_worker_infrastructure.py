"""Consumer-visible leases, disk identity, busy-worker and supervisor behavior."""

import asyncio
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from types import SimpleNamespace
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, Mock

import pytest
from redis import Redis
from redis.asyncio import Redis as AsyncRedis
from redis.exceptions import ConnectionError

from app.core.config import Settings, settings
from app.services.sandbox import (
    affinity,
    worker_heartbeat,
    worker_registry,
    worker_supervisor,
)
from app.services.sandbox.worker_registry import SandboxWorkerRegistry, WorkerPresence


@pytest.fixture
def local_disk(tmp_path, monkeypatch):
    monkeypatch.setattr(
        settings, "SANDBOX_WORKSPACE_ROOT", str(tmp_path / "disk" / "jobs")
    )
    monkeypatch.setattr(settings, "SANDBOX_CHECKPOINT_ROOT", "")
    monkeypatch.setattr(settings, "SANDBOX_WORKER_ID", "")
    monkeypatch.setattr(settings, "SANDBOX_WORKER_INSTANCE_ID", "")
    monkeypatch.setattr(settings, "SANDBOX_NODE_ID", "node-a")
    return tmp_path / "disk"


@pytest.fixture
def redis_server():
    external_url = os.environ.get("SANDBOX_TEST_REDIS_URL")
    if external_url:
        client = Redis.from_url(external_url, decode_responses=True)
        try:
            client.ping()
            client.flushdb()
        except ConnectionError as exc:
            client.close()
            pytest.fail(f"test Docker Redis is unavailable: {exc}")
        try:
            yield client, external_url
        finally:
            client.close()
        return

    binary = shutil.which("redis-server")
    if not binary:
        pytest.skip(
            "real Redis is required; set SANDBOX_TEST_REDIS_URL to an isolated Docker Redis"
        )
    socket_directory = TemporaryDirectory(prefix="sandbox-redis-", dir="/tmp")
    socket_path = f"{socket_directory.name}/redis.sock"
    process = subprocess.Popen(
        [
            binary,
            "--port",
            "0",
            "--unixsocket",
            socket_path,
            "--save",
            "",
            "--appendonly",
            "no",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    client = Redis(unix_socket_path=socket_path, decode_responses=True)
    deadline = time.monotonic() + 5
    try:
        while True:
            try:
                client.ping()
                break
            except ConnectionError:
                if process.poll() is not None or time.monotonic() >= deadline:
                    pytest.fail("test Redis did not start")
                time.sleep(0.02)
        yield client, socket_path
    finally:
        client.close()
        process.terminate()
        process.wait(timeout=5)
        socket_directory.cleanup()


@pytest.fixture
def registry_client(redis_server, monkeypatch):
    client, socket_path = redis_server
    async_client = (
        AsyncRedis.from_url(socket_path, decode_responses=True)
        if "://" in socket_path
        else AsyncRedis(unix_socket_path=socket_path, decode_responses=True)
    )
    monkeypatch.setattr(
        worker_registry, "get_redis", AsyncMock(return_value=async_client)
    )
    monkeypatch.setattr(worker_heartbeat, "heartbeat_redis", lambda: client)
    monkeypatch.setattr(worker_supervisor, "heartbeat_redis", lambda: client)
    return client, async_client, SandboxWorkerRegistry()


def test_disk_identity_survives_hostname_and_instance_changes(local_disk, monkeypatch):
    first = (affinity.sandbox_worker_id(), affinity.sandbox_storage_id())
    monkeypatch.setattr(affinity.socket, "gethostname", lambda: "replacement-pod")
    monkeypatch.setattr(settings, "SANDBOX_WORKER_INSTANCE_ID", "new-instance")
    assert (affinity.sandbox_worker_id(), affinity.sandbox_storage_id()) == first
    assert affinity.sandbox_instance_id() == "new-instance"
    monkeypatch.setattr(
        settings, "SANDBOX_WORKSPACE_ROOT", str(local_disk.parent / "other" / "jobs")
    )
    assert affinity.sandbox_storage_id() != first[1]
    assert affinity.sandbox_worker_id() != first[0]


def test_explicit_worker_identity_cannot_replace_retained_identity(
    local_disk, monkeypatch
):
    original = affinity.sandbox_worker_id()
    monkeypatch.setattr(settings, "SANDBOX_WORKER_ID", original)
    assert affinity.sandbox_worker_id() == original
    monkeypatch.setattr(settings, "SANDBOX_WORKER_ID", "different-worker")
    with pytest.raises(ValueError, match="retained sandbox disk identity"):
        affinity.sandbox_worker_id()


@pytest.mark.asyncio
async def test_live_owner_compare_expiry_and_retained_placement(registry_client):
    client, async_client, registry = registry_client
    first = WorkerPresence(
        worker_id="disk-a", instance_id="one", node_id="node-a", storage_id="storage-a"
    )
    replacement = first.model_copy(update={"instance_id": "two"})
    try:
        assert registry.refresh(client, first, 20)
        assert not registry.refresh(client, replacement, 20)
        assert not registry.refresh(
            client, first.model_copy(update={"storage_id": "other"}), 20
        )
        assert not registry.refresh(
            client, first.model_copy(update={"node_id": "other"}), 20
        )
        assert await registry.get("disk-a") == first
        assert await registry.list_ready() == [first]
        client.pexpire(registry.lease_key("disk-a"), 1)
        await asyncio.sleep(0.02)
        assert await registry.get("disk-a") is None
        assert await registry.list_ready() == []
        assert await registry.get_placement("disk-a") == first
        assert registry.refresh(client, replacement, 20)
        assert not registry.remove(client, first)
        assert await registry.get("disk-a") == replacement
        assert registry.remove(client, replacement)
        assert await registry.get("disk-a") is None
        assert await registry.get_placement("disk-a") == replacement
    finally:
        await async_client.aclose()


@pytest.mark.asyncio
async def test_unready_workers_excluded_and_redis_outage_propagates(
    registry_client, monkeypatch
):
    client, async_client, registry = registry_client
    presence = WorkerPresence(
        worker_id="a", instance_id="one", node_id="n", storage_id="s", ready=False
    )
    try:
        assert registry.refresh(client, presence, 20)
        assert await registry.get("a") == presence
        assert await registry.list_ready() == []
        failed = AsyncMock()
        failed.get.side_effect = ConnectionError("offline")
        failed.hkeys.side_effect = ConnectionError("offline")
        monkeypatch.setattr(
            worker_registry, "get_redis", AsyncMock(return_value=failed)
        )
        with pytest.raises(ConnectionError):
            await registry.get("a")
        with pytest.raises(ConnectionError):
            await registry.list_ready()
    finally:
        await async_client.aclose()


def test_busy_solo_worker_renews_lease_independently(
    local_disk, redis_server, monkeypatch
):
    client, _ = redis_server
    monkeypatch.setattr(settings, "SANDBOX_WORKER_HEARTBEAT_SECONDS", 0.03)
    monkeypatch.setattr(settings, "SANDBOX_WORKER_HEARTBEAT_TTL_SECONDS", 1)
    conflict = Mock()
    presence = worker_heartbeat.worker_presence()
    heartbeat = worker_heartbeat.SandboxWorkerHeartbeat(
        presence, redis=client, on_conflict=conflict
    )
    heartbeat.start()
    try:
        # The main/solo task thread is busy longer than the complete lease TTL.
        time.sleep(1.1)
        payload = client.get(
            worker_registry.sandbox_worker_registry.lease_key(presence.worker_id)
        )
        assert (
            WorkerPresence.model_validate_json(payload).instance_id
            == presence.instance_id
        )
        conflict.assert_not_called()
    finally:
        heartbeat.stop()
    assert (
        client.get(
            worker_registry.sandbox_worker_registry.lease_key(presence.worker_id)
        )
        is None
    )


def test_only_sandbox_consumers_advertise_writable_disk(
    local_disk, redis_server, monkeypatch
):
    client, _ = redis_server
    monkeypatch.setattr(worker_heartbeat, "heartbeat_redis", lambda: client)
    monkeypatch.setattr(worker_heartbeat, "_heartbeat", None)
    worker_heartbeat.start_worker_heartbeat(
        SimpleNamespace(
            task_consumer=SimpleNamespace(queues=[SimpleNamespace(name="agent")])
        )
    )
    assert worker_heartbeat._heartbeat is None
    sender = SimpleNamespace(
        task_consumer=SimpleNamespace(queues=[SimpleNamespace(name="sandbox")])
    )
    worker_heartbeat.start_worker_heartbeat(sender)
    try:
        presence = worker_heartbeat._heartbeat.presence
        assert presence.pid == os.getpid()
        assert (local_disk / "jobs").is_dir()
        assert (local_disk / "checkpoints").is_dir()
        assert client.get(
            worker_registry.sandbox_worker_registry.lease_key(presence.worker_id)
        )
    finally:
        worker_heartbeat.stop_worker_heartbeat()
    assert (
        client.get(
            worker_registry.sandbox_worker_registry.lease_key(presence.worker_id)
        )
        is None
    )


def test_disk_failure_does_not_advertise_ready(local_disk, redis_server, monkeypatch):
    client, _ = redis_server
    monkeypatch.setattr(worker_heartbeat, "_heartbeat", None)
    monkeypatch.setattr(
        worker_heartbeat, "worker_presence", Mock(side_effect=OSError("read-only disk"))
    )
    kill = Mock()
    monkeypatch.setattr(
        worker_heartbeat, "os", SimpleNamespace(kill=kill, getpid=os.getpid)
    )
    sender = SimpleNamespace(
        task_consumer=SimpleNamespace(queues=[SimpleNamespace(name="sandbox")])
    )
    worker_heartbeat.start_worker_heartbeat(sender)
    assert worker_heartbeat._heartbeat is None
    assert client.hlen(worker_registry.sandbox_worker_registry.PLACEMENTS_KEY) == 0
    kill.assert_called_once_with(os.getpid(), signal.SIGTERM)


def test_supervisor_recreates_child_on_retained_disk_and_retires_old_lease(
    local_disk, registry_client, monkeypatch
):
    client, _, registry = registry_client
    monkeypatch.setattr(settings, "SANDBOX_SUPERVISOR_MAX_RESTARTS", 1)
    monkeypatch.setattr(settings, "SANDBOX_SUPERVISOR_RESTART_SECONDS", 0)
    instances = iter(["child-one", "child-two"])
    monkeypatch.setattr(worker_supervisor, "uuid4", lambda: next(instances))
    presence = worker_heartbeat.worker_presence().model_copy(
        update={"instance_id": "child-one"}
    )
    assert registry.refresh(client, presence, 20)
    code = (
        "import os,pathlib,sys; p=pathlib.Path(sys.argv[1]); "
        "p.mkdir(parents=True,exist_ok=True); log=p/'children'; "
        "old=log.read_text() if log.exists() else ''; "
        "log.write_text(old+os.environ['SANDBOX_WORKER_INSTANCE_ID']+'\\n'); "
        "data=p/'retained'; "
        "assert not old or data.read_text()=='preserved'; "
        "data.write_text('preserved'); sys.exit(9 if not old else 0)"
    )
    assert (
        worker_supervisor.supervise_sandbox_worker(
            [sys.executable, "-c", code, str(local_disk)], cwd=str(local_disk.parent)
        )
        == 1
    )
    assert (local_disk / "children").read_text().splitlines() == [
        "child-one",
        "child-two",
    ]
    assert client.get(registry.lease_key(presence.worker_id)) is None
    assert (local_disk / "retained").read_text() == "preserved"


def test_supervisor_forwards_shutdown_and_does_not_restart(
    local_disk, redis_server, monkeypatch
):
    client, _ = redis_server
    monkeypatch.setattr(worker_supervisor, "heartbeat_redis", lambda: client)
    handlers = {}
    monkeypatch.setattr(
        worker_supervisor.signal,
        "signal",
        lambda sig, handler: handlers.setdefault(sig, handler),
    )
    marker = local_disk.parent / "child-started"
    code = "import pathlib,time,sys; pathlib.Path(sys.argv[1]).write_text('ready'); time.sleep(30)"

    def shutdown():
        deadline = time.monotonic() + 5
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        handlers[signal.SIGTERM](signal.SIGTERM, None)

    thread = threading.Thread(target=shutdown, daemon=True)
    thread.start()
    assert (
        worker_supervisor.supervise_sandbox_worker(
            [sys.executable, "-c", code, str(marker)], cwd=str(local_disk.parent)
        )
        == 0
    )
    thread.join(timeout=5)
    assert marker.read_text() == "ready"


def test_duplicate_heartbeat_start_does_not_register_again(monkeypatch):
    existing = Mock()
    monkeypatch.setattr(worker_heartbeat, "_heartbeat", existing)
    presence = Mock()
    monkeypatch.setattr(worker_heartbeat, "worker_presence", presence)
    sender = SimpleNamespace(
        task_consumer=SimpleNamespace(
            queues=[SimpleNamespace(name="sandbox")],
        )
    )

    worker_heartbeat.start_worker_heartbeat(sender)

    assert worker_heartbeat._heartbeat is existing
    presence.assert_not_called()


def test_stop_heartbeat_is_safe_without_a_registered_consumer(monkeypatch):
    monkeypatch.setattr(worker_heartbeat, "_heartbeat", None)

    worker_heartbeat.stop_worker_heartbeat()

    assert worker_heartbeat._heartbeat is None


def test_supervisor_exits_if_shutdown_arrives_before_child_start(monkeypatch):
    delivered = False

    def install_handler(sig, handler):
        nonlocal delivered
        if sig == signal.SIGTERM and callable(handler) and not delivered:
            delivered = True
            handler(sig, None)
        return signal.SIG_DFL

    monkeypatch.setattr(worker_supervisor.signal, "signal", install_handler)
    spawn = Mock()
    monkeypatch.setattr(worker_supervisor.subprocess, "Popen", spawn)

    assert worker_supervisor._supervise([], cwd=".") == 0
    spawn.assert_not_called()


def test_supervisor_stops_a_child_created_after_shutdown(local_disk, monkeypatch):
    handlers = {}

    def install_handler(sig, handler):
        if callable(handler):
            handlers[sig] = handler
        return signal.SIG_DFL

    monkeypatch.setattr(worker_supervisor.signal, "signal", install_handler)
    killpg = Mock(side_effect=ProcessLookupError)
    monkeypatch.setattr(worker_supervisor.os, "killpg", killpg)
    presence = WorkerPresence(
        worker_id="disk-a",
        instance_id="instance-a",
        node_id="node-a",
        storage_id="storage-a",
    )
    monkeypatch.setattr(worker_supervisor, "worker_presence", lambda: presence)
    redis = Mock()
    monkeypatch.setattr(worker_supervisor, "heartbeat_redis", lambda: redis)
    monkeypatch.setattr(worker_supervisor.sandbox_worker_registry, "remove", Mock())
    child = SimpleNamespace(
        pid=1234, poll=Mock(return_value=0), wait=Mock(return_value=0)
    )

    def spawn(*args, **kwargs):
        handlers[signal.SIGTERM](signal.SIGTERM, None)
        return child

    monkeypatch.setattr(worker_supervisor.subprocess, "Popen", spawn)

    assert worker_supervisor._supervise(["sandbox-worker"], cwd=str(local_disk)) == 0
    assert killpg.call_count == 2
    child.wait.assert_called_once_with()
    redis.close.assert_called_once_with()


def test_supervisor_shutdown_during_restart_backoff_returns_cleanly(
    local_disk, monkeypatch
):
    class StopDuringBackoff:
        def is_set(self):
            return False

        def wait(self, timeout):
            return True

        def set(self):
            return None

    monkeypatch.setattr(worker_supervisor.threading, "Event", StopDuringBackoff)
    monkeypatch.setattr(settings, "SANDBOX_SUPERVISOR_MAX_RESTARTS", 1)
    monkeypatch.setattr(settings, "SANDBOX_SUPERVISOR_RESTART_SECONDS", 0)
    monkeypatch.setattr(
        worker_supervisor.signal, "signal", lambda sig, handler: signal.SIG_DFL
    )
    killpg = Mock(side_effect=ProcessLookupError)
    monkeypatch.setattr(worker_supervisor.os, "killpg", killpg)
    presence = WorkerPresence(
        worker_id="disk-a",
        instance_id="instance-a",
        node_id="node-a",
        storage_id="storage-a",
    )
    monkeypatch.setattr(worker_supervisor, "worker_presence", lambda: presence)
    redis = Mock()
    monkeypatch.setattr(worker_supervisor, "heartbeat_redis", lambda: redis)
    monkeypatch.setattr(worker_supervisor.sandbox_worker_registry, "remove", Mock())
    child = SimpleNamespace(
        pid=1234, poll=Mock(return_value=1), wait=Mock(return_value=1)
    )
    monkeypatch.setattr(worker_supervisor.subprocess, "Popen", Mock(return_value=child))

    assert worker_supervisor._supervise(["sandbox-worker"], cwd=str(local_disk)) == 0
    child.wait.assert_called_once_with()
    assert killpg.call_count == 1


@pytest.mark.parametrize(
    "overrides",
    [
        {"SANDBOX_WORKER_HEARTBEAT_SECONDS": 0},
        {
            "SANDBOX_WORKER_HEARTBEAT_SECONDS": 20,
            "SANDBOX_WORKER_HEARTBEAT_TTL_SECONDS": 20,
        },
        {"SANDBOX_WORKER_RECOVERY_SECONDS": -1},
        {"SANDBOX_RECOVERY_POLL_SECONDS": 0},
        {"SANDBOX_SESSION_MAX_RESETS": -1},
        {"SANDBOX_SUPERVISOR_RESTART_SECONDS": -1},
        {"SANDBOX_SUPERVISOR_MAX_RESTARTS": -1},
    ],
)
def test_recovery_settings_reject_unbounded_or_invalid_ranges(overrides):
    with pytest.raises(ValueError):
        Settings(_env_file=None, **overrides)


def test_invalid_retained_identity_and_explicit_identity_fail_closed(
    local_disk, monkeypatch
):
    local_disk.mkdir(parents=True)
    identity_path = local_disk / ".worker-identity.json"
    identity_path.write_text('{"worker_id":"disk-a"}', encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid sandbox disk identity"):
        affinity.sandbox_worker_id()

    identity_path.unlink()
    monkeypatch.setattr(settings, "SANDBOX_WORKER_ID", " ")
    with pytest.raises(ValueError, match="SANDBOX_WORKER_ID"):
        affinity.sandbox_worker_id()
    assert not identity_path.exists()


def test_ready_registration_rejects_a_second_instance_for_the_same_disk(
    local_disk, redis_server
):
    client, _ = redis_server
    owner = worker_heartbeat.worker_presence()
    assert worker_registry.sandbox_worker_registry.refresh(client, owner, 20)
    conflict = Mock()
    duplicate = owner.model_copy(update={"instance_id": "different-instance"})
    heartbeat = worker_heartbeat.SandboxWorkerHeartbeat(
        duplicate,
        redis=client,
        on_conflict=conflict,
    )

    heartbeat.start()

    conflict.assert_called_once_with()
    assert not heartbeat._thread.is_alive()
    retained = WorkerPresence.model_validate_json(
        client.get(worker_registry.sandbox_worker_registry.lease_key(owner.worker_id))
    )
    assert retained.instance_id == owner.instance_id


def test_heartbeat_thread_exits_if_its_disk_lease_is_replaced(local_disk, monkeypatch):
    monkeypatch.setattr(settings, "SANDBOX_WORKER_HEARTBEAT_SECONDS", 0.01)
    refresh = Mock(side_effect=[True, False])
    monkeypatch.setattr(worker_heartbeat.sandbox_worker_registry, "refresh", refresh)
    monkeypatch.setattr(worker_heartbeat.sandbox_worker_registry, "remove", Mock())
    conflict = threading.Event()
    presence = WorkerPresence(
        worker_id="disk-a",
        instance_id="instance-a",
        node_id="node-a",
        storage_id="storage-a",
    )
    heartbeat = worker_heartbeat.SandboxWorkerHeartbeat(
        presence,
        redis=Mock(),
        on_conflict=conflict.set,
    )

    heartbeat.start()

    assert conflict.wait(1)
    heartbeat.stop()
    assert refresh.call_count == 2
    assert not heartbeat._thread.is_alive()
