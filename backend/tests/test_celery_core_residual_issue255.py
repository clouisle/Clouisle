import asyncio
import importlib.util
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest


class _Signal:
    def connect(self, function):
        return function


class _Conf(SimpleNamespace):
    def update(self, **kwargs):
        self.__dict__.update(kwargs)


def _load_celery_module(monkeypatch, *, password=""):
    celery_app = SimpleNamespace(conf=_Conf(), send_task=Mock())
    celery_module = ModuleType("celery")
    celery_module.Celery = Mock(return_value=celery_app)
    schedules_module = ModuleType("celery.schedules")
    schedules_module.crontab = Mock(side_effect=lambda **kwargs: kwargs)
    signals_module = ModuleType("celery.signals")
    signals_module.worker_process_init = _Signal()
    signals_module.worker_process_shutdown = _Signal()
    settings = SimpleNamespace(
        REDIS_PASSWORD=password,
        REDIS_HOST="redis.test",
        REDIS_PORT=6380,
        TIMEZONE="UTC",
        CELERY_VISIBILITY_TIMEOUT_SECONDS=123,
        DATABASE_URL="postgres://configured",
        POSTGRES_USER="user",
        POSTGRES_PASSWORD="secret",
        POSTGRES_SERVER="db",
        POSTGRES_PORT=5432,
        POSTGRES_DB="clouisle",
        KB_PROCESSING_RECOVERY_AFTER_SECONDS=300,
    )
    config_module = ModuleType("app.core.config")
    config_module.settings = settings

    for name, module in {
        "celery": celery_module,
        "celery.schedules": schedules_module,
        "celery.signals": signals_module,
        "app.core.config": config_module,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)

    module_name = f"test_celery_core_{password or 'without_password'}"
    path = __file__.replace(
        "tests/test_celery_core_residual_issue255.py", "app/core/celery.py"
    )
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, celery_app


def test_configures_celery_with_and_without_redis_password(monkeypatch):
    without_password, app = _load_celery_module(monkeypatch)
    assert without_password.REDIS_URL == "redis://redis.test:6380"
    assert app.conf.visibility_timeout == 123
    assert app.conf.task_routes["app.tasks.workflow.*"] == {"queue": "workflow"}
    assert app.conf.beat_schedule["cleanup-expired-sandbox-sessions"]["options"] == {
        "queue": "sandbox"
    }

    with_password, _ = _load_celery_module(monkeypatch, password="password")
    assert with_password.REDIS_URL == "redis://:password@redis.test:6380"


@pytest.mark.parametrize("redis_result", [False, RuntimeError("redis unavailable")])
def test_init_tortoise_skips_recovery_without_lock(monkeypatch, redis_result):
    module, app = _load_celery_module(monkeypatch)
    tortoise = SimpleNamespace(init=AsyncMock())
    get_redis = AsyncMock()
    if isinstance(redis_result, Exception):
        get_redis.side_effect = redis_result
    else:
        get_redis.return_value = SimpleNamespace(
            set=AsyncMock(return_value=redis_result)
        )
    document = SimpleNamespace(filter=Mock())
    register_tools = Mock()

    _install_worker_boundaries(
        monkeypatch, tortoise, get_redis, document, register_tools
    )
    loop = asyncio.new_event_loop()
    monkeypatch.setattr(asyncio, "new_event_loop", lambda: loop)
    try:
        module.init_tortoise()
    finally:
        loop.close()
        asyncio.set_event_loop(None)

    tortoise.init.assert_awaited_once()
    document.filter.assert_not_called()
    app.send_task.assert_not_called()
    register_tools.assert_called_once_with()


def test_init_tortoise_recovers_only_documents_with_valid_task_metadata(monkeypatch):
    module, app = _load_celery_module(monkeypatch)
    tortoise = SimpleNamespace(init=AsyncMock())
    redis = SimpleNamespace(set=AsyncMock(return_value=True))
    get_redis = AsyncMock(return_value=redis)
    invalid_missing = SimpleNamespace(metadata={}, save=AsyncMock(), id="missing")
    invalid_args = SimpleNamespace(
        metadata={"task_name": "tasks.bad", "task_args": "not-a-list"},
        save=AsyncMock(),
        id="bad-args",
    )
    valid = SimpleNamespace(
        metadata={"task_name": "tasks.process", "task_args": ["doc-1"]},
        save=AsyncMock(),
        id="doc-1",
    )
    query = SimpleNamespace(
        limit=AsyncMock(return_value=[invalid_missing, invalid_args, valid])
    )
    document = SimpleNamespace(filter=Mock(return_value=query))
    register_tools = Mock()

    _install_worker_boundaries(
        monkeypatch, tortoise, get_redis, document, register_tools
    )
    loop = asyncio.new_event_loop()
    monkeypatch.setattr(asyncio, "new_event_loop", lambda: loop)
    try:
        module.init_tortoise()
    finally:
        loop.close()
        asyncio.set_event_loop(None)

    redis.set.assert_awaited_once_with(
        "kb:processing-recovery:lock", "1", ex=300, nx=True
    )
    query.limit.assert_awaited_once_with(100)
    invalid_missing.save.assert_not_awaited()
    invalid_args.save.assert_not_awaited()
    valid.save.assert_awaited_once_with(update_fields=["metadata"])
    task_id = valid.metadata["task_id"]
    app.send_task.assert_called_once_with(
        "tasks.process", args=["doc-1"], task_id=task_id
    )


def _install_worker_boundaries(
    monkeypatch, tortoise, get_redis, document, register_tools
):
    modules = {
        "tortoise": SimpleNamespace(Tortoise=tortoise),
        "app.llm.tools.builtin": SimpleNamespace(
            register_all_builtin_tools=register_tools
        ),
        "app.core.redis": SimpleNamespace(get_redis=get_redis),
        "app.models.knowledge_base": SimpleNamespace(
            Document=document,
            DocumentStatus=SimpleNamespace(
                PROCESSING=SimpleNamespace(value="processing")
            ),
        ),
    }
    for name, boundary in modules.items():
        monkeypatch.setitem(sys.modules, name, boundary)


def test_close_tortoise_uses_stopped_and_running_loops(monkeypatch):
    module, _ = _load_celery_module(monkeypatch)
    close_connections = AsyncMock()
    monkeypatch.setitem(
        sys.modules,
        "tortoise",
        SimpleNamespace(Tortoise=SimpleNamespace(close_connections=close_connections)),
    )

    stopped_loop = Mock()
    stopped_loop.is_running.return_value = False
    monkeypatch.setattr(asyncio, "get_event_loop", lambda: stopped_loop)
    module.close_tortoise()
    coroutine = stopped_loop.run_until_complete.call_args.args[0]
    asyncio.run(coroutine)
    close_connections.assert_awaited_once()

    close_connections.reset_mock()
    running_loop = Mock()
    running_loop.is_running.return_value = True
    monkeypatch.setattr(asyncio, "get_event_loop", lambda: running_loop)
    module.close_tortoise()
    coroutine = running_loop.create_task.call_args.args[0]
    asyncio.run(coroutine)
    close_connections.assert_awaited_once()


def test_close_tortoise_ignores_event_loop_errors(monkeypatch):
    module, _ = _load_celery_module(monkeypatch)
    monkeypatch.setitem(
        sys.modules,
        "tortoise",
        SimpleNamespace(Tortoise=SimpleNamespace(close_connections=AsyncMock())),
    )
    monkeypatch.setattr(
        asyncio, "get_event_loop", Mock(side_effect=RuntimeError("no event loop"))
    )

    module.close_tortoise()
