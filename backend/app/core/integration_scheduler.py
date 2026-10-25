"""Reconcile messaging Beat entries against persisted administrator settings."""

import asyncio
import logging
from time import monotonic

from celery.beat import PersistentScheduler
from tortoise.context import TortoiseContext

from app.core.config import settings
from app.models.feishu_knowledge import FeishuKnowledgeSource
from app.models.integration import Integration
from app.services.integration_features import active_features

logger = logging.getLogger(__name__)
REFRESH_SECONDS = 2.0

# Templates only: disabled entries must not remain in Beat's active schedule.
INTEGRATION_SCHEDULE = {
    "poll-wechat-bindings": {
        "task": "app.tasks.wechat_poll.dispatch_bindings_task",
        "schedule": 3.0,
        "options": {"queue": "default", "expires": 3},
    },
    "recover-wechat-agent-bindings": {
        "task": "app.tasks.wechat_agent.recover_bindings_task",
        "schedule": 3.0,
        "options": {"queue": "agent"},
    },
    "recover-wechat-knowledge-receipts": {
        "task": "app.tasks.wechat_knowledge.recover_receipts_task",
        "schedule": 60.0,
        "options": {"queue": "knowledge"},
    },
    "recover-feishu-agent-channel": {
        "task": "app.tasks.feishu_agent.recover_pending_task",
        "schedule": 10.0,
        "options": {"queue": "agent"},
    },
    "dispatch-feishu-knowledge-sync": {
        "task": "app.tasks.feishu_knowledge.dispatch_due_sources_task",
        "schedule": 60.0,
        "options": {"queue": "knowledge"},
    },
}


class IntegrationScheduler(PersistentScheduler):
    """Keep PostgreSQL authoritative without dispatching feature-check tasks.

    Beat owns its ORM context and event loop; API workers only persist settings.
    The persistent scheduler still owns ordinary entries and their run times.
    """

    def __init__(self, *args, **kwargs):
        self._runner = asyncio.Runner()
        self._context = TortoiseContext()
        self._next_refresh = 0.0
        super().__init__(*args, **kwargs)
        self.max_interval = min(self.max_interval, REFRESH_SECONDS)

    async def _enabled_entries(self) -> set[str]:
        with self._context:
            if not self._context.inited:
                await self._context.init(
                    db_url=settings.DATABASE_URL,
                    modules={"models": ["app.models"]},
                )
            integrations = await Integration.filter(
                provider_type__in=["wechat", "feishu"]
            ).only("provider_type", "is_enabled", "enabled_capabilities")
            enabled = set()
            for integration in integrations:
                features = active_features(integration)
                if integration.provider_type == "wechat":
                    if features.intersection({"agent_chat", "knowledge_collection"}):
                        enabled.add("poll-wechat-bindings")
                    if "agent_chat" in features:
                        enabled.add("recover-wechat-agent-bindings")
                    if "knowledge_collection" in features:
                        enabled.add("recover-wechat-knowledge-receipts")
                else:
                    if "agent_chat" in features:
                        enabled.add("recover-feishu-agent-channel")
                    # Wiki imports have source-level switches, not a capability
                    # switch. Directory sync and login must not control them.
                    if (
                        integration.is_enabled
                        and await FeishuKnowledgeSource.filter(is_enabled=True).exists()
                    ):
                        enabled.add("dispatch-feishu-knowledge-sync")
            return enabled

    def tick(self, *args, **kwargs):
        if monotonic() >= self._next_refresh:
            try:
                enabled = self._runner.run(
                    asyncio.wait_for(self._enabled_entries(), timeout=3)
                )
            except Exception:
                # Never continue publishing against a stale enabled snapshot.
                # Ordinary maintenance must keep running during a DB outage.
                logger.warning(
                    "Integration schedule refresh failed; pausing integration tasks"
                )
                enabled = set()
            self._next_refresh = monotonic() + REFRESH_SECONDS
            for name, template in INTEGRATION_SCHEDULE.items():
                if name not in enabled:
                    if self.schedule.pop(name, None) is not None:
                        self._heap = None
                elif name not in self.schedule:
                    self.update_from_dict({name: template})
                    self._heap = None
        delay = super().tick(*args, **kwargs)
        return min(delay, max(0.0, self._next_refresh - monotonic()))

    def close(self):
        try:
            if self._context.inited:
                self._runner.run(self._context.close_connections())
        finally:
            self._runner.close()
            super().close()
