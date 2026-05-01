from app.api.v1.endpoints.tools import get_builtin_tools
from app.llm.tools.builtin import register_all_builtin_tools


def _get_tool(tools, name: str):
    for tool in tools:
        if tool.name == name:
            return tool
    raise AssertionError(f"tool not found: {name}")


def test_get_builtin_tools_uses_backend_translations_for_sandbox_display_names():
    register_all_builtin_tools()

    zh_tools = get_builtin_tools("zh")
    en_tools = get_builtin_tools("en")

    assert _get_tool(zh_tools, "bash").display_name == "执行命令"
    assert _get_tool(zh_tools, "artifact").display_name == "生成下载链接"
    assert _get_tool(en_tools, "bash").display_name == "Run Command"
    assert _get_tool(en_tools, "artifact").display_name == "Create Download Link"


def test_get_builtin_tools_uses_backend_translations_for_non_sandbox_descriptions():
    register_all_builtin_tools()

    en_tools = get_builtin_tools("en")

    web_search = _get_tool(en_tools, "web_search")
    assert web_search.description == (
        "Search the web. Use a search engine to find relevant information when you need up-to-date facts or research a topic."
    )
    assert web_search.parameters[0].description == "Search keywords or question"
    assert web_search.parameters[1].description == "Number of results. Default 5, max 10."
