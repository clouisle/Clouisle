from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.api.v1.endpoints.chat import get_agent_tools, get_tool_display_names
from app.llm.tools.builtin import register_all_builtin_tools
from app.llm.tools.builtin.ask_user import ask_user
from app.llm.tools.interaction import ToolInteractionRequest
from app.models.agent import RAGMode
from app.services.agent_run_store import validate_user_answers


def _agent(tools_config, **overrides):
    values = {
        "id": uuid4(),
        "team_id": uuid4(),
        "tools_config": tools_config,
        "enable_user_input_request": True,
        "enable_memory": False,
        "rag_mode": RAGMode.OFF,
        "enable_image_generation": False,
        "enable_video_generation": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.anyio
async def test_skill_selection_exposes_sandbox_tools():
    register_all_builtin_tools()
    skill = SimpleNamespace(
        id=uuid4(),
        name="demo_skill",
        display_name="Demo Skill",
        description="Run demo skill",
        input_schema={"type": "object", "properties": {}},
    )
    agent = _agent([{"type": "skill", "skill_id": str(skill.id)}])

    with patch(
        "app.services.skill.SkillService.get_skill_for_team",
        new=AsyncMock(return_value=skill),
    ):
        tools = await get_agent_tools(agent)

    names = {tool["function"]["name"] for tool in tools}
    assert any(name.startswith("skill_demo_skill_") for name in names)
    assert {"bash", "edit", "read", "write"}.issubset(names)


@pytest.mark.anyio
async def test_selected_sandbox_builtin_tools_are_exposed_independently():
    register_all_builtin_tools()
    agent = _agent(
        [
            {"type": "builtin", "name": "bash"},
            {"type": "builtin", "name": "read"},
            {"type": "builtin", "name": "edit"},
        ]
    )

    tools = await get_agent_tools(agent)

    names = {tool["function"]["name"] for tool in tools}
    assert {"bash", "edit", "read"}.issubset(names)
    assert "write" not in names


@pytest.mark.anyio
async def test_ask_user_tool_is_available_when_enabled():
    register_all_builtin_tools()

    tools = await get_agent_tools(_agent([]))
    names = {tool["function"]["name"] for tool in tools}
    assert "ask_user" in names
    ask_user = next(tool for tool in tools if tool["function"]["name"] == "ask_user")
    params = ask_user["function"]["parameters"]
    assert "questions" in params["properties"]
    assert "questions" in params["required"]


@pytest.mark.anyio
async def test_ask_user_tool_is_not_available_when_disabled():
    register_all_builtin_tools()

    tools = await get_agent_tools(_agent([], enable_user_input_request=False))
    assert "ask_user" not in {tool["function"]["name"] for tool in tools}


@pytest.mark.anyio
async def test_ask_user_display_name_is_not_exposed_when_disabled():
    names = await get_tool_display_names(_agent([], enable_user_input_request=False))
    assert "ask_user" not in names


@pytest.mark.anyio
async def test_ask_user_uses_one_array_contract_for_one_and_many_questions():
    one = await ask_user([{"id": "target", "question": "Where?"}])
    many = await ask_user(
        [
            {"id": "target", "question": "Where?", "options": ["cloud"]},
            {"id": "region", "question": "Which region?", "required": False},
        ]
    )

    assert isinstance(one, ToolInteractionRequest)
    assert one.arguments == {
        "questions": [{"id": "target", "question": "Where?", "required": True}]
    }
    assert many.arguments == {
        "questions": [
            {
                "id": "target",
                "question": "Where?",
                "options": ["cloud"],
                "required": True,
            },
            {"id": "region", "question": "Which region?", "required": False},
        ]
    }


@pytest.mark.anyio
@pytest.mark.parametrize(
    "questions",
    [
        [],
        "not-a-list",
        [{"id": "target", "question": "Where?"}] * 21,
        ["not-an-object"],
        [{"id": "", "question": "Where?"}],
        [{"id": "   ", "question": "Where?"}],
        [{"id": "target", "question": ""}],
        [{"id": "t" * 101, "question": "Where?"}],
        [{"id": "target", "question": "q" * 2001}],
        [
            {"id": "target", "question": "Where?"},
            {"id": "target", "question": "Again?"},
        ],
        [{"id": "target", "question": "Where?", "options": "cloud"}],
        [{"id": "target", "question": "Where?", "options": ["cloud"] * 51}],
        [{"id": "target", "question": "Where?", "options": ["", "cloud"]}],
        [{"id": "target", "question": "Where?", "options": [1, 2]}],
        [{"id": "target", "question": "Where?", "options": ["o" * 501]}],
        [{"id": "target", "question": "Where?", "required": "yes"}],
    ],
)
async def test_ask_user_rejects_malformed_questions(questions):
    with pytest.raises(ValueError):
        await ask_user(questions)


@pytest.mark.anyio
async def test_ask_user_normalizes_and_strips_valid_questions():
    request = await ask_user(
        [
            {
                "id": "  target  ",
                "question": "  Where to deploy?  ",
                "options": ["  cloud  ", "local"],
                "required": False,
            }
        ]
    )
    assert request.arguments == {
        "questions": [
            {
                "id": "target",
                "question": "Where to deploy?",
                "options": ["cloud", "local"],
                "required": False,
            }
        ]
    }


@pytest.mark.anyio
async def test_ask_user_defaults_required_true_and_omits_empty_options():
    request = await ask_user([{"id": "target", "question": "Where?"}])
    assert request.arguments == {
        "questions": [{"id": "target", "question": "Where?", "required": True}]
    }


@pytest.mark.parametrize(
    "pending_input",
    [
        {"questions": []},
        {"questions": [{"id": "q", "question": "Q"}, {"id": "q", "question": "Q2"}]},
        {"questions": [{"id": "q", "question": "Q", "required": "false"}]},
        {"questions": [{"id": "q", "question": "Q", "options": ["ok", 1]}]},
    ],
)
def test_validate_user_answers_rejects_malformed_persisted_questions(pending_input):
    with pytest.raises(ValueError, match="pending questions are invalid"):
        validate_user_answers(pending_input, {})


def test_validate_user_answers_accepts_complete_multi_question_answers():
    validate_user_answers(
        {
            "questions": [
                {"id": "target", "question": "Where?", "options": ["cloud"]},
                {"id": "note", "question": "Note?", "required": False},
            ]
        },
        {"target": "cloud"},
    )


def test_validate_user_answers_accepts_custom_text_for_option_questions():
    validate_user_answers(
        {
            "questions": [
                {"id": "target", "question": "Where?", "options": ["cloud", "local"]},
            ]
        },
        {"target": "self-hosted"},
    )


def test_validate_user_answers_allows_only_empty_explicit_skips():
    pending_input = {
        "questions": [
            {"id": "target", "question": "Where?", "options": ["cloud"]},
        ]
    }

    validate_user_answers(pending_input, {}, skipped=True)
    with pytest.raises(ValueError, match="skipped answers must be empty"):
        validate_user_answers(pending_input, {"target": "cloud"}, skipped=True)


def test_validate_user_answers_allows_empty_string_for_optional_options_question():
    pending_input = {
        "questions": [
            {
                "id": "optional_env",
                "question": "Deploy env?",
                "options": ["staging", "production"],
                "required": False,
            }
        ]
    }
    validate_user_answers(pending_input, {"optional_env": ""})
    validate_user_answers(pending_input, {"optional_env": "   "})
