"""
Celery application configuration for Clouisle backend.
"""

from celery import Celery
from celery.schedules import crontab
from celery.signals import worker_process_init, worker_process_shutdown

from app.core.config import settings

# Redis URL for Celery broker and result backend
if settings.REDIS_PASSWORD:
    REDIS_URL = (
        f"redis://:{settings.REDIS_PASSWORD}@{settings.REDIS_HOST}:{settings.REDIS_PORT}"
    )
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
    # Result settings
    result_expires=3600 * 24,  # 24 hours
    # Worker settings
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=100,
    # Retry settings
    broker_connection_retry_on_startup=True,
)

# Optional: Configure task routes
celery_app.conf.task_routes = {
    "app.tasks.knowledge_base.*": {"queue": "default"},
    "app.tasks.usage.*": {"queue": "default"},
    "app.tasks.workflow.*": {"queue": "workflow"},
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
    # Archive old audit logs every day at 03:00
    "archive-old-audit-logs": {
        "task": "app.tasks.audit_log.archive_old_audit_logs",
        "schedule": crontab(hour=3, minute=0),
    },
}


# Initialize Tortoise ORM when worker process starts
@worker_process_init.connect
def init_tortoise(**kwargs):
    """Initialize Tortoise ORM for each worker process."""
    import asyncio
    from tortoise import Tortoise

    async def _init():
        await Tortoise.init(
            db_url=settings.DATABASE_URL
            or f"postgres://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}@{settings.POSTGRES_SERVER}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}",
            modules={"models": ["app.models"]},
        )

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(_init())


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
