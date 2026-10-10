"""Single-leader maintenance for admin observability.

Runs from API processes so alert evaluation and retention do not depend on a
Celery business worker. A transaction-scoped PostgreSQL advisory lock ensures
only one process performs each bounded cycle.
"""

from __future__ import annotations

import asyncio
import logging

from tortoise.transactions import in_transaction

logger = logging.getLogger(__name__)
MAINTENANCE_INTERVAL_SECONDS = 60


async def run_maintenance_cycle() -> bool:
    """Run one bounded cycle if this process acquires the database leader lock."""
    async with in_transaction() as connection:
        dialect = getattr(getattr(connection, "capabilities", None), "dialect", "")
        if dialect != "postgres":
            logger.debug(
                "Skipping observability maintenance on %s",
                dialect or "unknown database",
            )
            return False
        _, rows = await connection.execute_query(
            """
            SELECT pg_try_advisory_xact_lock(
                hashtextextended('clouisle:observability:maintenance', 0)
            ) AS acquired
            """
        )
        if not rows or not rows[0].get("acquired"):
            return False

        from app.services.observability_v2 import (
            alert_rules,
            evaluate_alert_rules,
            reconcile_agent_terminal_summaries,
            retain,
        )

        repaired = await reconcile_agent_terminal_summaries(connection)
        if repaired:
            logger.info("Reconciled %s terminal AgentRun summaries", repaired)
        await alert_rules()
        await evaluate_alert_rules()
        await retain()
        return True


async def observability_maintenance_loop() -> None:
    """Maintain alerts and bounded retention without a Celery worker."""
    while True:
        try:
            await run_maintenance_cycle()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("Observability maintenance cycle failed", exc_info=True)
        await asyncio.sleep(MAINTENANCE_INTERVAL_SECONDS)
