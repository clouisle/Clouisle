import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services import observability_maintenance


class _Transaction:
    def __init__(self, connection):
        self.connection = connection

    async def __aenter__(self):
        return self.connection

    async def __aexit__(self, *_args):
        return False


def _connection(dialect, acquired=None):
    rows = [] if acquired is None else [{"acquired": acquired}]
    return SimpleNamespace(
        capabilities=SimpleNamespace(dialect=dialect),
        execute_query=AsyncMock(return_value=(None, rows)),
    )


@pytest.mark.asyncio
async def test_maintenance_cycle_skips_when_another_api_process_is_leader(monkeypatch):
    connection = _connection("postgres", acquired=False)
    monkeypatch.setattr(
        observability_maintenance, "in_transaction", lambda: _Transaction(connection)
    )
    alert_rules = AsyncMock()
    evaluate_alert_rules = AsyncMock()
    retain = AsyncMock()
    monkeypatch.setattr("app.services.observability_v2.alert_rules", alert_rules)
    monkeypatch.setattr(
        "app.services.observability_v2.evaluate_alert_rules", evaluate_alert_rules
    )
    monkeypatch.setattr("app.services.observability_v2.retain", retain)

    acquired = await observability_maintenance.run_maintenance_cycle()

    assert acquired is False
    alert_rules.assert_not_awaited()
    evaluate_alert_rules.assert_not_awaited()
    retain.assert_not_awaited()


@pytest.mark.asyncio
async def test_maintenance_skips_postgres_lock_on_non_postgres_database(monkeypatch):
    connection = _connection("sqlite")
    monkeypatch.setattr(
        observability_maintenance, "in_transaction", lambda: _Transaction(connection)
    )
    alert_rules = AsyncMock()
    monkeypatch.setattr("app.services.observability_v2.alert_rules", alert_rules)

    acquired = await observability_maintenance.run_maintenance_cycle()

    assert acquired is False
    connection.execute_query.assert_not_awaited()
    alert_rules.assert_not_awaited()


@pytest.mark.asyncio
async def test_maintenance_loop_survives_cycle_errors_and_propagates_shutdown(
    monkeypatch,
):
    cycle = AsyncMock(
        side_effect=[
            RuntimeError("temporary database failure"),
            asyncio.CancelledError(),
        ]
    )
    monkeypatch.setattr(observability_maintenance, "run_maintenance_cycle", cycle)
    monkeypatch.setattr(observability_maintenance, "MAINTENANCE_INTERVAL_SECONDS", 0)

    with pytest.raises(asyncio.CancelledError):
        await observability_maintenance.observability_maintenance_loop()

    assert cycle.await_count == 2


@pytest.mark.parametrize("repaired", [0, 3])
@pytest.mark.asyncio
async def test_maintenance_runs_alerts_after_acquiring_leader_lock(
    monkeypatch, repaired
):
    connection = _connection("postgres", acquired=True)
    monkeypatch.setattr(
        observability_maintenance, "in_transaction", lambda: _Transaction(connection)
    )
    reconcile = AsyncMock(return_value=repaired)
    alert_rules = AsyncMock()
    evaluate = AsyncMock()
    retain = AsyncMock()
    monkeypatch.setattr(
        "app.services.observability_v2.reconcile_agent_terminal_summaries", reconcile
    )
    monkeypatch.setattr("app.services.observability_v2.alert_rules", alert_rules)
    monkeypatch.setattr("app.services.observability_v2.evaluate_alert_rules", evaluate)
    monkeypatch.setattr("app.services.observability_v2.retain", retain)

    acquired = await observability_maintenance.run_maintenance_cycle()

    assert acquired is True
    reconcile.assert_awaited_once_with(connection)
    alert_rules.assert_awaited_once_with()
    evaluate.assert_awaited_once_with()
    retain.assert_awaited_once_with()
