"""
Celery application configuration for Clouisle backend.
"""

import logging

from celery import Celery
from celery.schedules import crontab
from celery.signals import worker_process_init, worker_process_shutdown

from app.core.config import settings

logger = logging.getLogger(__name__)

# Redis URL for Celery broker and result backend
if settings.REDIS_PASSWORD:
    REDIS_URL = f"redis://:{settings.REDIS_PASSWORD}@{settings.REDIS_HOST}:{settings.REDIS_PORT}"
else:
    REDIS_URL = f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}"

# Create Celery app
celery_app = Celery(
    "clouisle",
    broker=f"{REDIS_URL}/0",
    backend=f"{REDIS_URL}/1",
    include=[
        "app.tasks.knowledge_base",
        "app.tasks.usage",
        "app.tasks.workflow",
        "app.tasks.audit_log",
        "app.tasks.notification",
        "app.tasks.api_key",
        "app.tasks.password_expiration",
        "app.tasks.session_memory",
        "app.tasks.sandbox",
    ],
)

# Celery configuration
celery_app.conf.update(
    # Task settings
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone=settings.TIMEZONE,
    enable_utc=True,
    # Task execution settings
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_track_started=True,
    # Result settings
    result_expires=3600 * 24,  # 24 hours
    # Worker settings
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=100,
    # Retry settings
    broker_connection_retry_on_startup=True,
    broker_transport_options={
        "visibility_timeout": settings.CELERY_VISIBILITY_TIMEOUT_SECONDS,
    },
    result_backend_transport_options={
        "visibility_timeout": settings.CELERY_VISIBILITY_TIMEOUT_SECONDS,
    },
    visibility_timeout=settings.CELERY_VISIBILITY_TIMEOUT_SECONDS,
)

# Optional: Configure task routes
celery_app.conf.task_routes = {
    "app.tasks.knowledge_base.*": {"queue": "default"},
    "app.tasks.usage.*": {"queue": "default"},
    "app.tasks.workflow.*": {"queue": "workflow"},
    "app.tasks.notification.*": {"queue": "default"},
    "app.tasks.audit_log.*": {"queue": "default"},
    "app.tasks.api_key.*": {"queue": "default"},
    "app.tasks.password_expiration.*": {"queue": "default"},
    "app.tasks.session_memory.*": {"queue": "default"},
    "app.tasks.sandbox.*": {"queue": "sandbox"},
    "tasks.cleanup_expired_sandbox_sessions": {"queue": "sandbox"},
    "tasks.archive_old_audit_logs": {"queue": "default"},
    "tasks.check_api_key_expiration": {"queue": "default"},
    "tasks.check_password_expiration": {"queue": "default"},
    "tasks.reset_daily_usage": {"queue": "default"},
    "tasks.reset_monthly_usage": {"queue": "default"},
    "send_notification_dingtalk": {"queue": "default"},
    "send_notification_email": {"queue": "default"},
}

# Beat schedule for periodic tasks
celery_app.conf.beat_schedule = {
    # Reset daily usage every day at 00:00
    "reset-daily-usage": {
        "task": "tasks.reset_daily_usage",
        "schedule": crontab(hour=0, minute=0),
    },
    # Reset monthly usage on the 1st of each month at 00:05
    "reset-monthly-usage": {
        "task": "tasks.reset_monthly_usage",
        "schedule": crontab(hour=0, minute=5, day_of_month=1),
    },
    # Check API key expiration every day at 09:00
    "check-api-key-expiration": {
        "task": "tasks.check_api_key_expiration",
        "schedule": crontab(hour=9, minute=0),
    },
    # Check password expiration every day at 08:00
    "check-password-expiration": {
        "task": "tasks.check_password_expiration",
        "schedule": crontab(hour=8, minute=0),
    },
    "cleanup-expired-sandbox-sessions": {
        "task": "tasks.cleanup_expired_sandbox_sessions",
        "schedule": crontab(minute="*/15"),
        "options": {"queue": "sandbox"},
    },
}


# Initialize Tortoise ORM when worker process starts
@worker_process_init.connect
def init_tortoise(**kwargs):
    """Initialize Tortoise ORM for each worker process."""
    import asyncio
    from tortoise import Tortoise
    from app.llm.tools.builtin import register_all_builtin_tools

    async def _init():
        await Tortoise.init(
            db_url=settings.DATABASE_URL
            or f"postgres://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}@{settings.POSTGRES_SERVER}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}",
            modules={"models": ["app.models"]},
            _enable_global_fallback=True,  # Enable global state for compatibility
        )

    async def _recover_processing_documents():
        from datetime import datetime, timedelta, timezone
        from uuid import uuid4

        from app.core.redis import get_redis
        from app.models.knowledge_base import Document, DocumentStatus

        try:
            redis = await get_redis()
            lock_acquired = await redis.set(
                "kb:processing-recovery:lock",
                "1",
                ex=settings.KB_PROCESSING_RECOVERY_AFTER_SECONDS,
                nx=True,
            )
        except Exception as e:
            logger.warning("KB document task recovery skipped: %s", e)
            return

        if not lock_acquired:
            return

        cutoff = datetime.now(timezone.utc) - timedelta(
            seconds=settings.KB_PROCESSING_RECOVERY_AFTER_SECONDS
        )
        documents = await Document.filter(
            status=DocumentStatus.PROCESSING.value,
            updated_at__lt=cutoff,
        ).limit(100)

        for document in documents:
            metadata = document.metadata or {}
            task_name = metadata.get("task_name")
            task_args = metadata.get("task_args")
            if not task_name or not isinstance(task_args, list):
                continue

            task_id = str(uuid4())
            metadata["task_id"] = task_id
            document.metadata = metadata
            await document.save(update_fields=["metadata"])
            celery_app.send_task(task_name, args=task_args, task_id=task_id)
            logger.warning(
                "Recovered stale KB document task: document_id=%s task_name=%s task_id=%s",
                document.id,
                task_name,
                task_id,
            )

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(_init())
    loop.run_until_complete(_recover_processing_documents())
    register_all_builtin_tools()


# Close Tortoise ORM when worker process shuts down
@worker_process_shutdown.connect
def close_tortoise(**kwargs):
    """Close Tortoise ORM connections when worker shuts down."""
    import asyncio
    from tortoise import Tortoise

    async def _close():
        await Tortoise.close_connections()

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(_close())
        else:
            loop.run_until_complete(_close())
    except Exception:
        pass
