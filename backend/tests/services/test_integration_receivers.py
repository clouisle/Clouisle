"""Worker-managed receiver ownership and lifecycle transitions."""

import json
import subprocess
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.services import integration_receivers as manager
from app.services import integration_receiver_state as state


def integration(**changes):
    values = dict(
        id=uuid4(),
        is_enabled=True,
        enabled_capabilities=["agent_chat"],
        config={"app_id": "cli_test", "agent_chat_connection_mode": "long_connection"},
        credentials={"app_secret": "encrypted"},
    )
    values.update(changes)
    return SimpleNamespace(**values)


class LeaseStore:
    def __init__(self):
        self.values = {}

    async def set(self, key, value, **kwargs):
        if kwargs.get("nx") and key in self.values:
            return False
        self.values[key] = value
        return True

    async def get(self, key):
        return self.values.get(key)

    async def eval(self, script, count, key, owner):
        if key not in self.values or json.loads(self.values[key])["owner"] != owner:
            return 0
        del self.values[key]
        return 1

    async def aclose(self):
        pass


class Child:
    def __init__(self, *, hangs=False):
        self.returncode = None
        self.terminated = False
        self.killed = False
        self.hangs = hangs

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True
        if not self.hangs:
            self.returncode = -15

    def kill(self):
        self.killed = True
        self.returncode = -9

    def wait(self, timeout):
        if self.returncode is None:
            raise subprocess.TimeoutExpired("receiver", timeout)
        return self.returncode


@pytest.fixture
def children(monkeypatch):
    spawned = []

    def spawn(*args, **kwargs):
        child = Child()
        spawned.append(child)
        return child

    monkeypatch.setattr(manager.subprocess, "Popen", spawn)
    return spawned


@pytest.mark.asyncio
async def test_two_workers_elect_one_receiver_and_disable_releases_for_reenable(
    children,
):
    first, second, leases = (
        manager.IntegrationReceiverManager(),
        manager.IntegrationReceiverManager(),
        LeaseStore(),
    )
    instance = integration(enabled_capabilities=[])
    await first.reconcile(instance, leases)
    assert children == []
    instance.enabled_capabilities = ["agent_chat"]
    await first.reconcile(instance, leases)
    await second.reconcile(instance, leases)
    assert first.child is not None and second.child is None
    assert len(children) == 1
    instance.enabled_capabilities = []
    await first.reconcile(instance, leases)
    assert first.child is None
    assert children[0].terminated
    assert state.receiver_key(instance.id) not in leases.values
    instance.enabled_capabilities = ["agent_chat"]
    await second.reconcile(instance, leases)
    assert second.child is not None
    await second._stop_child(leases)


@pytest.mark.asyncio
async def test_mode_and_credential_changes_replace_only_the_owned_child(children):
    owner, leases, instance = (
        manager.IntegrationReceiverManager(),
        LeaseStore(),
        integration(),
    )
    await owner.reconcile(instance, leases)
    original = owner.child
    instance.credentials = {"app_secret": "rotated"}
    await owner.reconcile(instance, leases)
    assert children[0].terminated
    assert owner.child.owner != original.owner
    instance.config["agent_chat_connection_mode"] = "callback"
    await owner.reconcile(instance, leases)
    assert children[1].terminated
    assert owner.child is None
    assert not leases.values


@pytest.mark.asyncio
async def test_crashed_child_recovers_after_backoff_and_shutdown_kills_hung_process(
    children, monkeypatch
):
    now = [100.0]
    monkeypatch.setattr(manager.time, "monotonic", lambda: now[0])
    owner, leases, instance = (
        manager.IntegrationReceiverManager(),
        LeaseStore(),
        integration(),
    )
    await owner.reconcile(instance, leases)
    children[0].returncode = 1
    await owner.reconcile(instance, leases)
    assert owner.child is None
    await owner.reconcile(instance, leases)
    assert len(children) == 1
    now[0] = 200.0
    await owner.reconcile(instance, leases)
    assert len(children) == 2
    children[1].hangs = True
    await owner._stop_child(leases)
    assert children[1].terminated and children[1].killed
    assert not leases.values


@pytest.mark.asyncio
async def test_lost_owner_stops_old_child_without_deleting_new_owner(children):
    owner, leases, instance = (
        manager.IntegrationReceiverManager(),
        LeaseStore(),
        integration(),
    )
    await owner.reconcile(instance, leases)
    key = owner.child.key
    new_presence = json.dumps({"owner": "replacement"})
    leases.values[key] = new_presence
    await owner.reconcile(instance, leases)
    assert children[0].terminated
    assert owner.child is None
    assert leases.values[key] == new_presence


@pytest.mark.asyncio
async def test_spawn_failure_releases_owned_lease(children, monkeypatch):
    def fail(*args, **kwargs):
        raise OSError("unavailable executable")

    monkeypatch.setattr(manager.subprocess, "Popen", fail)
    owner, leases = manager.IntegrationReceiverManager(), LeaseStore()
    with pytest.raises(OSError):
        await owner.reconcile(integration(), leases)
    assert not leases.values


@pytest.mark.asyncio
async def test_receiver_status_tracks_live_presence_and_stale_fingerprint(monkeypatch):
    leases, instance = LeaseStore(), integration()
    monkeypatch.setattr(state, "receiver_redis", lambda: leases)
    assert await state.receiver_status(instance) == {
        "state": "waiting",
        "managed": True,
    }
    leases.values[state.receiver_key(instance.id)] = json.dumps(
        {
            "owner": "worker",
            "fingerprint": state.receiver_fingerprint(instance),
            "state": "connected",
        }
    )
    assert (await state.receiver_status(instance))["state"] == "connected"
    instance.credentials = {"app_secret": "rotated"}
    assert (await state.receiver_status(instance))["state"] == "waiting"
    instance.enabled_capabilities = []
    assert await state.receiver_status(instance) == {
        "state": "disabled",
        "managed": False,
    }


@pytest.mark.asyncio
async def test_database_unavailable_at_startup_is_retried_and_recovers(monkeypatch):
    attempts = []
    owner = manager.IntegrationReceiverManager()
    leases = LeaseStore()

    class Context:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def init(self, **kwargs):
            attempts.append(True)
            if len(attempts) == 1:
                raise ConnectionError("database unavailable")

    async def reconcile(*args):
        owner._stop.set()

    monkeypatch.setattr(manager, "TortoiseContext", Context)
    monkeypatch.setattr(manager, "receiver_redis", lambda: leases)
    monkeypatch.setattr(manager, "RECONCILE_SECONDS", 0)
    monkeypatch.setattr(
        manager.Integration, "get_or_none", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(owner, "reconcile", reconcile)
    await owner._serve()
    assert len(attempts) == 2
