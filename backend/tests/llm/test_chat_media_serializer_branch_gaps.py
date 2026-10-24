"""Branch coverage for chat adapter media validation and model resolution.

Covers the remaining media-validation / capability-rejection arcs in the
Gemini, OpenAI, and Anthropic chat adapters plus ``chat_helpers.model_utils``.

Contract asserted here: malformed or unsupported media payloads fail fast with
an ``InvalidRequestError`` and nothing is silently dropped, while valid typed
payloads are serialized into the provider wire format verbatim.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.api.v1.endpoints.chat_helpers import model_utils
from app.llm.adapters.chat.anthropic_adapter import AnthropicAdapter
from app.llm.adapters.chat.gemini_adapter import GeminiAdapter
from app.llm.adapters.chat.openai_adapter import OpenAIAdapter
from app.llm.errors import InvalidRequestError
from app.llm.types import (
    AudioContent,
    ContentPart,
    ContentType,
    FileContent,
    FinishReason,
    ImageContent,
    Message,
    MessageRole,
    VideoContent,
)
from app.schemas.response import BusinessError, ResponseCode


def obj(**values):
    return SimpleNamespace(**values)


def adapter(adapter_type, **overrides):
    values = {
        "model_id": "test-model",
        "api_key": "secret",
        "base_url": None,
        "config": {},
        "default_params": {},
        "max_output_tokens": None,
    }
    values.update(overrides)
    return adapter_type(obj(**values))


def message(parts, role=MessageRole.USER):
    return SimpleNamespace(
        role=role,
        content=parts,
        reasoning_content=None,
        tool_calls=None,
        tool_call_id=None,
    )


# ---------------------------------------------------------------------------
# Gemini adapter
# ---------------------------------------------------------------------------


def test_gemini_audio_and_video_url_serialize_without_declared_mime():
    gemini = adapter(GeminiAdapter)

    _, contents = gemini._convert_messages(
        [
            message(
                [
                    ContentPart(
                        type=ContentType.AUDIO,
                        audio=AudioContent(base64="YXVkaW8=", format="wav"),
                    ),
                    ContentPart(
                        type=ContentType.VIDEO,
                        video=VideoContent(
                            url="https://video.invalid/clip.mp4", mime_type=None
                        ),
                    ),
                ]
            )
        ]
    )

    assert contents[0]["parts"] == [
        {"inline_data": {"mime_type": "audio/wav", "data": "YXVkaW8="}},
        {
            "file_data": {
                "mime_type": None,
                "file_uri": "https://video.invalid/clip.mp4",
            }
        },
    ]


def test_gemini_media_payloads_fail_fast_when_missing_or_unresolved():
    gemini = adapter(GeminiAdapter)

    for part_type, payload, expected in (
        (ContentType.AUDIO, AudioContent(), "Audio payload is missing"),
        (ContentType.VIDEO, VideoContent(), "Video payload is missing"),
        (
            ContentType.AUDIO,
            AudioContent(asset_ref="asset-1", base64=None),
            "Unresolved asset reference cannot be serialized",
        ),
        (
            ContentType.VIDEO,
            VideoContent(asset_ref="asset-2", url=None),
            "Unresolved asset reference cannot be serialized",
        ),
        (ContentType.AUDIO, None, "Audio content is missing"),
        (ContentType.VIDEO, None, "Video content is missing"),
    ):
        with pytest.raises(InvalidRequestError, match=expected):
            gemini._convert_messages(
                [message([ContentPart(type=part_type, **{part_type.value: payload})])]
            )


def test_gemini_file_payload_serialization_and_rejections():
    gemini = adapter(GeminiAdapter)

    _, contents = gemini._convert_messages(
        [
            message(
                [
                    ContentPart(
                        type=ContentType.FILE,
                        file=FileContent(extracted_text="body", filename="report.txt"),
                    ),
                    ContentPart(
                        type=ContentType.FILE,
                        file=FileContent(mime_type="application/pdf", base64="cGRm"),
                    ),
                ]
            )
        ]
    )
    assert contents[0]["parts"] == [
        {"text": "report.txt:\nbody"},
        {"inline_data": {"mime_type": "application/pdf", "data": "cGRm"}},
    ]

    # PDF without a payload, and non-PDF MIME types, are rejected not dropped
    for payload in (
        FileContent(mime_type="application/pdf"),
        FileContent(mime_type="text/plain", base64="cGRm"),
    ):
        with pytest.raises(
            InvalidRequestError,
            match=f"Unsupported Gemini file MIME type: {payload.mime_type}",
        ):
            gemini._convert_messages(
                [message([ContentPart(type=ContentType.FILE, file=payload)])]
            )

    with pytest.raises(InvalidRequestError, match="File content is missing"):
        gemini._convert_messages(
            [message([ContentPart(type=ContentType.FILE, file=None)])]
        )


class _GeminiStream:
    def __init__(self, chunks):
        self.chunks = iter(chunks)

    def __aiter__(self):
        return self

    async def __anext__(self):
        chunk = next(self.chunks, None)
        if chunk is None:
            raise StopAsyncIteration
        return chunk


def _install_gemini_client(monkeypatch, stream):
    models = SimpleNamespace(
        generate_content=AsyncMock(),
        generate_content_stream=AsyncMock(return_value=stream),
    )
    monkeypatch.setattr(
        "google.genai.Client", lambda **kwargs: obj(aio=obj(models=models))
    )
    return models


@pytest.mark.anyio
async def test_gemini_stream_emits_usage_only_chunk_when_candidates_absent(
    monkeypatch,
):
    chunks = [
        obj(
            candidates=[],
            usage_metadata=obj(
                prompt_token_count=7,
                candidates_token_count=3,
                total_token_count=10,
                cached_content_token_count=2,
            ),
        )
    ]
    models = _install_gemini_client(monkeypatch, _GeminiStream(chunks))
    gemini = adapter(GeminiAdapter)

    emitted = [chunk async for chunk in gemini.chat_stream([message("hi")])]

    assert len(emitted) == 1
    assert emitted[0].usage.total_tokens == 10
    assert emitted[0].usage.cache_read_tokens == 2
    assert emitted[0].usage.total_input_tokens == 7
    assert emitted[0].delta.content is None
    assert emitted[0].finish_reason is None
    models.generate_content_stream.assert_awaited_once()


@pytest.mark.anyio
async def test_gemini_stream_skips_candidate_free_chunks_without_usage(monkeypatch):
    _install_gemini_client(
        monkeypatch, _GeminiStream([obj(candidates=[], usage_metadata=None)])
    )
    gemini = adapter(GeminiAdapter)

    assert [chunk async for chunk in gemini.chat_stream([message("hi")])] == []


# ---------------------------------------------------------------------------
# OpenAI adapter
# ---------------------------------------------------------------------------


def test_openai_image_rejects_missing_or_unresolved_payloads():
    openai = adapter(OpenAIAdapter)

    for image in (
        None,
        ImageContent(asset_ref="asset-1"),
        ImageContent(),
    ):
        with pytest.raises(
            InvalidRequestError, match="Image payload is missing or unresolved"
        ):
            openai._convert_messages(
                [message([ContentPart(type=ContentType.IMAGE, image=image)])]
            )


def test_openai_image_data_url_must_declare_base64_encoding():
    openai = adapter(OpenAIAdapter)

    for url in ("data:image/png,raw", "data:image/png;base64"):
        with pytest.raises(
            InvalidRequestError, match="Image data URL must use base64 encoding"
        ):
            openai._convert_messages(
                [
                    message(
                        [
                            ContentPart(
                                type=ContentType.IMAGE,
                                image=ImageContent(url=url, base64=None),
                            )
                        ]
                    )
                ]
            )


def test_openai_image_rejects_unsupported_mime_and_serializes_base64():
    openai = adapter(OpenAIAdapter)

    with pytest.raises(
        InvalidRequestError, match="Unsupported image MIME type: image/tiff"
    ):
        openai._convert_messages(
            [
                message(
                    [
                        ContentPart(
                            type=ContentType.IMAGE,
                            image=ImageContent(
                                base64="aW1n", format="tiff", mime_type="image/tiff"
                            ),
                        )
                    ]
                )
            ]
        )

    converted = openai._convert_messages(
        [
            message(
                [
                    ContentPart(
                        type=ContentType.IMAGE,
                        image=ImageContent(base64="aW1n", format="png"),
                    )
                ]
            )
        ]
    )
    assert converted[0]["content"] == [
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,aW1n"}}
    ]


def test_openai_rejects_unsupported_and_malformed_content_parts():
    openai = adapter(OpenAIAdapter)

    with pytest.raises(
        InvalidRequestError, match="File input is unsupported by OpenAI chat adapter"
    ):
        openai._convert_messages(
            [
                message(
                    [
                        ContentPart(
                            type=ContentType.FILE,
                            file=FileContent(
                                extracted_text="body", filename="report.txt"
                            ),
                        )
                    ]
                )
            ]
        )

    for part_type, payload, expected in (
        (ContentType.AUDIO, AudioContent(base64="YXVkaW8="), "Audio input"),
        (ContentType.VIDEO, VideoContent(base64="dmlkZW8="), "Video input"),
    ):
        with pytest.raises(
            InvalidRequestError, match=f"{expected} is unsupported by OpenAI"
        ):
            openai._convert_messages(
                [message([ContentPart(type=part_type, **{part_type.value: payload})])]
            )

    with pytest.raises(InvalidRequestError, match="Unsupported content part: diagram"):
        openai._convert_messages(
            [message([SimpleNamespace(type="diagram", image=None)])]
        )

    with pytest.raises(InvalidRequestError, match="Invalid multimodal content part"):
        openai._convert_messages([message([object()])])


def test_openai_passes_through_image_url_and_raw_dict_parts():
    openai = adapter(OpenAIAdapter)

    converted = openai._convert_messages(
        [
            message(
                [
                    SimpleNamespace(
                        type="image_url",
                        image_url={"url": "https://image.invalid/b.png"},
                    ),
                    {"type": "text", "text": "raw"},
                ]
            )
        ]
    )

    assert converted[0]["content"] == [
        {"type": "image_url", "image_url": {"url": "https://image.invalid/b.png"}},
        {"type": "text", "text": "raw"},
    ]


def test_openai_image_rejects_falsy_payload_without_url():
    """Empty-string base64/url pass the earlier truthiness gate, then fail."""
    openai = adapter(OpenAIAdapter)

    with pytest.raises(
        InvalidRequestError, match="Image payload is missing or unresolved"
    ):
        openai._convert_messages(
            [
                message(
                    [
                        ContentPart(
                            type=ContentType.IMAGE,
                            image=ImageContent(
                                base64="",
                                url="",
                                format="png",
                                mime_type="image/png",
                            ),
                        )
                    ]
                )
            ]
        )


class _OpenAIStream:
    def __init__(self, chunks):
        self.chunks = list(chunks)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self.chunks:
            raise StopAsyncIteration
        return self.chunks.pop(0)


def _install_openai_client(monkeypatch, stream):
    create = AsyncMock(return_value=stream)
    client = obj(
        chat=obj(completions=obj(create=create)),
        close=AsyncMock(),
    )
    monkeypatch.setattr("openai.AsyncOpenAI", lambda **kwargs: client)
    return create, client


def _tool_delta(index, name, arguments):
    return obj(
        index=index,
        id=None,
        type="function",
        function=obj(name=name, arguments=arguments),
    )


@pytest.mark.anyio
async def test_openai_stream_emits_tool_only_activity_chunk(monkeypatch):
    """Tool deltas carrying no content and no finish still surface activity."""
    chunks = [
        obj(choices=[], usage=None),
        obj(
            choices=[
                obj(
                    delta=obj(content=None, reasoning_content=None, tool_calls=None),
                    finish_reason=None,
                )
            ],
            usage=None,
        ),
        obj(
            choices=[
                obj(
                    delta=obj(
                        content=None,
                        reasoning_content=None,
                        tool_calls=[_tool_delta(0, "lookup", '{"q":')],
                    ),
                    finish_reason=None,
                )
            ],
            usage=None,
        ),
    ]
    create, client = _install_openai_client(monkeypatch, _OpenAIStream(chunks))
    openai = adapter(OpenAIAdapter)

    emitted = [
        chunk
        async for chunk in openai.chat_stream(
            [Message(role=MessageRole.USER, content="hi")]
        )
    ]

    assert len(emitted) == 2
    assert all(chunk.delta.stream_activity for chunk in emitted)
    assert all(chunk.delta.content is None for chunk in emitted)
    assert all(chunk.delta.tool_call_starts is None for chunk in emitted)
    assert all(chunk.finish_reason is None for chunk in emitted)
    create.assert_awaited_once()
    client.close.assert_awaited_once()


# ---------------------------------------------------------------------------
# Anthropic adapter
# ---------------------------------------------------------------------------


def test_anthropic_file_payloads_serialize_and_fail_fast():
    anthropic = adapter(AnthropicAdapter)

    _, converted = anthropic._convert_messages(
        [
            message(
                [
                    ContentPart(
                        type=ContentType.FILE,
                        file=FileContent(extracted_text="body", filename="report.pdf"),
                    ),
                    ContentPart(
                        type=ContentType.FILE,
                        file=FileContent(mime_type="application/pdf", base64="cGRm"),
                    ),
                ]
            )
        ]
    )
    assert converted[0]["content"] == [
        {"type": "text", "text": "report.pdf:\nbody"},
        {
            "type": "document",
            "source": {
                "type": "base64",
                "media_type": "application/pdf",
                "data": "cGRm",
            },
        },
    ]

    with pytest.raises(InvalidRequestError, match="File content is missing"):
        anthropic._convert_messages(
            [message([ContentPart(type=ContentType.FILE, file=None)])]
        )

    with pytest.raises(
        InvalidRequestError, match="Unsupported Anthropic file MIME type: text/plain"
    ):
        anthropic._convert_messages(
            [
                message(
                    [
                        ContentPart(
                            type=ContentType.FILE,
                            file=FileContent(mime_type="text/plain", base64="cGRm"),
                        )
                    ]
                )
            ]
        )


def test_anthropic_rejects_audio_and_video_input_parts():
    anthropic = adapter(AnthropicAdapter)

    for part_type, payload in (
        (ContentType.AUDIO, AudioContent(base64="YXVkaW8=")),
        (ContentType.VIDEO, VideoContent(base64="dmlkZW8=")),
    ):
        with pytest.raises(
            InvalidRequestError,
            match=f"Anthropic chat input does not support {part_type.value}",
        ):
            anthropic._convert_messages(
                [message([ContentPart(type=part_type, **{part_type.value: payload})])]
            )


def test_anthropic_convert_messages_keeps_dict_and_tool_result_payloads():
    anthropic = adapter(AnthropicAdapter, default_params={"thinking": True})
    messages = [
        message([{"type": "text", "text": "raw dict"}, {"ignored": True}]),
        SimpleNamespace(
            role=MessageRole.TOOL,
            content=[obj(text="result"), {"text": "more"}],
            tool_call_id="call-1",
        ),
    ]

    _, converted = anthropic._convert_messages(messages)

    assert converted[0]["content"] == [
        {"type": "text", "text": "raw dict"},
        {"ignored": True},
    ]
    assert converted[1]["content"] == [
        {"type": "tool_result", "tool_use_id": "call-1", "content": "result\nmore"}
    ]


def test_anthropic_is_real_user_message_rejects_tool_result_and_empty_content():
    anthropic = adapter(AnthropicAdapter)

    assert anthropic._is_real_user_message({"role": "user", "content": "plain"}) is True
    assert (
        anthropic._is_real_user_message(
            {"role": "user", "content": [{"type": "text", "text": "plain"}]}
        )
        is True
    )
    assert (
        anthropic._is_real_user_message({"role": "assistant", "content": "x"}) is False
    )
    assert (
        anthropic._is_real_user_message(
            {"role": "user", "content": [{"type": "tool_result", "content": "x"}]}
        )
        is False
    )
    assert anthropic._is_real_user_message({"role": "user", "content": []}) is False


def test_anthropic_message_cache_breakpoint_marks_first_text_block_only():
    anthropic = adapter(AnthropicAdapter)

    string_message = {"role": "user", "content": "hello"}
    anthropic._mark_message_cache_breakpoint(string_message)
    assert string_message["content"] == [
        {"type": "text", "text": "hello", "cache_control": {"type": "ephemeral"}}
    ]

    list_message = {
        "role": "user",
        "content": [
            {"type": "image"},
            {"type": "text", "text": "first"},
            {"type": "text", "text": "second"},
        ],
    }
    anthropic._mark_message_cache_breakpoint(list_message)
    assert "cache_control" not in list_message["content"][0]
    assert list_message["content"][1]["cache_control"] == {"type": "ephemeral"}
    assert "cache_control" not in list_message["content"][2]

    # A list without any text block, and non-list content, are left untouched
    image_only = {"role": "user", "content": [{"type": "image"}]}
    anthropic._mark_message_cache_breakpoint(image_only)
    assert image_only["content"] == [{"type": "image"}]

    other = {"role": "user", "content": 5}
    anthropic._mark_message_cache_breakpoint(other)
    assert other["content"] == 5


def test_anthropic_cache_breakpoints_skip_prefix_below_threshold():
    anthropic = adapter(AnthropicAdapter)
    messages = [{"role": "user", "content": "short"}]
    tools = [{"name": "lookup", "input_schema": {"type": "object"}}]

    system, converted, converted_tools = anthropic._apply_cache_breakpoints(
        "short system", messages, tools
    )

    assert system == "short system"
    assert converted == [{"role": "user", "content": "short"}]
    assert "cache_control" not in converted_tools[-1]


def test_anthropic_extract_response_ignores_empty_blocks():
    anthropic = adapter(AnthropicAdapter)
    response = obj(
        content=[
            obj(type="text", text=""),
            obj(type="thinking", thinking=""),
            obj(type="ignored"),
        ],
        stop_reason="unknown_reason",
        usage=None,
    )

    content, reasoning, tool_calls = anthropic._extract_response(response)

    assert content is None
    assert reasoning is None
    assert tool_calls is None
    assert anthropic._map_finish_reason("unknown_reason") == FinishReason.STOP


# ---------------------------------------------------------------------------
# chat_helpers.model_utils
# ---------------------------------------------------------------------------


class _Query:
    def __init__(self, result=None):
        self.result = result

    def prefetch_related(self, *_args):
        return self

    def filter(self, *_args, **_kwargs):
        return self

    async def first(self):
        return self.result


def _model(**overrides):
    values = {
        "id": "11111111-1111-1111-1111-111111111111",
        "model_id": "gpt-test",
        "provider": "openai",
        "model_type": "chat",
        "is_enabled": True,
        "context_length": 8192,
        "max_output_tokens": 4096,
        "base_url": None,
        "capabilities": {"input_modalities": ["text", "image"]},
        "config": None,
    }
    values.update(overrides)
    return obj(**values)


def _team_model(model=None):
    return obj(is_enabled=True, model=model or _model())


@pytest.mark.anyio
async def test_resolve_agent_chat_model_requires_bound_model_when_configured(
    monkeypatch,
):
    from app.api.v1.endpoints import chat
    from app.llm import model_manager

    get_agent_chat_model = AsyncMock(return_value=None)
    monkeypatch.setattr(chat, "get_agent_chat_model", get_agent_chat_model)
    monkeypatch.setattr(model_manager, "resolve_team_chat_model", AsyncMock())

    with pytest.raises(BusinessError) as caught:
        await model_utils.resolve_agent_chat_model(
            obj(model_id="22222222-2222-2222-2222-222222222222", team_id=None)
        )

    assert caught.value.code == ResponseCode.MODEL_NOT_FOUND
    assert caught.value.msg_key == "model_not_found"
    get_agent_chat_model.assert_awaited_once()


@pytest.mark.anyio
async def test_resolve_agent_chat_model_rejects_disabled_bindings(monkeypatch):
    from app.api.v1.endpoints import chat

    monkeypatch.setattr(
        chat,
        "get_agent_chat_model",
        AsyncMock(return_value=obj(is_enabled=False, model=_model())),
    )

    with pytest.raises(BusinessError) as caught:
        await model_utils.resolve_agent_chat_model(
            obj(model_id="22222222-2222-2222-2222-222222222222", team_id=None)
        )

    assert caught.value.code == ResponseCode.MODEL_DISABLED
    assert caught.value.msg_key == "model_disabled"


@pytest.mark.anyio
async def test_resolve_agent_chat_model_rejects_disabled_global_model(monkeypatch):
    from app.api.v1.endpoints import chat

    monkeypatch.setattr(
        chat,
        "get_agent_chat_model",
        AsyncMock(return_value=_team_model(model=_model(is_enabled=False))),
    )

    with pytest.raises(BusinessError) as caught:
        await model_utils.resolve_agent_chat_model(
            obj(model_id="22222222-2222-2222-2222-222222222222", team_id=None)
        )

    assert caught.value.code == ResponseCode.MODEL_DISABLED


@pytest.mark.anyio
async def test_resolve_agent_chat_model_falls_back_to_team_default(monkeypatch):
    from app.api.v1.endpoints import chat
    from app.llm import model_manager

    default_model = _model()
    default_team_model = _team_model(model=default_model)
    monkeypatch.setattr(chat, "get_agent_chat_model", AsyncMock(return_value=None))
    resolve_default = AsyncMock(return_value=(default_model, default_team_model))
    monkeypatch.setattr(model_manager, "resolve_team_chat_model", resolve_default)

    resolution = await model_utils.resolve_agent_chat_model(
        obj(model_id=None, team_id="33333333-3333-3333-3333-333333333333")
    )

    assert resolution.model is default_model
    assert resolution.team_model is default_team_model
    assert resolution.model_id == "11111111-1111-1111-1111-111111111111"
    assert resolution.tokenizer_model_id == "gpt-test"
    assert resolution.provider == "openai"
    assert resolution.context_length == 8192
    assert resolution.max_output_tokens == 4096
    assert sorted(
        modality.value for modality in resolution.input_capabilities.modalities
    ) == ["image", "text"]
    resolve_default.assert_awaited_once_with(
        team_id="33333333-3333-3333-3333-333333333333", model_id=None
    )


@pytest.mark.anyio
async def test_resolve_agent_chat_model_returns_bound_model_metadata(monkeypatch):
    from app.api.v1.endpoints import chat

    bound_model = _model(provider="anthropic", model_id="claude-test")
    monkeypatch.setattr(
        chat, "get_agent_chat_model", AsyncMock(return_value=_team_model(bound_model))
    )

    resolution = await model_utils.resolve_agent_chat_model(
        obj(model_id="22222222-2222-2222-2222-222222222222", team_id=None)
    )

    assert resolution.model is bound_model
    assert resolution.tokenizer_model_id == "claude-test"
    assert resolution.provider == "anthropic"


@pytest.mark.anyio
async def test_get_model_identifier_reports_unbound_and_missing_bindings(monkeypatch):
    assert await model_utils.get_model_identifier(obj(model_id=None)) is None

    monkeypatch.setattr(model_utils.TeamModel, "filter", lambda **_kwargs: _Query())
    assert await model_utils.get_model_identifier(obj(model_id="missing")) is None

    monkeypatch.setattr(
        model_utils.TeamModel, "filter", lambda **_kwargs: _Query(obj(model=None))
    )
    assert await model_utils.get_model_identifier(obj(model_id="missing")) is None

    monkeypatch.setattr(
        model_utils.TeamModel, "filter", lambda **_kwargs: _Query(obj(model=_model()))
    )
    assert (
        await model_utils.get_model_identifier(
            obj(model_id="22222222-2222-2222-2222-222222222222")
        )
        == "11111111-1111-1111-1111-111111111111"
    )


def _capabilities(modalities):
    from app.llm.capabilities import InputCapabilities

    return InputCapabilities(frozenset(modalities), {}, {})


@pytest.mark.anyio
@pytest.mark.parametrize(
    "declared,expected",
    [
        (frozenset({ContentType.IMAGE, ContentType.TEXT}), ["image", "text"]),
        (frozenset({ContentType.TEXT}), ["text"]),
    ],
)
async def test_get_model_capabilities_reports_declared_modalities(
    monkeypatch, declared, expected
):
    monkeypatch.setattr(
        model_utils,
        "resolve_agent_chat_model",
        AsyncMock(
            return_value=SimpleNamespace(input_capabilities=_capabilities(declared))
        ),
    )

    assert await model_utils.get_model_capabilities(obj()) == {
        "input_modalities": expected
    }
