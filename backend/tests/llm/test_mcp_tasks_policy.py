"""Capability and policy tests for MCP client task support (issue #500).

These are the pure parts: which capability is advertised on which protocol
revision, and how the platform flag plus a server's own settings resolve into
bounded polling values. The loop itself is covered in ``test_mcp_tasks.py``.
"""

from __future__ import annotations

from unittest.mock import patch

import mcp.types as types

from app.llm.tools import mcp_client, mcp_tasks


def test_capability_is_declared_only_on_the_task_revision():
    capability = mcp_tasks.capability_for(mcp_tasks.TASKS_PROTOCOL_VERSION)

    assert capability == types.ClientTasksCapability(
        cancel=types.TasksCancelCapability()
    )
    # Only ``cancel`` is truthful: ``tasks/list`` is not implemented and this
    # adapter never augments its own sampling/elicitation requests.
    assert capability.list is None
    assert capability.requests is None
    assert mcp_tasks.capability_for("2025-06-18") is None
    assert mcp_tasks.capability_for(None) is None


def test_session_class_is_off_unless_the_policy_enables_tasks(monkeypatch):
    enabled = mcp_tasks.McpTaskPolicy(enabled=True)

    assert mcp_tasks.task_session_class(mcp_tasks.DEFAULT_TASK_POLICY) is None
    assert mcp_tasks.task_session_class(enabled) is mcp_tasks._TaskCapableSession

    monkeypatch.setattr(mcp_tasks, "TASKS_SDK_READY", False)
    assert mcp_tasks.task_session_class(enabled) is None


def test_session_declares_tasks_on_the_negotiated_task_revision():
    session = mcp_tasks._TaskCapableSession.__new__(mcp_tasks._TaskCapableSession)
    base = types.ClientCapabilities()

    with patch.object(
        mcp_client.ClientSession, "_build_capabilities", return_value=base
    ) as hook:
        declared = session._build_capabilities(mcp_tasks.TASKS_PROTOCOL_VERSION)
        other = session._build_capabilities("2026-07-28")

    assert hook.call_count == 2
    assert declared.tasks == types.ClientTasksCapability(
        cancel=types.TasksCancelCapability()
    )
    assert other.tasks is None


def test_client_reads_both_switches_from_its_config(monkeypatch):
    monkeypatch.setattr(mcp_tasks.settings, "MCP_TASKS_ENABLED", True)

    assert mcp_client.McpClient({"enable_tasks": True}).tasks.enabled is True
    assert mcp_client.McpClient({}).tasks.enabled is False


def test_both_switches_are_required(monkeypatch):
    monkeypatch.setattr(mcp_tasks.settings, "MCP_TASKS_ENABLED", False)
    assert (
        mcp_tasks.resolve_task_policy({"enable_tasks": True})
        == mcp_tasks.DEFAULT_TASK_POLICY
    )
    assert (
        mcp_tasks.resolve_task_policy({"enable_tasks": True}, global_enabled=False)
        == mcp_tasks.DEFAULT_TASK_POLICY
    )
    assert (
        mcp_tasks.resolve_task_policy(None, global_enabled=True)
        == mcp_tasks.DEFAULT_TASK_POLICY
    )
    assert (
        mcp_tasks.resolve_task_policy({"enable_tasks": False}, global_enabled=True)
        == mcp_tasks.DEFAULT_TASK_POLICY
    )

    monkeypatch.setattr(mcp_tasks.settings, "MCP_TASKS_ENABLED", True)
    policy = mcp_tasks.resolve_task_policy({"enable_tasks": True})

    assert policy.enabled is True
    assert policy.poll_interval == mcp_tasks.DEFAULT_POLL_INTERVAL_SECONDS
    assert policy.timeout == mcp_tasks.DEFAULT_TASK_TIMEOUT_SECONDS
    assert policy.max_polls == mcp_tasks.DEFAULT_MAX_POLLS


def test_out_of_range_bounds_are_clamped():
    policy = mcp_tasks.resolve_task_policy(
        {
            "enable_tasks": True,
            "tasks_poll_interval_seconds": 0.001,
            "tasks_timeout_seconds": 99999,
            "tasks_max_polls": 0,
        },
        global_enabled=True,
    )

    assert policy.poll_interval == mcp_tasks.MIN_POLL_INTERVAL_SECONDS
    assert policy.timeout == mcp_tasks.MAX_TASK_TIMEOUT_SECONDS
    assert policy.max_polls == 1


def test_unparseable_bounds_fall_back_to_defaults():
    policy = mcp_tasks.resolve_task_policy(
        {
            "enable_tasks": True,
            "tasks_poll_interval_seconds": "soon",
            "tasks_timeout_seconds": None,
            "tasks_max_polls": "many",
        },
        global_enabled=True,
    )

    assert policy.poll_interval == mcp_tasks.DEFAULT_POLL_INTERVAL_SECONDS
    assert policy.timeout == mcp_tasks.DEFAULT_TASK_TIMEOUT_SECONDS
    assert policy.max_polls == mcp_tasks.DEFAULT_MAX_POLLS


def test_enabled_policy_without_sdk_support_stays_off(monkeypatch):
    monkeypatch.setattr(mcp_tasks, "TASKS_SDK_READY", False)

    assert (
        mcp_tasks.resolve_task_policy({"enable_tasks": True}, global_enabled=True)
        == mcp_tasks.DEFAULT_TASK_POLICY
    )
