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
    items: dict[str, Any] | None = Field(default=None, description="数组元素定义")
    default: Any = Field(default=None, description="默认值")


class ToolInfo(BaseModel):
    """工具信息"""

    name: str = Field(..., description="工具名称")
    description: str = Field(..., description="工具描述")
    parameters: list[ToolParameter] = Field(
        default_factory=list, description="参数列表"
    )
    parameters_schema: dict[str, Any] | None = Field(
        default=None, description="原始 JSON Schema 参数定义"
    )
    handler: Callable[..., Awaitable[Any]] | None = Field(default=None, exclude=True)

    class Config:
        arbitrary_types_allowed = True

    def to_openai_schema(self) -> dict:
        """转换为 OpenAI 工具格式"""
        parameters_schema = self.parameters_schema
        if parameters_schema is None:
            properties: dict[str, dict[str, Any]] = {}
            required: list[str] = []

            for param in self.parameters:
                prop: dict[str, Any] = {"type": param.type}
                if param.description:
                    prop["description"] = param.description
                if param.enum:
                    prop["enum"] = param.enum
                if param.items is not None:
                    prop["items"] = param.items
                elif param.type == "array":
                    prop["items"] = {}
                if param.default is not None:
                    prop["default"] = param.default
                properties[param.name] = prop

                if param.required:
                    required.append(param.name)

            parameters_schema = {
                "type": "object",
                "properties": properties,
                "required": required,
            }

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": parameters_schema,
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

        # 注册沙箱工具（需要 session_id）
        tool_registry.register_sandbox_tool("Bash", BashSandboxTool)
    """

    def __init__(self):
        self._tools: dict[str, ToolInfo] = {}
        self._sandbox_tools: dict[str, type] = {}
        self._sandbox_tool_infos: dict[str, ToolInfo] = {}

    def register_sandbox_tool(
        self,
        name: str,
        tool_class: type,
        *,
        tool_info: ToolInfo | None = None,
        aliases: list[str] | None = None,
    ) -> None:
        """注册内部沙箱工具类。"""
        self._sandbox_tools[name] = tool_class
        for alias in aliases or []:
            self._sandbox_tools[alias] = tool_class
        if tool_info is not None:
            self._sandbox_tool_infos[tool_info.name] = tool_info
        logger.debug(f"Registered sandbox tool: {name}")

    def get_sandbox_tool_class(self, name: str) -> type | None:
        """获取沙箱工具类"""
        return self._sandbox_tools.get(name)

    def get_sandbox_tool_infos(self, names: list[str] | None = None) -> list[ToolInfo]:
        """获取可暴露给模型的内部沙箱工具定义。"""
        if names is None:
            return list(self._sandbox_tool_infos.values())
        return [self._sandbox_tool_infos[name] for name in names if name in self._sandbox_tool_infos]

    def to_openai_sandbox_tools(self, names: list[str] | None = None) -> list[dict]:
        """转换内部沙箱工具为 OpenAI 工具格式。"""
        return [tool.to_openai_schema() for tool in self.get_sandbox_tool_infos(names)]

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
        **context: Any,
    ) -> Any:
        """
        执行工具

        Args:
            name: 工具名称
            arguments: 参数字典
            credentials: 凭证信息（可选）
            session_id: 会话 ID（用于沙箱工具）
            allowed_commands: 允许的命令列表（用于 Bash 工具）

        Returns:
            工具执行结果

        Raises:
            ValueError: 工具不存在或没有处理函数
        """
        # 1. 优先检查沙箱工具
        sandbox_class = self.get_sandbox_tool_class(name)
        if sandbox_class:
            session_id = context.pop("session_id", None)
            allowed_commands = context.pop("allowed_commands", None)
            agent = context.get("agent")
            tool_instance = sandbox_class(
                session_id=session_id,
                allowed_commands=allowed_commands,
                agent_id=str(agent.id) if agent is not None else None,
                team_id=str(agent.team_id) if agent is not None and agent.team_id else None,
            )
            return await tool_instance.execute(**arguments)

        # 2. 回退到普通工具
        tool = self._tools.get(name)
        if not tool:
            raise ValueError(f"Tool not found: {name}")
        return await self.execute_tool_info(
            tool,
            arguments,
            credentials=credentials,
            **context,
        )

    async def execute_tool_info(
        self,
        tool: ToolInfo,
        arguments: dict[str, Any],
        credentials: dict[str, str] | None = None,
        **context: Any,
    ) -> Any:
        if not tool.handler:
            raise ValueError(f"Tool has no handler: {tool.name}")

        import inspect

        sig = inspect.signature(tool.handler)
        handler_kwargs = dict(arguments)

        if "credentials" in sig.parameters:
            handler_kwargs["credentials"] = credentials

        for key, value in context.items():
            if key in sig.parameters:
                handler_kwargs[key] = value

        return await tool.handler(**handler_kwargs)

    def clear(self) -> None:
        """清空所有注册的工具"""
        self._tools.clear()
        self._sandbox_tools.clear()
        self._sandbox_tool_infos.clear()


# 全局工具注册表
tool_registry = ToolRegistry()
