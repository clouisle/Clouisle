from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.llm.types import DecisionAnswer, DecisionResponse, Usage
from app.services.workflow.executors.decision import DecisionNodeExecutor


@pytest.mark.asyncio
async def test_decision_executor_activates_selected_choice_branch():
    context = SimpleNamespace(
        resolve_template=AsyncMock(return_value="user cannot log in"),
        set_branch=AsyncMock(),
    )
    workflow = SimpleNamespace(team_id="team-1")
    run = SimpleNamespace(workflow_id="workflow-1")
    response = DecisionResponse(
        model="jev-1.13.0",
        answers={
            "route": DecisionAnswer(
                type="choice",
                choice="support",
                confidence=0.91,
                probabilities={"support": 0.91, "billing": 0.09},
            )
        },
        usage=Usage(total_tokens=12),
    )
    node = {
        "id": "decision-1",
        "data": {
            "decisionConfig": {
                "modelId": "team-model-1",
                "stateTemplate": "{{start.question}}",
                "questionId": "route",
                "questionType": "choice",
                "instructions": "Choose a support route",
                "options": ["support", "billing"],
            }
        },
    }

    with (
        patch(
            "app.models.workflow.Workflow.get_or_none",
            new=AsyncMock(return_value=workflow),
        ),
        patch(
            "app.services.workflow.executors.decision.model_manager.team_decide",
            new=AsyncMock(return_value=response),
        ) as decide,
    ):
        result = await DecisionNodeExecutor().execute(node, context, run)

    assert result.success
    assert result.next_handles == ["support"]
    assert result.outputs["answer"] == "support"
    context.set_branch.assert_awaited_once_with("decision-1", "support")
    decide.assert_awaited_once()
    sent_request = decide.await_args.args[1]
    assert sent_request.questions["route"].criteria == {
        "support": None,
        "billing": None,
    }


@pytest.mark.asyncio
async def test_decision_executor_routes_score_to_highest_probability_level():
    context = SimpleNamespace(
        resolve_template=AsyncMock(return_value="support request"),
        set_branch=AsyncMock(),
    )
    response = DecisionResponse(
        model="jev-1.13.0",
        answers={
            "priority": DecisionAnswer(
                type="score",
                score=0.8,
                confidence=0.8,
                probabilities={"0": 0.2, "1": 0.8},
                legend={"0": "low", "1": "high"},
            )
        },
        usage=Usage(total_tokens=8),
    )
    node = {
        "id": "decision-score",
        "data": {
            "decisionConfig": {
                "modelId": "team-model-1",
                "stateTemplate": "{{start.question}}",
                "questionId": "priority",
                "questionType": "score",
                "instructions": "Rate the priority",
                "options": ["low", "high"],
            }
        },
    }
    with (
        patch(
            "app.models.workflow.Workflow.get_or_none",
            new=AsyncMock(return_value=SimpleNamespace(team_id="team-1")),
        ),
        patch(
            "app.services.workflow.executors.decision.model_manager.team_decide",
            new=AsyncMock(return_value=response),
        ) as decide,
    ):
        result = await DecisionNodeExecutor().execute(
            node, context, SimpleNamespace(workflow_id="workflow-1")
        )

    assert result.success
    assert result.outputs["score"] == 0.8
    assert result.outputs["answer"] == "high"
    assert result.next_handles == ["high"]
    sent_request = decide.await_args.args[1]
    assert sent_request.questions["priority"].criteria == ["low", "high"]
    context.set_branch.assert_awaited_once_with("decision-score", "high")


@pytest.mark.asyncio
async def test_decision_executor_routes_noul_probability_without_confidence():
    context = SimpleNamespace(
        resolve_template=AsyncMock(return_value="Is Alex a student?"),
        set_branch=AsyncMock(),
    )
    response = DecisionResponse(
        model="jev-1.13.0",
        answers={"decision": DecisionAnswer(type="noul", noul=0.7)},
        usage=Usage(total_tokens=5),
    )
    node = {
        "id": "decision-noul",
        "data": {
            "decisionConfig": {
                "modelId": "model-1",
                "stateTemplate": "Is Alex a student?",
                "questionType": "noul",
                "instructions": "Is Alex a student?",
                "confidenceThreshold": 0.99,
                "defaultHandle": "fallback",
            }
        },
    }
    with (
        patch(
            "app.models.workflow.Workflow.get_or_none",
            new=AsyncMock(return_value=SimpleNamespace(team_id="team-1")),
        ),
        patch(
            "app.services.workflow.executors.decision.model_manager.team_decide",
            new=AsyncMock(return_value=response),
        ) as decide,
    ):
        result = await DecisionNodeExecutor().execute(
            node, context, SimpleNamespace(workflow_id="workflow-1")
        )

    assert result.success
    assert result.outputs["noul"] == 0.7
    assert "confidence" not in result.outputs
    assert result.outputs["answer"] == "yes"
    assert result.next_handles == ["yes"]
    assert decide.await_args.args[1].questions["decision"].criteria is None
    assert {
        output["name"]
        for output in DecisionNodeExecutor().get_output_variables(
            node["data"]["decisionConfig"]
        )
    } == {"answer", "noul", "selected_handle", "usage"}


@pytest.mark.asyncio
async def test_decision_executor_rejects_missing_choice_options():
    context = SimpleNamespace(resolve_template=AsyncMock(), set_branch=AsyncMock())
    run = SimpleNamespace(workflow_id="workflow-1")
    node = {
        "id": "decision-1",
        "data": {
            "decisionConfig": {
                "modelId": "team-model-1",
                "stateTemplate": "{{start.question}}",
                "instructions": "Choose a route",
                "questionType": "choice",
                "options": [],
            }
        },
    }

    result = await DecisionNodeExecutor().execute(node, context, run)

    assert not result.success
    assert result.error == "validation_error"
    context.resolve_template.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("question_type", "options", "expected_error"),
    [
        ("choice", ["only-option"], False),
        ("choice", ["same", "same"], True),
        ("choice", [f"option-{index}" for index in range(256)], True),
        ("score", ["low"], True),
        ("score", [f"level-{index}" for index in range(11)], True),
    ],
)
async def test_decision_config_enforces_typesafe_option_limits(
    question_type, options, expected_error
):
    errors = await DecisionNodeExecutor().validate_config(
        {
            "modelId": "model-1",
            "stateTemplate": "state",
            "instructions": "Choose or score",
            "questionType": question_type,
            "options": options,
        }
    )

    assert bool(errors) is expected_error


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "config",
    [
        {},
        {"modelId": "model-1", "instructions": "Choose"},
        {"modelId": "model-1", "stateTemplate": "state"},
        {
            "modelId": "model-1",
            "stateTemplate": "state",
            "instructions": "Choose",
            "questionType": "unknown",
        },
        {
            "modelId": "model-1",
            "stateTemplate": "state",
            "instructions": "Choose",
            "questionType": "choice",
            "options": "yes",
        },
        {
            "modelId": "model-1",
            "stateTemplate": "state",
            "instructions": "Choose",
            "questionType": "choice",
            "options": ["yes", " "],
        },
    ],
)
async def test_decision_executor_rejects_invalid_configuration_before_calls(config):
    context = SimpleNamespace(resolve_template=AsyncMock(), set_branch=AsyncMock())
    run = SimpleNamespace(workflow_id="workflow-1")
    node = {"id": "decision-1", "data": {"decisionConfig": config}}

    result = await DecisionNodeExecutor().execute(node, context, run)

    assert result.error == "validation_error"
    context.resolve_template.assert_not_awaited()
    context.set_branch.assert_not_awaited()


@pytest.mark.asyncio
async def test_decision_executor_returns_not_found_for_missing_workflow():
    context = SimpleNamespace(
        resolve_template=AsyncMock(return_value="state"), set_branch=AsyncMock()
    )
    node = {
        "id": "decision-1",
        "data": {
            "decisionConfig": {
                "modelId": "model-1",
                "stateTemplate": "state",
                "instructions": "Choose",
                "questionType": "noul",
            }
        },
    }

    with patch(
        "app.models.workflow.Workflow.get_or_none", new=AsyncMock(return_value=None)
    ):
        result = await DecisionNodeExecutor().execute(
            node, context, SimpleNamespace(workflow_id="missing")
        )

    assert result.error == "workflow_not_found"
    context.set_branch.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "answers",
    [
        {},
        {"route": None},
        {"route": SimpleNamespace(type="score")},
        {
            "route": SimpleNamespace(
                type="choice", choice="unknown", probabilities={"yes": 0.7, "no": 0.3}
            )
        },
        {
            "route": SimpleNamespace(
                type="choice", choice="yes", probabilities={"yes": 1.0}
            )
        },
    ],
)
async def test_decision_executor_rejects_incomplete_choice_answers(answers):
    context = SimpleNamespace(
        resolve_template=AsyncMock(return_value="state"), set_branch=AsyncMock()
    )
    response = SimpleNamespace(answers=answers, usage=Usage(total_tokens=1))
    node = {
        "id": "decision-1",
        "data": {
            "decisionConfig": {
                "modelId": "model-1",
                "stateTemplate": "state",
                "questionId": "route",
                "instructions": "Choose",
                "options": ["yes", "no"],
            }
        },
    }
    with (
        patch(
            "app.models.workflow.Workflow.get_or_none",
            new=AsyncMock(return_value=SimpleNamespace(team_id="team-1")),
        ),
        patch(
            "app.services.workflow.executors.decision.model_manager.team_decide",
            new=AsyncMock(return_value=response),
        ),
    ):
        result = await DecisionNodeExecutor().execute(
            node, context, SimpleNamespace(workflow_id="workflow-1")
        )

    assert result.error == "decision_result_missing"
    context.set_branch.assert_not_awaited()


@pytest.mark.asyncio
async def test_decision_executor_uses_default_handle_below_confidence_threshold():
    context = SimpleNamespace(
        resolve_template=AsyncMock(return_value="state"), set_branch=AsyncMock()
    )
    response = SimpleNamespace(
        answers={
            "route": SimpleNamespace(
                type="choice",
                choice="yes",
                confidence=0.4,
                probabilities={"yes": 0.6, "no": 0.4},
            )
        },
        usage=Usage(total_tokens=1),
    )
    node = {
        "id": "decision-1",
        "data": {
            "decisionConfig": {
                "modelId": "model-1",
                "stateTemplate": "state",
                "questionId": "route",
                "instructions": "Choose",
                "options": ["yes", "no"],
                "confidenceThreshold": 0.8,
                "defaultHandle": "review",
            }
        },
    }
    with (
        patch(
            "app.models.workflow.Workflow.get_or_none",
            new=AsyncMock(return_value=SimpleNamespace(team_id="team-1")),
        ),
        patch(
            "app.services.workflow.executors.decision.model_manager.team_decide",
            new=AsyncMock(return_value=response),
        ),
    ):
        result = await DecisionNodeExecutor().execute(
            node, context, SimpleNamespace(workflow_id="workflow-1")
        )

    assert result.outputs["answer"] == "yes"
    assert result.outputs["selected_handle"] == "review"
    assert result.next_handles == ["review"]
    context.set_branch.assert_awaited_once_with("decision-1", "review")


@pytest.mark.asyncio
async def test_decision_executor_routes_noul_probability_below_half_to_no():
    context = SimpleNamespace(
        resolve_template=AsyncMock(return_value="state"), set_branch=AsyncMock()
    )
    response = DecisionResponse(
        model="jev-1.13.0",
        answers={"decision": DecisionAnswer(type="noul", noul=0.3)},
        usage=Usage(total_tokens=1),
    )
    node = {
        "id": "decision-noul",
        "data": {
            "decisionConfig": {
                "modelId": "model-1",
                "stateTemplate": "state",
                "instructions": "Is this true?",
                "questionType": "noul",
            }
        },
    }
    with (
        patch(
            "app.models.workflow.Workflow.get_or_none",
            new=AsyncMock(return_value=SimpleNamespace(team_id="team-1")),
        ),
        patch(
            "app.services.workflow.executors.decision.model_manager.team_decide",
            new=AsyncMock(return_value=response),
        ),
    ):
        result = await DecisionNodeExecutor().execute(
            node, context, SimpleNamespace(workflow_id="workflow-1")
        )

    assert result.outputs["answer"] == "no"
    assert result.next_handles == ["no"]


@pytest.mark.asyncio
async def test_decision_executor_translates_provider_errors():
    context = SimpleNamespace(
        resolve_template=AsyncMock(return_value="state"), set_branch=AsyncMock()
    )
    node = {
        "id": "decision-1",
        "data": {
            "decisionConfig": {
                "modelId": "model-1",
                "stateTemplate": "state",
                "instructions": "Choose",
                "options": ["yes", "no"],
            }
        },
    }
    with (
        patch(
            "app.models.workflow.Workflow.get_or_none",
            new=AsyncMock(return_value=SimpleNamespace(team_id="team-1")),
        ),
        patch(
            "app.services.workflow.executors.decision.model_manager.team_decide",
            new=AsyncMock(side_effect=RuntimeError("upstream unavailable")),
        ),
        patch(
            "app.services.workflow.executors.decision.translate_public_workflow_error",
            return_value="model_unavailable",
        ),
    ):
        result = await DecisionNodeExecutor().execute(
            node, context, SimpleNamespace(workflow_id="workflow-1")
        )

    assert result.error == "model_unavailable"


def test_decision_executor_declares_type_specific_outputs():
    executor = DecisionNodeExecutor()

    assert [
        output.name for output in executor.get_output_specs({"questionType": "choice"})
    ] == ["answer", "choice", "confidence", "probabilities", "selected_handle", "usage"]
    assert [
        output.name for output in executor.get_output_specs({"questionType": "score"})
    ] == ["answer", "score", "confidence", "probabilities", "selected_handle", "usage"]
    assert [
        output.name for output in executor.get_output_specs({"questionType": "noul"})
    ] == ["answer", "noul", "selected_handle", "usage"]


@pytest.mark.asyncio
async def test_decision_config_requires_fields_and_accepts_noul_without_options():
    executor = DecisionNodeExecutor()

    errors = await executor.validate_config({"questionType": "unsupported"})
    assert errors == [
        "modelId is required",
        "stateTemplate is required",
        "instructions is required",
        "questionType must be choice, score, or noul",
    ]
    assert (
        await executor.validate_config(
            {
                "modelId": "model-1",
                "stateTemplate": "state",
                "instructions": "Is this true?",
                "questionType": "noul",
            }
        )
        == []
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "answer",
    [
        SimpleNamespace(
            type="score",
            score=0.5,
            confidence=0.8,
            probabilities={"0": 0.7},
            legend={"0": "low", "1": "high"},
        ),
        SimpleNamespace(
            type="score",
            score=0.5,
            confidence=0.8,
            probabilities={"0": 0.7, "1": 0.3},
            legend={"0": "low"},
        ),
    ],
)
async def test_decision_executor_rejects_incomplete_score_distributions(answer):
    context = SimpleNamespace(
        resolve_template=AsyncMock(return_value="state"), set_branch=AsyncMock()
    )
    response = SimpleNamespace(
        answers={"priority": answer}, usage=Usage(total_tokens=1)
    )
    node = {
        "id": "decision-score",
        "data": {
            "decisionConfig": {
                "modelId": "model-1",
                "stateTemplate": "state",
                "questionId": "priority",
                "questionType": "score",
                "instructions": "Score this",
                "options": ["low", "high"],
            }
        },
    }
    with (
        patch(
            "app.models.workflow.Workflow.get_or_none",
            new=AsyncMock(return_value=SimpleNamespace(team_id="team-1")),
        ),
        patch(
            "app.services.workflow.executors.decision.model_manager.team_decide",
            new=AsyncMock(return_value=response),
        ),
    ):
        result = await DecisionNodeExecutor().execute(
            node, context, SimpleNamespace(workflow_id="workflow-1")
        )

    assert result.error == "decision_result_missing"
    context.set_branch.assert_not_awaited()
