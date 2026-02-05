"""
流式工具调用累加器

处理流式响应中的工具调用增量拼接。
"""

import json
from typing import Any

from app.llm.types import ToolCall, FunctionCall


class ToolCallAccumulator:
    """
    流式工具调用累加器

    在流式响应中，工具调用是分块返回的：
    - 第一个 chunk 包含 id 和 function.name
    - 后续 chunks 包含 function.arguments 的增量

    此类负责累加这些增量，并在完成时返回完整的工具调用列表。
    """

    def __init__(self):
        # index -> partial tool call
        self._tool_calls: dict[int, dict[str, Any]] = {}

    def accumulate(self, delta: Any) -> None:
        """
        累加工具调用增量

        Args:
            delta: 包含 tool_calls 的 delta 对象
        """
        tool_calls = getattr(delta, "tool_calls", None)
        if not tool_calls:
            return

        for tc_delta in tool_calls:
            idx = getattr(tc_delta, "index", 0)
            if idx not in self._tool_calls:
                self._tool_calls[idx] = {
                    "id": "",
                    "type": "function",
                    "function": {"name": "", "arguments": ""},
                }

            # 累加 id
            tc_id = getattr(tc_delta, "id", None)
            if tc_id:
                self._tool_calls[idx]["id"] = tc_id

            # 累加 type
            tc_type = getattr(tc_delta, "type", None)
            if tc_type:
                self._tool_calls[idx]["type"] = tc_type

            # 累加 function
            tc_function = getattr(tc_delta, "function", None)
            if tc_function:
                func_name = getattr(tc_function, "name", None)
                if func_name:
                    self._tool_calls[idx]["function"]["name"] += func_name

                func_args = getattr(tc_function, "arguments", None)
                if func_args:
                    self._tool_calls[idx]["function"]["arguments"] += func_args

    def accumulate_dict(self, tool_calls: list[dict]) -> None:
        """
        累加字典格式的工具调用增量

        Args:
            tool_calls: 工具调用增量列表
        """
        for tc_delta in tool_calls:
            idx = tc_delta.get("index", 0)
            if idx not in self._tool_calls:
                self._tool_calls[idx] = {
                    "id": "",
                    "type": "function",
                    "function": {"name": "", "arguments": ""},
                }

            if tc_delta.get("id"):
                self._tool_calls[idx]["id"] = tc_delta["id"]

            if tc_delta.get("type"):
                self._tool_calls[idx]["type"] = tc_delta["type"]

            function = tc_delta.get("function", {})
            if function.get("name"):
                self._tool_calls[idx]["function"]["name"] += function["name"]
            if function.get("arguments"):
                self._tool_calls[idx]["function"]["arguments"] += function["arguments"]

    def has_tool_calls(self) -> bool:
        """是否有工具调用"""
        return len(self._tool_calls) > 0

    def finalize(self) -> list[ToolCall]:
        """
        返回完整的工具调用列表

        Returns:
            ToolCall 对象列表
        """
        import uuid

        result = []
        for tc in self._tool_calls.values():
            result.append(
                ToolCall(
                    id=tc["id"] or str(uuid.uuid4()),
                    type=tc["type"],
                    function=FunctionCall(
                        name=tc["function"]["name"],
                        arguments=tc["function"]["arguments"] or "{}",
                    ),
                )
            )
        return result

    def clear(self) -> None:
        """清空累加器"""
        self._tool_calls.clear()


def extract_tool_calls_from_content(content: Any) -> list[ToolCall] | None:
    """
    从 content blocks 提取工具调用

    用于 Anthropic 风格的 tool_use content block。

    Args:
        content: 响应内容，可能包含 tool_use blocks

    Returns:
        ToolCall 列表，如果没有则返回 None
    """
    import uuid

    items: list[Any] = []
    if isinstance(content, list):
        items = content
    elif isinstance(content, dict):
        items = [content]
    else:
        return None

    tool_calls: list[ToolCall] = []
    for item in items:
        if not isinstance(item, dict):
            # 尝试作为对象处理
            if hasattr(item, "type") and getattr(item, "type", None) == "tool_use":
                name = getattr(item, "name", "") or ""
                tool_id = getattr(item, "id", None) or str(uuid.uuid4())
                tool_input = getattr(item, "input", {}) or {}
                if isinstance(tool_input, dict):
                    tool_input = json.dumps(tool_input)
                tool_calls.append(
                    ToolCall(
                        id=tool_id,
                        type="function",
                        function=FunctionCall(
                            name=name,
                            arguments=tool_input or "{}",
                        ),
                    )
                )
            continue

        if item.get("type") != "tool_use":
            continue

        name = item.get("name") or ""
        tool_id = item.get("id") or str(uuid.uuid4())
        tool_input = item.get("input") or {}
        if isinstance(tool_input, dict):
            tool_input = json.dumps(tool_input)

        tool_calls.append(
            ToolCall(
                id=tool_id,
                type="function",
                function=FunctionCall(
                    name=name,
                    arguments=tool_input or "{}",
                ),
            )
        )

    return tool_calls or None
