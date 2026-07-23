from app.services.workflow.plan import ExecutionPlan


def _branching_plan() -> ExecutionPlan:
    return ExecutionPlan.from_workflow(
        {
            "nodes": [
                {"id": "start", "type": "user_input", "data": {}},
                {"id": "condition", "type": "condition", "data": {}},
                {"id": "left", "type": "llm", "data": {}},
                {"id": "right", "type": "llm", "data": {}},
                {"id": "end", "type": "answer", "data": {}},
            ],
            "edges": [
                {"source": "start", "target": "condition"},
                {
                    "source": "condition",
                    "target": "left",
                    "sourceHandle": "true",
                },
                {
                    "source": "condition",
                    "target": "right",
                    "sourceHandle": "false",
                },
                {"source": "left", "target": "end"},
                {"source": "right", "target": "end"},
            ],
        }
    )


def test_navigation_handles_missing_nodes_and_branch_handles():
    plan = _branching_plan()

    assert plan.get_downstream_nodes("missing") == []
    assert plan.get_downstream_nodes("condition", "true") == ["left"]
    assert plan.get_downstream_nodes("condition", "missing") == []
    assert plan.get_upstream_nodes("missing") == []
    assert plan.get_branch_paths("missing") == {}
    assert plan.get_branch_paths("condition") == {
        "true": ["left"],
        "false": ["right"],
    }


def test_all_downstream_traverses_branches_once_and_ignores_missing_nodes():
    plan = _branching_plan()

    assert plan.get_all_downstream("condition") == {"left", "right", "end"}
    assert plan.get_all_downstream("missing") == set()


def test_validate_without_start_and_serialize_plan(monkeypatch):
    monkeypatch.setattr("app.services.workflow.plan.t", lambda key, **kwargs: key)
    empty_plan = ExecutionPlan(workflow_def={})

    assert empty_plan.validate() == ["workflow_validation_no_start_node"]

    plan = _branching_plan()
    serialized = plan.to_dict()
    assert serialized["start_node_id"] == "start"
    assert serialized["node_count"] == 5
    assert serialized["stage_count"] == 4
    assert serialized["execution_order"][0] == "start"
    assert serialized["execution_order"][-1] == "end"
