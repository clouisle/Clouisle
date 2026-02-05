"""
工具注册表

提供统一的工具注册和管理功能。
"""

import logging
from typing import Any, Callable, Awaitable
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ToolParameter(BaseModel):
    """工具参数定义"""

    name: str = Field(..., description="参数名")
    type: str = Field(
        ..., description="参数类型 (string, integer, number, boolean, array, object)"
    )
    description: str | None = Field(default=None, description="参数描述")
    required: bool = Field(default=False, description="是否必填")
    enum: list[str] | None = Field(default=None, description="枚举值")
    default: Any = Field(default=None, description="默认值")


class ToolInfo(BaseModel):
    """工具信息"""

    name: str = Field(..., description="工具名称")
    description: str = Field(..., description="工具描述")
    parameters: list[ToolParameter] = Field(
        default_factory=list, description="参数列表"
    )
    handler: Callable[..., Awaitable[Any]] | None = Field(default=None, exclude=True)

    class Config:
        arbitrary_types_allowed = True

    def to_openai_schema(self) -> dict:
        """转换为 OpenAI 工具格式"""
        properties: dict[str, dict[str, str | list[str]]] = {}
        required: list[str] = []

        for param in self.parameters:
            prop: dict[str, str | list[str]] = {"type": param.type}
            if param.description:
                prop["description"] = param.description
            if param.enum:
                prop["enum"] = param.enum
            properties[param.name] = prop

            if param.required:
                required.append(param.name)

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }

    def to_langchain_schema(self) -> dict:
        """转换为 LangChain 工具格式"""
        # LangChain 使用与 OpenAI 相同的格式
        return self.to_openai_schema()


class ToolRegistry:
    """
    工具注册表

    用于注册和管理可供 LLM 调用的工具。

    使用示例:
        from app.llm.tools import tool_registry

        # 注册工具
        @tool_registry.register(
            name="get_weather",
            description="获取指定城市的天气",
            parameters=[
                ToolParameter(name="city", type="string", description="城市名", required=True),
            ]
        )
        async def get_weather(city: str) -> str:
            return f"{city} 的天气是晴天"

        # 获取所有工具
        tools = tool_registry.get_all_tools()

        # 执行工具
        result = await tool_registry.execute("get_weather", {"city": "北京"})
    """

    def __init__(self):
        self._tools: dict[str, ToolInfo] = {}

    def register(
        self,
        name: str,
        description: str,
        parameters: list[ToolParameter] | None = None,
    ) -> Callable:
        """
        注册工具的装饰器

        Args:
            name: 工具名称
            description: 工具描述
            parameters: 参数列表

        Returns:
            装饰器函数
        """

        def decorator(func: Callable[..., Awaitable[Any]]) -> Callable:
            tool_info = ToolInfo(
                name=name,
                description=description,
                parameters=parameters or [],
                handler=func,
            )
            self._tools[name] = tool_info
            logger.debug(f"Registered tool: {name}")
            return func

        return decorator

    def register_tool(self, tool_info: ToolInfo) -> None:
        """
        直接注册工具

        Args:
            tool_info: 工具信息
        """
        self._tools[tool_info.name] = tool_info
        logger.debug(f"Registered tool: {tool_info.name}")

    def unregister(self, name: str) -> None:
        """
        注销工具

        Args:
            name: 工具名称
        """
        if name in self._tools:
            del self._tools[name]
            logger.debug(f"Unregistered tool: {name}")

    def get_tool(self, name: str) -> ToolInfo | None:
        """
        获取工具

        Args:
            name: 工具名称

        Returns:
            工具信息或 None
        """
        return self._tools.get(name)

    def get_all_tools(self) -> list[ToolInfo]:
        """
        获取所有注册的工具

        Returns:
            工具列表
        """
        return list(self._tools.values())

    def get_tools_by_names(self, names: list[str]) -> list[ToolInfo]:
        """
        根据名称获取多个工具

        Args:
            names: 工具名称列表

        Returns:
            工具列表
        """
        return [self._tools[name] for name in names if name in self._tools]

    def to_openai_tools(self, names: list[str] | None = None) -> list[dict]:
        """
        转换为 OpenAI 工具格式

        Args:
            names: 要包含的工具名称，None 表示全部

        Returns:
            OpenAI 工具定义列表
        """
        tools = self.get_tools_by_names(names) if names else self.get_all_tools()
        return [tool.to_openai_schema() for tool in tools]

    def to_langchain_tools(self, names: list[str] | None = None) -> list[dict]:
        """
        转换为 LangChain 工具格式

        Args:
            names: 要包含的工具名称

        Returns:
            LangChain 工具定义列表
        """
        tools = self.get_tools_by_names(names) if names else self.get_all_tools()
        return [tool.to_langchain_schema() for tool in tools]

    async def execute(
        self,
        name: str,
        arguments: dict[str, Any],
        credentials: dict[str, str] | None = None,
    ) -> Any:
        """
        执行工具

        Args:
            name: 工具名称
            arguments: 参数字典
            credentials: 凭证信息（可选）

        Returns:
            工具执行结果

        Raises:
            ValueError: 工具不存在或没有处理函数
        """
        tool = self._tools.get(name)
        if not tool:
            raise ValueError(f"Tool not found: {name}")
        if not tool.handler:
            raise ValueError(f"Tool has no handler: {name}")

        # 如果工具函数支持 credentials 参数，则传递
        import inspect

        sig = inspect.signature(tool.handler)
        if "credentials" in sig.parameters:
            return await tool.handler(**arguments, credentials=credentials)
        else:
            return await tool.handler(**arguments)

    def clear(self) -> None:
        """清空所有注册的工具"""
        self._tools.clear()


# 全局工具注册表
tool_registry = ToolRegistry()
