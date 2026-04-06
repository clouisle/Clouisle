"""
Tests for non-executable workflow nodes in the execution plan.
"""

from app.services.workflow.plan import ExecutionPlan


def test_comment_nodes_are_excluded_from_execution_plan():
    workflow_def = {
        "nodes": [
            {"id": "start", "type": "user_input", "data": {"type": "user_input"}},
            {"id": "note_1", "type": "comment", "data": {"type": "comment"}},
            {"id": "end", "type": "answer", "data": {"type": "answer"}},
        ],
        "edges": [
            {"source": "start", "target": "end"},
        ],
    }

    plan = ExecutionPlan.from_workflow(workflow_def)

    assert "note_1" not in plan.nodes
    assert plan.get_execution_order() == ["start", "end"]
    assert plan.validate() == []


def test_edges_to_comment_nodes_are_ignored():
    workflow_def = {
        "nodes": [
            {"id": "start", "type": "user_input", "data": {"type": "user_input"}},
            {"id": "note_1", "type": "comment", "data": {"type": "comment"}},
            {"id": "end", "type": "answer", "data": {"type": "answer"}},
        ],
        "edges": [
            {"source": "start", "target": "note_1"},
            {"source": "start", "target": "end"},
        ],
    }

    plan = ExecutionPlan.from_workflow(workflow_def)

    assert plan.get_downstream_nodes("start") == ["end"]
    assert plan.get_upstream_nodes("end") == ["start"]
    assert plan.validate() == []
