"""Worker-owned Feishu SDK receiver; no public listener, service, or CLI."""

from __future__ import annotations

import asyncio
import logging
import json
import os
import signal
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from threading import Thread
from uuid import UUID

from tortoise import Tortoise

from app.core.config import settings
from app.core.redis import close_redis
from app.integrations.credentials import IntegrationSecretError, decrypt_secret
from app.services.feishu_agent_events import get_connection_mode, receive_message
from app.services.integration_config import get_builtin_integration
from app.services.integration_receiver_state import (
    RECEIVER_TTL_SECONDS,
    RECONCILE_SECONDS,
    REFRESH_SCRIPT,
    configured_receiver,
    receiver_fingerprint,
    receiver_key,
    receiver_redis,
)

logger = logging.getLogger(__name__)
EVENT_TIMEOUT_SECONDS = 3


class _SDKLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # SDK errors may contain endpoint URLs, payloads or provider details.
        record.msg = (
            "Feishu SDK transport error; connection recovery is managed automatically"
        )
        record.args = ()
        record.exc_info = None
        record.exc_text = None
        return True


@dataclass(frozen=True)
class ReceiverConfig:
    integration_id: UUID
    app_id: str
    encrypted_secret: str
    owner: str = ""


async def _load_config() -> ReceiverConfig:
    integration = await get_builtin_integration("feishu")
    if (
        not integration.is_enabled
        or "agent_chat" not in integration.enabled_capabilities
        or get_connection_mode(integration) != "long_connection"
    ):
        raise ValueError(
            "Enable Feishu Agent chat and save long connection mode before starting the receiver."
        )
    app_id = str(integration.config.get("app_id") or "").strip()
    encrypted_secret = integration.credentials.get("app_secret") or ""
    if not app_id or not encrypted_secret:
        raise ValueError(
            "Save the Feishu App ID and App Secret before starting the receiver."
        )
    return ReceiverConfig(integration.id, app_id, encrypted_secret)


async def accept_long_connection_event(data, config: ReceiverConfig) -> str | None:
    """Recheck saved state before accepting an SDK-authenticated event."""
    header = getattr(data, "header", None)
    if (
        getattr(header, "app_id", None) != config.app_id
        or getattr(header, "event_type", None) != "im.message.receive_v1"
        or not isinstance(getattr(data, "event", None), dict)
    ):
        return None
    integration = await get_builtin_integration("feishu")
    if config.owner:
        client = receiver_redis()
        try:
            value = await client.get(receiver_key(integration.id))
            if not value or json.loads(value).get("owner") != config.owner:
                raise RuntimeError("Receiver ownership expired")
        finally:
            await client.aclose()
    if (
        integration.id != config.integration_id
        or not integration.is_enabled
        or "agent_chat" not in integration.enabled_capabilities
        or get_connection_mode(integration) != "long_connection"
    ):
        return None
    if (
        integration.config.get("app_id") != config.app_id
        or integration.credentials.get("app_secret") != config.encrypted_secret
    ):
        raise RuntimeError("Receiver configuration advanced; redelivery is required")
    return await receive_message(data.event, app_id=config.app_id)


def build_event_handler(
    config: ReceiverConfig, database_loop: asyncio.AbstractEventLoop
):
    """Bridge the SDK's synchronous handler to the database event loop.

    The handler does not return until the receipt commits, so the SDK cannot
    acknowledge an event that exists only in process memory.
    """
    import lark_oapi as lark

    def on_message(data) -> None:
        future = asyncio.run_coroutine_threadsafe(
            accept_long_connection_event(data, config), database_loop
        )
        try:
            future.result(timeout=EVENT_TIMEOUT_SECONDS)
        except FutureTimeoutError:
            future.cancel()
            raise RuntimeError(
                "Feishu message intake timed out; redelivery is required"
            ) from None
        except Exception:
            # The SDK includes handler errors in its logs; never leak payloads,
            # credentials, or database connection details through that path.
            logger.error("Feishu message intake failed; redelivery is required")
            raise RuntimeError("Feishu message intake failed") from None

    return (
        lark.EventDispatcherHandler.builder("", "")
        .register_p2_customized_event("im.message.receive_v1", on_message)
        .build()
    )


async def _initialize() -> ReceiverConfig:
    await Tortoise.init(
        db_url=settings.DATABASE_URL,
        modules={"models": ["app.models"]},
        _enable_global_fallback=True,
    )
    return await _load_config()


async def _close_database() -> None:
    await Tortoise.close_connections()
    await close_redis()


async def _watch_lifecycle(
    config: ReceiverConfig, state: dict, parent_pid: int
) -> None:
    client = receiver_redis()
    try:
        while True:
            if os.getppid() != parent_pid:
                break
            integration = await asyncio.wait_for(
                get_builtin_integration("feishu"), timeout=3
            )
            if (
                os.getppid() != parent_pid
                or not configured_receiver(integration)
                or receiver_fingerprint(integration) != state["fingerprint"]
            ):
                break
            presence = json.dumps(
                {
                    "owner": config.owner,
                    "fingerprint": state["fingerprint"],
                    "state": state["state"],
                }
            )
            if not await client.eval(
                REFRESH_SCRIPT,
                1,
                receiver_key(integration.id),
                config.owner,
                presence,
                RECEIVER_TTL_SECONDS,
            ):
                break
            await asyncio.sleep(RECONCILE_SECONDS)
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.warning("Feishu receiver lost configuration or ownership")
    finally:
        await client.aclose()
    os.kill(os.getpid(), signal.SIGTERM)


def run_receiver() -> None:
    """Internal child entrypoint started and stopped by an Agent worker parent."""
    owner = os.environ.get("CLOUISLE_RECEIVER_OWNER")
    parent_pid = int(os.environ.get("CLOUISLE_RECEIVER_PARENT") or 0)
    fingerprint = os.environ.get("CLOUISLE_RECEIVER_FINGERPRINT")
    if not owner or not parent_pid or not fingerprint:
        raise ValueError(
            "Feishu reception is managed automatically by the Agent worker."
        )
    database_loop = asyncio.new_event_loop()
    database_thread = Thread(
        target=database_loop.run_forever, name="feishu-intake", daemon=True
    )
    database_thread.start()
    sdk_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(sdk_loop)
    client = None
    watcher = None
    state = {"state": "starting", "fingerprint": fingerprint}
    previous_sigterm = signal.getsignal(signal.SIGTERM)

    def stop_receiver(_signum, _frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, stop_receiver)
    try:
        loaded = asyncio.run_coroutine_threadsafe(_initialize(), database_loop).result(
            timeout=10
        )
        config = ReceiverConfig(
            loaded.integration_id, loaded.app_id, loaded.encrypted_secret, owner
        )
        watcher = asyncio.run_coroutine_threadsafe(
            _watch_lifecycle(config, state, parent_pid), database_loop
        )
        try:
            app_secret = decrypt_secret(config.encrypted_secret)
        except IntegrationSecretError:
            raise ValueError(
                "Feishu App Secret cannot be decrypted; save it again."
            ) from None
        if not app_secret:
            raise ValueError(
                "Save a nonempty Feishu App Secret before enabling Agent chat."
            )
        import lark_oapi as lark
        from lark_oapi.ws import client as sdk_client

        # SDK 1.x owns a synchronous module-level loop and has no public stop
        # API. Only this child process touches its loop and lifecycle methods.
        sdk_client.loop = sdk_loop

        class ManagedClient(lark.ws.Client):
            async def _connect(self):
                await super()._connect()
                if self._conn is not None:
                    state["state"] = "connected"

            async def _disconnect(self):
                state["state"] = "reconnecting"
                await super()._disconnect()

            async def _reconnect(self):
                state["state"] = "reconnecting"
                try:
                    await super()._reconnect()
                except Exception:
                    state["state"] = "error"
                    os.kill(os.getpid(), signal.SIGTERM)

        client = ManagedClient(
            config.app_id,
            app_secret,
            event_handler=build_event_handler(config, database_loop),
            log_level=lark.LogLevel.WARNING,
        )
        sdk_client.logger.addFilter(_SDKLogFilter())
        client.on_reconnecting = lambda: state.update(state="reconnecting")
        logger.info("Starting managed Feishu long connection")
        client.start()
    except KeyboardInterrupt:
        logger.info("Stopping managed Feishu long connection")
    except Exception:
        state["state"] = "error"
        logger.error("Managed Feishu receiver failed; worker will retry")
    finally:
        signal.signal(signal.SIGTERM, previous_sigterm)
        if watcher is not None:
            watcher.cancel()
        pending = asyncio.all_tasks(sdk_loop)
        for task in pending:
            task.cancel()
        if pending:
            sdk_loop.run_until_complete(
                asyncio.gather(*pending, return_exceptions=True)
            )
        if client is not None:
            sdk_loop.run_until_complete(
                asyncio.wait_for(client._disconnect(), timeout=2)
            )
        sdk_loop.close()
        asyncio.set_event_loop(None)
        try:
            asyncio.run_coroutine_threadsafe(_close_database(), database_loop).result(
                timeout=5
            )
        finally:
            database_loop.call_soon_threadsafe(database_loop.stop)
            database_thread.join(timeout=5)
            database_loop.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_receiver()
