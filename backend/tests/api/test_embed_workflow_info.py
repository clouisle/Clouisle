"""Embed workflow info projects the start node's input parameters.

The embed page has no definition editor and must not receive node configs, so
only the public parameter metadata is exposed. These tests pin the projection
and its defensive branches without needing a database.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.api.v1.endpoints.embed import (
    MAX_EMBED_INPUT_PARAMETERS,
    _embedded_workflow_input_parameters,
)


def _workflow(definition):
    return SimpleNamespace(definition=definition)


def _start_node(parameters, *, node_type: str = "user_input", on_config: bool = True):
    data = {"type": node_type}
    if on_config:
        data["config"] = {"parameters": parameters}
    else:
        data["parameters"] = parameters
    return {"id": "start", "type": node_type, "data": data}


def test_projects_start_node_parameters_from_config():
    workflow = _workflow(
        {
            "nodes": [
                {"id": "other", "type": "answer", "data": {"type": "answer"}},
                _start_node(
                    [
                        {"name": "query", "type": "text", "required": True},
                        {
                            "name": "limit",
                            "type": "number",
                            "required": False,
                            "default": 5,
                        },
                    ]
                ),
            ]
        }
    )

    assert _embedded_workflow_input_parameters(workflow) == [
        {"name": "query", "type": "text", "required": True},
        {"name": "limit", "type": "number", "required": False, "default": 5},
    ]


def test_projects_public_fields_only():
    workflow = _workflow(
        {
            "nodes": [
                _start_node(
                    [
                        {
                            "name": "tone",
                            "label": "Tone",
                            "description": "How formal",
                            "options": ["warm", 3],
                            "credential": "should-not-leak",
                        }
                    ]
                )
            ]
        }
    )

    (parameter,) = _embedded_workflow_input_parameters(workflow)

    assert parameter == {
        "name": "tone",
        "type": "text",
        "required": True,
        "label": "Tone",
        "description": "How formal",
        "options": ["warm", "3"],
    }
    assert "credential" not in parameter


def test_falls_back_to_data_parameters_and_trigger_nodes():
    workflow = _workflow(
        {
            "nodes": [
                _start_node(
                    [{"name": "url", "required": True}],
                    node_type="trigger",
                    on_config=False,
                )
            ]
        }
    )

    assert _embedded_workflow_input_parameters(workflow) == [
        {"name": "url", "type": "text", "required": True}
    ]


def test_returns_empty_without_a_usable_start_node():
    assert _embedded_workflow_input_parameters(_workflow(None)) == []
    assert _embedded_workflow_input_parameters(_workflow({"nodes": "nope"})) == []
    assert _embedded_workflow_input_parameters(_workflow({"nodes": ["nope", {}]})) == []
    assert (
        _embedded_workflow_input_parameters(_workflow({"nodes": [{"data": "nope"}]}))
        == []
    )
    assert (
        _embedded_workflow_input_parameters(
            _workflow({"nodes": [{"data": {"type": "answer"}}]})
        )
        == []
    )
    assert (
        _embedded_workflow_input_parameters(
            _workflow({"nodes": [{"data": {"type": "user_input", "config": {}}}]})
        )
        == []
    )


def test_skips_unnamed_entries_and_caps_inspected_entries():
    parameters = [
        {"name": f"p{index}"} for index in range(MAX_EMBED_INPUT_PARAMETERS + 5)
    ]
    parameters.insert(1, {"type": "text"})

    projected = _embedded_workflow_input_parameters(
        _workflow({"nodes": [_start_node(parameters)]})
    )

    # The bound is on inspected entries, so it also caps the response and keeps
    # a malformed definition from costing more than a fixed amount of work.
    assert len(projected) == MAX_EMBED_INPUT_PARAMETERS - 1
    assert all(parameter["name"].startswith("p") for parameter in projected)


def test_caps_a_definition_with_only_named_entries():
    parameters = [
        {"name": f"p{index}"} for index in range(MAX_EMBED_INPUT_PARAMETERS + 5)
    ]

    projected = _embedded_workflow_input_parameters(
        _workflow({"nodes": [_start_node(parameters)]})
    )

    assert len(projected) == MAX_EMBED_INPUT_PARAMETERS
    assert projected[-1]["name"] == f"p{MAX_EMBED_INPUT_PARAMETERS - 1}"
