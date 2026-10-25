"""Transport-independent intake after a Feishu event has been authenticated."""

import asyncio
import logging
from typing import Literal

from app.models.integration import Integration

logger = logging.getLogger(__name__)

FeishuConnectionMode = Literal["callback", "long_connection"]
CONNECTION_MODE_KEY = "agent_chat_connection_mode"


def get_connection_mode(integration: Integration) -> str:
    """Existing integrations keep callback delivery; unknown modes fail closed."""
    return str((integration.config or {}).get(CONNECTION_MODE_KEY, "callback"))


async def receive_message(event: dict, *, app_id: str) -> str | None:
    """Commit the receipt before queuing work or acknowledging the provider."""
    from app.services.feishu_agent_runtime import accept_message

    receipt_id = await accept_message({**event, "app_id": app_id})
    if receipt_id:
        try:
            await asyncio.to_thread(_enqueue_receipt, receipt_id)
        except Exception:
            # The receipt is durable. Beat discovers it even if publishing fails.
            logger.exception(
                "Feishu receipt %s is awaiting broker recovery", receipt_id
            )
    return receipt_id


def _enqueue_receipt(receipt_id: str) -> None:
    from app.core.celery import celery_app

    # shared_task resolves the current app per thread, including the receiver's
    # publisher thread where no FastAPI or worker startup initialized Celery.
    celery_app.set_current()
    from app.tasks.feishu_agent import process_message_task

    process_message_task.delay(receipt_id)
