"""User-facing question tool for Agent runs."""

from __future__ import annotations

from typing import Any

from ..interaction import ToolInteractionRequest
from ..registry import ToolInfo, ToolConcurrency, tool_registry


MAX_QUESTIONS = 20
MAX_QUESTION_ID_LENGTH = 100
MAX_QUESTION_LENGTH = 2000
MAX_OPTION_LENGTH = 500
MAX_OPTIONS = 50


def _normalize_questions(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value or len(value) > MAX_QUESTIONS:
        raise ValueError("questions must contain between 1 and 20 items")

    normalized: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("each question must be an object")

        question_id = item.get("id")
        question = item.get("question")
        if not isinstance(question_id, str) or not question_id.strip():
            raise ValueError("each question requires a non-empty id")
        if not isinstance(question, str) or not question.strip():
            raise ValueError("each question requires non-empty text")

        question_id = question_id.strip()
        question = question.strip()
        if len(question_id) > MAX_QUESTION_ID_LENGTH:
            raise ValueError("question id is too long")
        if len(question) > MAX_QUESTION_LENGTH:
            raise ValueError("question text is too long")
        if question_id in seen_ids:
            raise ValueError("question ids must be unique")
        seen_ids.add(question_id)

        options = item.get("options")
        if options is not None:
            if not isinstance(options, list) or len(options) > MAX_OPTIONS:
                raise ValueError("question options are invalid")
            normalized_options: list[str] = []
            for option in options:
                if not isinstance(option, str) or not option.strip():
                    raise ValueError("question options must be non-empty strings")
                option = option.strip()
                if len(option) > MAX_OPTION_LENGTH:
                    raise ValueError("question option is too long")
                normalized_options.append(option)
            options = normalized_options

        required = item.get("required", True)
        if not isinstance(required, bool):
            raise ValueError("question required must be a boolean")

        normalized_item: dict[str, Any] = {
            "id": question_id,
            "question": question,
            "required": required,
        }
        if options is not None:
            normalized_item["options"] = options
        normalized.append(normalized_item)

    return normalized


async def ask_user(questions: Any) -> ToolInteractionRequest:
    """Pause the Agent run and ask the user one structured set of questions."""
    return ToolInteractionRequest(
        tool_name="ask_user",
        arguments={"questions": _normalize_questions(questions)},
    )


def register_ask_user_tool() -> None:
    """Register the model-callable user interaction tool."""
    tool_registry.register_tool(
        ToolInfo(
            name="ask_user",
            description="Ask the user one or more questions before continuing.",
            parameters_schema={
                "type": "object",
                "properties": {
                    "questions": {
                        "type": "array",
                        "description": "Questions to present together in one form.",
                        "minItems": 1,
                        "maxItems": MAX_QUESTIONS,
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "question": {"type": "string"},
                                "options": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                                "required": {"type": "boolean", "default": True},
                            },
                            "required": ["id", "question"],
                            "additionalProperties": False,
                        },
                    }
                },
                "required": ["questions"],
                "additionalProperties": False,
            },
            handler=ask_user,
            concurrency=ToolConcurrency.EXCLUSIVE,
        )
    )


__all__ = ["ask_user", "register_ask_user_tool"]
