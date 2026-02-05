"""
统一的思考内容提取器

处理各服务商不同格式的 thinking/reasoning 内容提取。
"""

from typing import Any


class ThinkingExtractor:
    """
    统一的思考内容提取器

    各服务商的 thinking 字段位置和格式不同：
    - OpenAI o1/o3: response.reasoning_content
    - DeepSeek R1: delta.reasoning_content
    - Claude: content blocks with type="thinking"
    - Gemini: parts with thought=True
    """

    # 各服务商可能的 thinking 字段名
    THINKING_FIELDS = [
        "reasoning_content",
        "reasoning",
        "reasoning_text",
        "reasoning_summary",
        "thinking",
        "thinking_content",
        "thought",
        "thoughts",
        "thought_process",
        "analysis",
        "model_reasoning",
        "chain_of_thought",
        "cot",
    ]

    @classmethod
    def extract(cls, *sources: Any) -> str | None:
        """
        从多个来源提取思考内容

        Args:
            *sources: 可能包含思考内容的对象

        Returns:
            提取到的思考内容，如果没有则返回 None
        """
        for source in sources:
            result = cls._extract_from_source(source)
            if result:
                return result
        return None

    @classmethod
    def _extract_from_source(cls, source: Any) -> str | None:
        """从单个来源提取思考内容"""
        if source is None:
            return None

        # 字符串直接返回
        if isinstance(source, str):
            trimmed = source.strip()
            return trimmed or None

        # 列表：可能是 content blocks
        if isinstance(source, list):
            return cls._extract_from_blocks(source)

        # 字典：检查各种字段
        if isinstance(source, dict):
            return cls._extract_from_dict(source)

        # 对象：检查属性
        return cls._extract_from_object(source)

    @classmethod
    def _extract_from_blocks(cls, blocks: list) -> str | None:
        """
        从 content blocks 提取思考内容

        支持格式：
        - Anthropic: [{"type": "thinking", "thinking": "..."}]
        - Gemini: [{"thought": True, "text": "..."}]
        """
        thinking_parts: list[str] = []

        for block in blocks:
            if isinstance(block, dict):
                block_type = block.get("type")
                # Anthropic style: type="thinking"
                if block_type in ("thinking", "thought", "reasoning", "analysis"):
                    text = (
                        block.get("thinking")
                        or block.get("text")
                        or block.get("content")
                    )
                    if text:
                        thinking_parts.append(str(text))
                # Gemini style: thought=True
                elif block.get("thought") is True or block.get("is_thought") is True:
                    text = block.get("text") or block.get("content")
                    if text:
                        thinking_parts.append(str(text))
            elif hasattr(block, "type"):
                # 对象形式的 block
                block_type = getattr(block, "type", None)
                if block_type in ("thinking", "thought", "reasoning", "analysis"):
                    text = (
                        getattr(block, "thinking", None)
                        or getattr(block, "text", None)
                        or getattr(block, "content", None)
                    )
                    if text:
                        thinking_parts.append(str(text))
                elif getattr(block, "thought", False) or getattr(
                    block, "is_thought", False
                ):
                    text = getattr(block, "text", None) or getattr(
                        block, "content", None
                    )
                    if text:
                        thinking_parts.append(str(text))

        if thinking_parts:
            return "".join(thinking_parts).strip() or None
        return None

    @classmethod
    def _extract_from_dict(cls, data: dict) -> str | None:
        """从字典提取思考内容"""
        # 直接检查 thinking 字段
        for field in cls.THINKING_FIELDS:
            if field in data:
                result = cls._extract_from_source(data[field])
                if result:
                    return result

        # 检查嵌套的 delta
        delta = data.get("delta")
        if isinstance(delta, dict):
            for field in cls.THINKING_FIELDS:
                if field in delta:
                    result = cls._extract_from_source(delta[field])
                    if result:
                        return result

        # 检查 content blocks
        content = data.get("content")
        if isinstance(content, list):
            result = cls._extract_from_blocks(content)
            if result:
                return result

        return None

    @classmethod
    def _extract_from_object(cls, obj: Any) -> str | None:
        """从对象属性提取思考内容"""
        # 检查直接属性
        for field in cls.THINKING_FIELDS:
            if hasattr(obj, field):
                result = cls._extract_from_source(getattr(obj, field))
                if result:
                    return result

        # 检查 additional_kwargs
        additional = getattr(obj, "additional_kwargs", None)
        if additional:
            result = cls._extract_from_source(additional)
            if result:
                return result

        # 检查 model_extra
        model_extra = getattr(obj, "model_extra", None)
        if model_extra:
            result = cls._extract_from_source(model_extra)
            if result:
                return result

        # 检查 response_metadata
        response_metadata = getattr(obj, "response_metadata", None)
        if response_metadata:
            result = cls._extract_from_source(response_metadata)
            if result:
                return result

        return None


class ContentExtractor:
    """
    内容提取器

    从各种格式的响应中提取纯文本内容和思考内容。
    """

    @classmethod
    def extract(cls, content: Any) -> tuple[str | None, str | None]:
        """
        提取内容和思考

        Args:
            content: 响应内容，可能是字符串或 content blocks

        Returns:
            (text_content, thinking_content) 元组
        """
        if isinstance(content, str):
            return content, None

        if not isinstance(content, list):
            return None, None

        text_parts: list[str] = []
        thinking_parts: list[str] = []

        for item in content:
            item_type = cls._get_type(item)
            item_text = cls._get_text(item)

            if not item_text:
                continue

            if cls._is_thinking(item, item_type):
                thinking_parts.append(item_text)
            else:
                text_parts.append(item_text)

        text = "".join(text_parts).strip() or None
        thinking = "".join(thinking_parts).strip() or None

        return text, thinking

    @classmethod
    def _get_type(cls, item: Any) -> str | None:
        """获取 block 类型"""
        if isinstance(item, dict):
            return item.get("type")
        return getattr(item, "type", None)

    @classmethod
    def _get_text(cls, item: Any) -> str | None:
        """获取 block 文本"""
        if isinstance(item, dict):
            return item.get("text") or item.get("content") or item.get("thinking")
        return (
            getattr(item, "text", None)
            or getattr(item, "content", None)
            or getattr(item, "thinking", None)
        )

    @classmethod
    def _is_thinking(cls, item: Any, item_type: str | None) -> bool:
        """判断是否是思考 block"""
        # 检查 thought 标记
        if isinstance(item, dict):
            if item.get("thought") is True or item.get("is_thought") is True:
                return True
        elif getattr(item, "thought", False) or getattr(item, "is_thought", False):
            return True

        # 检查类型
        if item_type in ("thinking", "thought", "reasoning", "analysis"):
            return True

        return False
