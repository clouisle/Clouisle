from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.api.v1.endpoints.chat_helpers import (
    config,
    message_builder,
    model_utils,
    tool_utils,
    version_utils,
)
from app.llm.types import ContentType, MessageRole


class Query:
    def __init__(self, result):
        self.result = result

    def order_by(self, *_args):
        return self

    def prefetch_related(self, *_args):
        return self

    async def all(self):
        return self.result

    async def first(self):
        return self.result

    async def count(self):
        return self.result


def test_config_language_and_streaming_defaults(monkeypatch):
    assert config.build_system_prompt_with_language("Be helpful", "en") == (
        "Be helpful\n\nPlease reply in English."
    )
    assert (
        config.build_system_prompt_with_language("Be helpful", "unknown")
        == "Be helpful"
    )

    monkeypatch.setattr(config.settings, "STREAM_GLOBAL_TIMEOUT", 10)
    monkeypatch.setattr(config.settings, "STREAM_GLOBAL_TIMEOUT_WITH_TOOLS", 20)
    monkeypatch.setattr(config.settings, "STREAM_HEARTBEAT_INTERVAL", 3)
    monkeypatch.setattr(config.settings, "STREAM_IDLE_TIMEOUT", 4)
    monkeypatch.setattr(config.settings, "STREAM_TOOL_TIMEOUT_HTTP", 5)
    monkeypatch.setattr(config.settings, "STREAM_TOOL_TIMEOUT_CODE", 6)
    monkeypatch.setattr(config.settings, "STREAM_TOOL_TIMEOUT_MCP", 7)
    monkeypatch.setattr(config.settings, "STREAM_TOOL_TIMEOUT_DOWNLOAD", 8)
    agent = SimpleNamespace(
        tools_config=[{"name": "read"}],
        enable_memory=False,
        enable_image_generation=False,
        enable_video_generation=False,
        streaming_config={"idle_timeout": 40, "tool_timeouts": {"code": 60}},
    )

    assert config.get_streaming_config(agent) == {
        "global_timeout": 20,
        "heartbeat_interval": 3,
        "idle_timeout": 40,
        "tool_timeouts": {"http": 5, "code": 60, "mcp": 7, "download": 8},
    }


@pytest.mark.anyio
async def test_build_messages_preserves_history_and_prefers_image_urls(monkeypatch):
    history = [
        SimpleNamespace(
            role=SimpleNamespace(value="assistant"),
            content="Earlier answer",
            tool_calls=None,
            tool_call_id=None,
        )
    ]
    monkeypatch.setattr(
        message_builder.ConversationMessage,
        "filter",
        lambda **_kwargs: Query(history),
    )

    messages = await message_builder.build_messages(
        SimpleNamespace(system_prompt="Be concise"),
        SimpleNamespace(id=uuid4()),
        "What is shown?",
        file_content="ignored when images are supplied",
        file_urls=[{"url": "https://example.test/image.png"}],
        user_locale="en",
    )

    assert [message.role for message in messages] == [
        MessageRole.SYSTEM,
        MessageRole.ASSISTANT,
        MessageRole.USER,
    ]
    assert messages[0].content == "Be concise\n\nPlease reply in English."
    assert messages[1].content == "Earlier answer"
    assert [part.type for part in messages[2].content] == [
        ContentType.TEXT,
        ContentType.IMAGE,
    ]
    assert messages[2].content[1].image.url == "https://example.test/image.png"


@pytest.mark.anyio
async def test_build_messages_rejects_image_without_url(monkeypatch):
    monkeypatch.setattr(
        message_builder.ConversationMessage,
        "filter",
        lambda **_kwargs: Query([]),
    )

    with pytest.raises(KeyError, match="url"):
        await message_builder.build_messages(
            SimpleNamespace(system_prompt=None),
            SimpleNamespace(id=uuid4()),
            "Describe this",
            file_urls=[{"name": "missing-url.png"}],
        )


@pytest.mark.anyio
async def test_model_utils_handle_unset_missing_and_capable_models(monkeypatch):
    no_model_agent = SimpleNamespace(model_id=None)
    assert await model_utils.get_model_identifier(no_model_agent) is None
    assert await model_utils.get_model_capabilities(no_model_agent) == {
        "supports_vision": False
    }

    model = SimpleNamespace(
        provider="acme", model_id="vision-1", capabilities={"vision": 1}
    )
    monkeypatch.setattr(
        model_utils.TeamModel,
        "filter",
        lambda **_kwargs: Query(SimpleNamespace(model=model)),
    )
    agent = SimpleNamespace(model_id=uuid4())

    assert await model_utils.get_model_identifier(agent) == "acme/vision-1"
    assert await model_utils.get_model_capabilities(agent) == {"supports_vision": True}

    monkeypatch.setattr(model_utils.TeamModel, "filter", lambda **_kwargs: Query(None))
    assert await model_utils.get_model_identifier(agent) is None
    assert await model_utils.get_model_capabilities(agent) == {"supports_vision": False}


@pytest.mark.anyio
async def test_tool_utils_add_skill_sandbox_tools_without_duplicates(monkeypatch):
    skill = SimpleNamespace(
        id=uuid4(),
        name="research",
        description="Research a topic",
        input_schema={"type": "object"},
    )
    monkeypatch.setattr(
        tool_utils.SkillService,
        "get_agent_skills",
        lambda *_args, **_kwargs: async_result([(skill, {})]),
    )
    monkeypatch.setattr(
        tool_utils.SkillService,
        "build_tool_name",
        lambda _skill: "skill_research",
    )
    sandbox_tools = [
        SimpleNamespace(name="read", description="Read", parameters_schema={}),
        SimpleNamespace(
            name="skill_research", description="Duplicate", parameters_schema={}
        ),
    ]
    monkeypatch.setattr(
        tool_utils.tool_registry,
        "get_sandbox_tool_infos",
        lambda names: sandbox_tools if names == ["read", "write", "bash"] else [],
    )

    tools = await tool_utils.get_agent_tools(SimpleNamespace(tools_config=[]))

    assert [tool["name"] for tool in tools] == ["skill_research", "read"]
    assert tools[0]["type"] == "skill"
    assert tools[1]["type"] == "builtin"


async def async_result(value):
    return value


@pytest.mark.anyio
async def test_version_utils_sort_versions_and_count_root(monkeypatch):
    root_id = uuid4()
    now = datetime.now(UTC)
    root = SimpleNamespace(
        id=root_id,
        parent_id=None,
        version_number=1,
        is_active=False,
        content="first",
        created_at=now,
    )
    child = SimpleNamespace(
        id=uuid4(),
        parent_id=root_id,
        version_number=2,
        is_active=True,
        content="second",
        created_at=now,
    )

    def filter_messages(**kwargs):
        if "id" in kwargs:
            return Query([root])
        return Query([child])

    monkeypatch.setattr(version_utils.Message, "filter", filter_messages)

    versions = await version_utils.get_message_versions(child)
    assert [(version.version_number, version.content) for version in versions] == [
        (1, "first"),
        (2, "second"),
    ]

    monkeypatch.setattr(version_utils.Message, "filter", lambda **_kwargs: Query(1))
    assert await version_utils.get_version_count(child) == 2
