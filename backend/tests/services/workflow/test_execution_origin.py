"""Trusted workflow provenance: stamp, read and inheritance rules.

`trigger_type` mirrors the workflow's configured trigger, so these tests pin
that provenance comes only from the persisted, server-stamped origin.
"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.schemas.tool_approval import ExecutionEntrypoint
from app.services.workflow.execution_origin import (
    ORIGIN_SNAPSHOT_KEY,
    WorkflowExecutionOrigin,
    api_key_origin,
    embed_origin,
    inherited_origin,
    origin_snapshot,
    read_run_origin,
    schedule_origin,
    stamp_run_origin,
    workflow_origin,
)


def test_snapshot_shape_and_validation():
    key_id = uuid4()
    assert origin_snapshot(api_key_origin(key_id)) == {
        "entrypoint": "api_key",
        "entrypoint_id": str(key_id),
    }
    assert origin_snapshot(embed_origin("wf-1"))["entrypoint"] == "embed"

    with pytest.raises(ValueError):
        WorkflowExecutionOrigin(ExecutionEntrypoint.CHAT, "conversation-1")
    with pytest.raises(ValueError):
        WorkflowExecutionOrigin(ExecutionEntrypoint.WORKFLOW, "   ")
    with pytest.raises(ValueError):
        WorkflowExecutionOrigin(ExecutionEntrypoint.WORKFLOW, "x" * 201)


def test_read_prefers_persisted_origin_over_the_configured_trigger():
    workflow_id, key_id = uuid4(), uuid4()
    run = SimpleNamespace(
        id=uuid4(),
        workflow_id=workflow_id,
        # A cron-configured workflow whose run was actually started with a key.
        trigger_type="cron",
        context_snapshot={ORIGIN_SNAPSHOT_KEY: origin_snapshot(api_key_origin(key_id))},
    )

    origin = read_run_origin(run)

    assert origin is not None
    assert origin.entrypoint is ExecutionEntrypoint.API_KEY
    assert origin.entrypoint_id == str(key_id)


def test_manual_run_of_cron_workflow_is_the_workflow_surface():
    workflow_id = uuid4()
    run = SimpleNamespace(
        id=uuid4(),
        workflow_id=workflow_id,
        trigger_type="cron",
        context_snapshot={},
    )

    assert read_run_origin(run) == workflow_origin(workflow_id)


@pytest.mark.parametrize(
    "snapshot_value",
    [
        "api_key",
        {"entrypoint": "chat", "entrypoint_id": "conversation-1"},
        {"entrypoint": "tool_test", "entrypoint_id": "x"},
        {"entrypoint": "api_key", "entrypoint_id": ""},
        {"entrypoint": "api_key", "entrypoint_id": 5},
    ],
)
def test_malformed_origins_fall_back_to_the_workflow_surface(snapshot_value):
    workflow_id = uuid4()
    run = SimpleNamespace(
        id=uuid4(),
        workflow_id=workflow_id,
        trigger_type="cron",
        context_snapshot={ORIGIN_SNAPSHOT_KEY: snapshot_value},
    )

    assert read_run_origin(run) == workflow_origin(workflow_id)


def test_read_requires_a_workflow_id():
    run = SimpleNamespace(id=uuid4(), workflow_id=None, context_snapshot={})

    assert read_run_origin(run) is None


def test_stamp_never_rewrites_an_established_origin():
    workflow_id = uuid4()
    run = SimpleNamespace(
        id=uuid4(),
        workflow_id=workflow_id,
        context_snapshot={"workflow_definition": {"nodes": []}},
    )

    assert stamp_run_origin(run, schedule_origin(workflow_id)) is True
    assert read_run_origin(run) == schedule_origin(workflow_id)

    # A resume pass cannot change the surface.
    assert stamp_run_origin(run, workflow_origin(workflow_id)) is False
    origin = read_run_origin(run)
    assert origin is not None and origin.entrypoint is ExecutionEntrypoint.SCHEDULE
    assert run.context_snapshot["workflow_definition"] == {"nodes": []}

    assert stamp_run_origin(run, workflow_origin(workflow_id), overwrite=True) is True
    origin = read_run_origin(run)
    assert origin is not None and origin.entrypoint is ExecutionEntrypoint.WORKFLOW


def test_subworkflow_inherits_the_root_surface():
    workflow_id, key_id = uuid4(), uuid4()
    parent = SimpleNamespace(
        id=uuid4(),
        workflow_id=workflow_id,
        context_snapshot={ORIGIN_SNAPSHOT_KEY: origin_snapshot(api_key_origin(key_id))},
    )
    assert inherited_origin(parent) == api_key_origin(key_id)

    legacy_parent = SimpleNamespace(
        id=uuid4(), workflow_id=workflow_id, context_snapshot={}
    )
    assert inherited_origin(legacy_parent) == workflow_origin(workflow_id)

    orphan = SimpleNamespace(id=uuid4(), workflow_id=None, context_snapshot={})
    assert inherited_origin(orphan) is None
