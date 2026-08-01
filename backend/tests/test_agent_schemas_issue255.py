from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.agent import (
    AgentCreate,
    AgentKnowledgeBaseConfig,
    AgentListOut,
    AgentOut,
    AgentPublicOut,
    AgentUpdate,
    ChatRequest,
    ChatResponse,
    ContextCompressionConfig,
    ConversationCreate,
    ConversationOut,
    ConversationUpdate,
    ConversationWithMessages,
    CreatorInfo,
    EditMessageRequest,
    EmbedAgentInfo,
    FileContent,
    FileUploadConfig,
    FileUrl,
    HistoryMessage,
    HistoryToolCall,
    ImageContent,
    ImageGenerationConfig,
    KnowledgeBaseInfo,
    MemoryConfig,
    MessageOut,
    MessageRoundStep,
    MessageVersion,
    ModelInfo,
    RegenerateRequest,
    SwitchVersionRequest,
    TeamInfo,
    ToolConfig,
    VariableDefinition,
    VideoGenerationConfig,
)


def test_agent_create_defaults_and_nested_mapping_validation():
    team_id = uuid4()
    knowledge_base_id = uuid4()

    agent = AgentCreate.model_validate(
        {
            "name": "Researcher",
            "team_id": str(team_id),
            "tools_config": [{"type": "builtin", "name": "search"}],
            "file_upload_config": {"parser": {"type": "builtin"}},
            "memory_config": {"importance_threshold": "high"},
            "context_compression_config": {"compaction_policy": "hard_budget_only"},
            "image_generation_config": {"allowed_providers": ["image-provider"]},
            "video_generation_config": {"default_duration": 8},
            "knowledge_base_configs": [{"knowledge_base_id": str(knowledge_base_id)}],
            "variables": [{"name": "topic", "required": True}],
        }
    )

    assert agent.team_id == team_id
    assert agent.max_iterations == 5
    assert agent.hide_tool_calls is False
    assert agent.hide_token_stats is False
    assert agent.hide_reasoning is False
    assert agent.rag_mode == "agentic"
    assert agent.visibility == "team"
    assert agent.tools_config == [ToolConfig(type="builtin", name="search")]
    assert agent.file_upload_config.max_files == 5
    assert agent.memory_config.max_memories_per_retrieval == 10
    assert agent.context_compression_config.compaction_policy == "hard_budget_only"
    assert agent.image_generation_config.default_width == 1024
    assert agent.video_generation_config.default_duration == 8
    assert agent.knowledge_base_configs[0].knowledge_base_id == knowledge_base_id
    assert agent.variables[0].type == "text"


def test_mutable_defaults_are_not_shared():
    first = AgentCreate(name="First", team_id=uuid4())
    second = AgentCreate(name="Second", team_id=uuid4())

    first.tools_config.append(ToolConfig(type="builtin"))
    first.suggested_questions.append("Question")

    assert second.tools_config == []
    assert second.suggested_questions == []
    assert ConversationCreate().variables == {}
    assert RegenerateRequest().variables == {}


@pytest.mark.parametrize(
    ("schema", "payload"),
    [
        (MemoryConfig, {"max_memories_per_retrieval": 0}),
        (MemoryConfig, {"importance_threshold": "urgent"}),
        (ContextCompressionConfig, {"recent_raw_turns": 0}),
        (ContextCompressionConfig, {"warning_ratio": 1.1}),
        (ContextCompressionConfig, {"compaction_policy": "always"}),
        (ContextCompressionConfig, {"retention_strategy": "oldest_first"}),
        (ImageGenerationConfig, {"default_width": 255}),
        (ImageGenerationConfig, {"max_images": 11}),
        (VideoGenerationConfig, {"default_duration": 31}),
        (VideoGenerationConfig, {"poll_interval_ms": 499}),
        (FileUploadConfig, {"max_file_size": 1023}),
        (FileUploadConfig, {"max_files": 11}),
        (VariableDefinition, {"name": ""}),
        (VariableDefinition, {"name": "valid", "maxLength": 0}),
        (
            AgentKnowledgeBaseConfig,
            {"knowledge_base_id": uuid4(), "retrieval_top_k": 0},
        ),
        (
            AgentKnowledgeBaseConfig,
            {"knowledge_base_id": uuid4(), "score_threshold": 1.1},
        ),
        (
            AgentKnowledgeBaseConfig,
            {"knowledge_base_id": uuid4(), "search_mode": "invalid"},
        ),
        (AgentCreate, {"name": "", "team_id": uuid4()}),
        (AgentCreate, {"name": "Agent", "team_id": uuid4(), "max_iterations": 201}),
        (AgentUpdate, {"name": ""}),
        (ConversationUpdate, {"title": ""}),
        (ChatRequest, {"message": ""}),
        (
            FileContent,
            {"filename": "a", "content": "", "mime_type": "text/plain", "size": -1},
        ),
        (
            FileUrl,
            {
                "filename": "a",
                "url": "https://example.test/a",
                "size": -1,
                "mime_type": "text/plain",
            },
        ),
    ],
)
def test_schema_rejects_invalid_input(schema, payload):
    with pytest.raises(ValidationError):
        schema.model_validate(payload)


def test_creator_info_handles_users_and_deleted_users():
    user_id = uuid4()
    user = SimpleNamespace(id=user_id, username="alice", avatar_url="avatar.png")

    assert CreatorInfo.from_user(user) == CreatorInfo(
        id=user_id, username="alice", avatar_url="avatar.png"
    )
    assert CreatorInfo.from_user(None) == CreatorInfo(
        id=None, username="Deleted User", avatar_url=None
    )
    assert CreatorInfo.model_validate(user).username == "alice"


def test_agent_output_converts_orm_attributes_and_serializes_nested_types():
    now = datetime.now(UTC)
    team = SimpleNamespace(id=uuid4(), name="Platform", avatar_url=None)
    model = SimpleNamespace(
        id=uuid4(), name="Large", provider="provider", model_id="model-v1"
    )
    creator = SimpleNamespace(id=uuid4(), username="alice", avatar_url=None)
    knowledge_base = SimpleNamespace(
        id=uuid4(),
        name="Docs",
        description=None,
        icon=None,
        document_count=3,
    )
    source = SimpleNamespace(
        id=uuid4(),
        name="Assistant",
        description=None,
        icon=None,
        team=team,
        model=model,
        variables=[{"name": "query"}],
        knowledge_bases=[
            SimpleNamespace(
                id=uuid4(),
                knowledge_base=knowledge_base,
                retrieval_top_k=5,
                score_threshold=0.3,
                search_mode="hybrid",
            )
        ],
        status="published",
        visibility="team",
        created_by=creator,
        created_at=now,
        updated_at=now,
    )

    output = AgentOut.model_validate(source)
    serialized = output.model_dump(mode="json")

    assert output.team == TeamInfo.model_validate(team)
    assert output.model == ModelInfo.model_validate(model)
    assert output.knowledge_bases[0].knowledge_base == KnowledgeBaseInfo.model_validate(
        knowledge_base
    )
    assert serialized["id"] == str(source.id)
    assert serialized["created_at"] == now.isoformat().replace("+00:00", "Z")
    assert serialized["variables"][0]["name"] == "query"


def test_public_embed_and_list_outputs_accept_orm_objects():
    now = datetime.now(UTC)
    common = {
        "id": uuid4(),
        "name": "Agent",
        "description": None,
        "icon": None,
        "avatar_url": None,
    }
    public = AgentPublicOut.model_validate(SimpleNamespace(**common))
    embed = EmbedAgentInfo.model_validate(SimpleNamespace(**common))
    listed = AgentListOut.model_validate(
        SimpleNamespace(
            **common,
            team=SimpleNamespace(id=uuid4(), name="Team", avatar_url=None),
            model=None,
            status="draft",
            visibility="private",
            created_at=now,
            updated_at=now,
        )
    )

    assert public.suggested_questions == []
    assert embed.embed_config == {}
    assert listed.team.name == "Team"


def test_message_conversation_and_chat_nested_serialization():
    now = datetime.now(UTC)
    conversation_id = uuid4()
    message_id = uuid4()
    version = MessageVersion(
        id=uuid4(),
        version_number=1,
        is_active=True,
        content="Earlier",
        created_at=now,
    )
    step = MessageRoundStep(id=uuid4(), role="tool", content="Result", created_at=now)
    message = MessageOut(
        id=message_id,
        conversation_id=conversation_id,
        role="assistant",
        content="Answer",
        steps=[step],
        versions=[version],
        created_at=now,
    )
    conversation = ConversationWithMessages(
        id=conversation_id,
        agent_id=uuid4(),
        messages=[message],
        created_at=now,
        updated_at=now,
    )
    response = ChatResponse(conversation_id=conversation_id, message=message)

    assert conversation.messages[0].steps[0].content == "Result"
    assert (
        response.model_dump(mode="json")["message"]["versions"][0]["version_number"]
        == 1
    )
    assert (
        ConversationOut.model_validate(
            SimpleNamespace(
                id=conversation_id,
                agent_id=conversation.agent_id,
                created_at=now,
                updated_at=now,
            )
        ).message_count
        == 0
    )


def test_chat_content_and_history_types_round_trip():
    image = ImageContent(url="data:image/png;base64,AA==")
    file = FileContent(
        filename="notes.txt", content="notes", mime_type="text/plain", size=5
    )
    file_url = FileUrl(
        filename="notes.txt",
        url="https://example.test/notes.txt",
        size=5,
        mime_type="text/plain",
    )
    tool_call = HistoryToolCall(id="call-1", name="search")
    history = HistoryMessage(
        role="assistant", content="Searching", tool_calls=[tool_call]
    )
    request = ChatRequest(
        message="Hello",
        images=[image],
        files=[file],
        file_urls=[file_url],
        history_override=[history],
    )

    assert (
        request.model_dump()["history_override"][0]["tool_calls"][0]["arguments"] == {}
    )
    assert request.images[0].type == "image_url"
    assert request.files[0].truncated is False
    assert SwitchVersionRequest(version_id=uuid4()).version_id
    assert EditMessageRequest(content="Revised").content == "Revised"
