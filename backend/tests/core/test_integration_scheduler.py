"""Exercise persisted admin switches through Beat ticks and a real memory broker."""

import asyncio
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from celery import Celery, current_app
from tortoise.context import TortoiseContext

from app.core import integration_scheduler as module
from app.models.feishu_knowledge import FeishuKnowledgeSource
from app.models.integration import Integration
from app.models.knowledge_base import KnowledgeBase
from app.models.user import Team


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    database_url = f"sqlite://{tmp_path / 'schedule.sqlite3'}"
    runner = asyncio.Runner()

    async def initialize():
        async with TortoiseContext() as context:
            await context.init(db_url=database_url, modules={"models": ["app.models"]})
            await context.generate_schemas()

    runner.run(initialize())
    monkeypatch.setattr(module.settings, "DATABASE_URL", database_url)
    now = datetime(2026, 10, 22, tzinfo=timezone.utc)
    clock = SimpleNamespace(seconds=0.0)
    monkeypatch.setattr(module, "monotonic", lambda: clock.seconds)
    previous_app = current_app._get_current_object()
    app = Celery(
        "integration-scheduler-test",
        broker="memory://",
        backend="cache+memory://",
    )
    app.conf.update(
        timezone="UTC",
        enable_utc=True,
        beat_schedule={
            "maintenance": {
                "task": "test.maintenance",
                "schedule": 1.0,
                "options": {"queue": f"maintenance-{tmp_path.name}"},
            }
        },
    )
    app.now = lambda: now + timedelta(seconds=clock.seconds)
    scheduler = module.IntegrationScheduler(
        app=app, schedule_filename=str(tmp_path / "beat")
    )

    def run(coroutine):
        async def isolated():
            async with TortoiseContext() as context:
                await context.init(
                    db_url=database_url, modules={"models": ["app.models"]}
                )
                return await coroutine

        return runner.run(isolated())

    @contextmanager
    def messages():
        with app.connection_for_read() as connection:
            channel = connection.channel()
            queues = [
                connection.SimpleQueue(queue, channel=channel)
                for queue in (
                    "agent",
                    "knowledge",
                    "default",
                    f"maintenance-{tmp_path.name}",
                )
            ]
            for queue in queues:
                queue.clear()
            try:
                yield queues
            finally:
                for queue in queues:
                    queue.clear()
                    queue.close()
                channel.close()

    state = SimpleNamespace(
        app=app, scheduler=scheduler, clock=clock, run=run, messages=messages
    )
    yield state
    state.scheduler.close()
    runner.close()
    app.close()
    previous_app.set_current()


def advance(runtime, seconds):
    runtime.clock.seconds += seconds
    # Celery sends at most one due entry per tick.
    for _ in range(len(runtime.scheduler.schedule) + 2):
        runtime.scheduler.tick()


def drain(queues):
    tasks = []
    for queue in queues:
        while True:
            try:
                message = queue.get(block=False)
            except queue.Empty:
                break
            tasks.append(message.headers["task"])
            message.ack()
    return tasks


async def configure(provider, capabilities, *, enabled=True):
    integration, _ = await Integration.get_or_create(
        name=provider, defaults={"provider_type": provider, "display_name": provider}
    )
    integration.is_enabled = enabled
    integration.enabled_capabilities = capabilities
    await integration.save()


def test_disabled_integrations_publish_no_ticks_but_maintenance_continues(runtime):
    runtime.run(configure("wechat", []))
    runtime.run(configure("feishu", ["agent_chat"], enabled=False))
    with runtime.messages() as queues:
        runtime.scheduler.tick()
        advance(runtime, 65)
        tasks = drain(queues)
    assert tasks == ["test.maintenance"]
    assert set(runtime.scheduler.schedule) == {"maintenance"}


def test_wechat_capability_changes_remove_due_heap_entries_and_resume(runtime):
    runtime.run(configure("wechat", ["agent_chat"]))
    with runtime.messages() as queues:
        runtime.scheduler.tick()
        advance(runtime, 4)
        assert sorted(drain(queues)) == sorted(
            [
                "app.tasks.wechat_poll.dispatch_bindings_task",
                "app.tasks.wechat_agent.recover_bindings_task",
                "test.maintenance",
            ]
        )

        runtime.run(configure("wechat", ["knowledge_collection"]))
        advance(runtime, 3)
        assert sorted(drain(queues)) == sorted(
            ["app.tasks.wechat_poll.dispatch_bindings_task", "test.maintenance"]
        )
        advance(runtime, 61)
        assert sorted(drain(queues)) == sorted(
            [
                "app.tasks.wechat_poll.dispatch_bindings_task",
                "app.tasks.wechat_knowledge.recover_receipts_task",
                "test.maintenance",
            ]
        )

        runtime.run(configure("wechat", []))
        advance(runtime, 65)
        assert drain(queues) == ["test.maintenance"]
        runtime.run(configure("wechat", ["agent_chat"]))
        advance(runtime, 2)
        assert drain(queues) == ["test.maintenance"]
        advance(runtime, 4)
        assert sorted(drain(queues)) == sorted(
            [
                "app.tasks.wechat_poll.dispatch_bindings_task",
                "app.tasks.wechat_agent.recover_bindings_task",
                "test.maintenance",
            ]
        )


def test_feishu_login_directory_and_notification_do_not_enable_agent_recovery(runtime):
    runtime.run(configure("feishu", ["user_login", "directory_sync", "notification"]))
    with runtime.messages() as queues:
        runtime.scheduler.tick()
        advance(runtime, 65)
        assert drain(queues) == ["test.maintenance"]
        runtime.run(configure("feishu", ["agent_chat"]))
        advance(runtime, 2)
        drain(queues)
        advance(runtime, 11)
        assert sorted(drain(queues)) == sorted(
            ["app.tasks.feishu_agent.recover_pending_task", "test.maintenance"]
        )
        runtime.run(configure("feishu", []))
        advance(runtime, 11)
        assert drain(queues) == ["test.maintenance"]


def test_feishu_wiki_dispatch_follows_source_not_unrelated_capabilities(runtime):
    async def source():
        team = await Team.create(name="Knowledge team")
        kb = await KnowledgeBase.create(name="Knowledge", team=team)
        return await FeishuKnowledgeSource.create(
            knowledge_base=kb, space_id="space", name="Wiki"
        )

    async def enable_source(identifier, enabled):
        await FeishuKnowledgeSource.filter(id=identifier).update(is_enabled=enabled)

    runtime.run(configure("feishu", []))
    identifier = runtime.run(source()).id
    with runtime.messages() as queues:
        runtime.scheduler.tick()
        advance(runtime, 61)
        assert sorted(drain(queues)) == sorted(
            ["app.tasks.feishu_knowledge.dispatch_due_sources_task", "test.maintenance"]
        )
        runtime.run(enable_source(identifier, False))
        advance(runtime, 61)
        assert drain(queues) == ["test.maintenance"]
        runtime.run(enable_source(identifier, True))
        runtime.run(configure("feishu", [], enabled=False))
        advance(runtime, 61)
        assert drain(queues) == ["test.maintenance"]
        from app.services.feishu_knowledge import dispatch_due_sources

        assert runtime.run(dispatch_due_sources()) == {"queued": 0, "failed": 0}


def test_database_failure_removes_stale_enabled_entries_without_stopping_maintenance(
    runtime, monkeypatch
):
    runtime.run(configure("wechat", ["agent_chat"]))
    with runtime.messages() as queues:
        runtime.scheduler.tick()
        advance(runtime, 4)
        drain(queues)
        original = runtime.scheduler._enabled_entries

        async def unavailable():
            raise OSError("database unavailable")

        monkeypatch.setattr(runtime.scheduler, "_enabled_entries", unavailable)
        advance(runtime, 5)
        assert drain(queues) == ["test.maintenance"]
        monkeypatch.setattr(runtime.scheduler, "_enabled_entries", original)
        advance(runtime, 2)
        drain(queues)
        advance(runtime, 4)
        assert sorted(drain(queues)) == sorted(
            [
                "app.tasks.wechat_poll.dispatch_bindings_task",
                "app.tasks.wechat_agent.recover_bindings_task",
                "test.maintenance",
            ]
        )


def test_restart_drops_persisted_integration_entries_until_current_state_is_loaded(
    runtime, tmp_path
):
    runtime.run(configure("wechat", ["agent_chat"]))
    runtime.scheduler.tick()
    runtime.scheduler.close()
    runtime.run(configure("wechat", []))
    runtime.scheduler = module.IntegrationScheduler(
        app=runtime.app, schedule_filename=str(tmp_path / "beat")
    )
    with runtime.messages() as queues:
        advance(runtime, 65)
        assert drain(queues) == ["test.maintenance"]


def test_sleep_never_crosses_the_next_feature_refresh(runtime):
    runtime.scheduler.tick()
    runtime.clock.seconds = 1.5
    runtime.scheduler.tick()  # Publish due maintenance first.
    assert runtime.scheduler.tick() <= 0.5
