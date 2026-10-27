"""User-visible context replay behavior for attachments and asset views.

The model must see the same attachments and viewed-asset payloads on every
follow-up turn: scoped asset bindings are replayed, malformed or stale markers
fail closed, and refreshed file URLs are persisted for later turns.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.llm.types import ContentPart, ContentType, ImageContent
from app.models.agent import MessageRole as ConversationMessageRole
from app.schemas.response import BusinessError
from app.services import chat_context


def _agent(**values):
    defaults = {
        "id": uuid4(),
        "team_id": None,
        "system_prompt": "prompt",
        "enable_memory": False,
        "tools_config": [],
        "enable_attachments": False,
        "enable_image_generation": False,
        "enable_video_generation": False,
        "context_compression_config": {},
    }
    defaults.update(values)
    return SimpleNamespace(**defaults)


def _conversation():
    return SimpleNamespace(id=uuid4(), variables={})


def _asset(**values):
    defaults = {
        "id": uuid4(),
        "checksum": "checksum-1",
        "content_type": "image/png",
        "display_filename": "pic.png",
    }
    defaults.update(values)
    return SimpleNamespace(**defaults)


def _part(**values):
    defaults = {
        "type": ContentType.IMAGE,
        "image": ImageContent(mime_type="image/png", asset_ref="r1"),
    }
    defaults.update(values)
    return ContentPart(**defaults)


def _marker(conversation, asset, **overrides):
    value = {
        "version": 1,
        "kind": "asset.view",
        "ref": "r1",
        "asset_id": str(asset.id),
        "scope_type": "conversation",
        "scope_id": str(conversation.id),
        "modality": "image",
        "mime_type": "image/png",
        "wire_mime_type": "image/png",
        "checksum": asset.checksum,
        "extracted_text": False,
        "selection": None,
        "representation": {"kind": "native"},
    }
    value.update(overrides)
    return value


async def _build(
    monkeypatch,
    *,
    history_override,
    current_images=None,
    current_user_message_id=None,
    include_current_user_message=True,
    protected_round_id=None,
    history=None,
    resolve=None,
):
    conversation = _conversation()
    monkeypatch.setattr(
        chat_context,
        "get_visible_conversation_messages",
        AsyncMock(return_value=history if history is not None else []),
    )
    if resolve is None:
        resolve = AsyncMock(return_value=([], ""))
    monkeypatch.setattr(chat_context, "_resolve_message_asset_parts", resolve)
    messages, _protected, _meta = await chat_context._build_messages_with_file_content(
        agent=_agent(),
        conversation=conversation,
        user_message="follow-up question",
        file_content=None,
        user_locale="en",
        history_override=history_override,
        current_images=current_images,
        input_capabilities=SimpleNamespace(modalities=frozenset({ContentType.TEXT})),
        model_config=None,
        current_user_message_id=current_user_message_id,
        include_current_user_message=include_current_user_message,
        exclude_message_ids=None,
        history_before_message_created_at=None,
        user=SimpleNamespace(id=uuid4()),
        protected_round_id=protected_round_id,
    )
    return conversation, messages


def _link(asset_id, asset):
    return SimpleNamespace(asset_id=asset_id, asset=asset)


def _filter_chain(links):
    async def _links(*_args, **_kwargs):
        return links

    return lambda **_kwargs: SimpleNamespace(
        prefetch_related=lambda *_a: SimpleNamespace(order_by=lambda *_a: _links())
    )


@pytest.mark.asyncio
async def test_historical_attachment_replay_keeps_only_conversation_scoped_assets(
    monkeypatch,
):
    """A deleted/unbound asset is dropped; a bound one reaches the model."""
    asset = SimpleNamespace(
        display_filename="notes.txt", content_type="text/plain", size=3
    )
    orphan = SimpleNamespace(
        display_filename="orphan.txt", content_type="text/plain", size=3
    )
    bound_id, orphan_id = uuid4(), uuid4()
    history = [
        SimpleNamespace(
            id=uuid4(),
            role=ConversationMessageRole.USER,
            content="summarize the notes",
            file_urls=None,
            round_id=uuid4(),
            round_role=None,
            is_round_canonical=True,
        )
    ]

    async def resolve_attachments(attachments, **_kwargs):
        refs = [
            f"{item['asset_ref']}:{item['filename']}"
            for item in attachments
            if isinstance(item, dict) and item.get("asset_ref")
        ]
        if not refs:
            return [], ""
        return [
            ContentPart(type=ContentType.TEXT, text="attached:" + ",".join(refs))
        ], ""

    monkeypatch.setattr(
        "app.models.asset.MessageAsset",
        SimpleNamespace(
            filter=_filter_chain([_link(bound_id, asset), _link(orphan_id, orphan)])
        ),
    )
    monkeypatch.setattr(
        "app.models.asset.AssetScopeRef",
        SimpleNamespace(
            get_or_none=AsyncMock(side_effect=[SimpleNamespace(ref="scoped-ref"), None])
        ),
    )

    _, messages = await _build(
        monkeypatch,
        history_override=None,
        history=history,
        resolve=resolve_attachments,
    )

    assert messages[-1].role.value == "user"
    assert [part.text for part in messages[-1].content] == [
        "summarize the notes",
        "attached:scoped-ref:notes.txt",
    ]


@pytest.mark.asyncio
async def test_historical_view_asset_tool_result_replays_parts_for_the_next_turn(
    monkeypatch,
):
    round_id = uuid4()
    replayed = _part()
    history = [
        SimpleNamespace(
            id=uuid4(),
            role=ConversationMessageRole.ASSISTANT,
            content="",
            reasoning_content=None,
            tool_calls=[
                {"id": "call-view", "name": "view_asset", "arguments": {"ref": "r1"}}
            ],
            round_id=round_id,
            round_role=None,
            is_round_canonical=False,
        ),
        SimpleNamespace(
            id=uuid4(),
            role=ConversationMessageRole.TOOL,
            content=json.dumps({"display": {"kind": "asset.view", "ref": "r1"}}),
            tool_call_id="call-view",
            tool_name="view_asset",
            round_id=round_id,
            round_role=None,
            is_round_canonical=False,
        ),
    ]
    rehydrate = AsyncMock(return_value=[replayed])
    monkeypatch.setattr(chat_context, "_rehydrate_asset_view_marker", rehydrate)

    _, messages = await _build(monkeypatch, history_override=None, history=history)

    tool_message = next(m for m in messages if m.role.value == "tool")
    assert json.loads(tool_message.content) == {"kind": "asset.view", "ref": "r1"}
    assert messages[-1].role.value == "user"
    assert messages[-1].content == [replayed]


@pytest.mark.asyncio
async def test_historical_tool_replay_skips_parts_already_in_the_current_message(
    monkeypatch,
):
    round_id = uuid4()
    current_part = _part()
    history = [
        SimpleNamespace(
            id=uuid4(),
            role=ConversationMessageRole.ASSISTANT,
            content="",
            reasoning_content=None,
            tool_calls=[
                {"id": "call-view", "name": "view_asset", "arguments": {"ref": "r1"}}
            ],
            round_id=round_id,
            round_role=None,
            is_round_canonical=False,
        ),
        SimpleNamespace(
            id=uuid4(),
            role=ConversationMessageRole.TOOL,
            content=json.dumps({"display": {"kind": "asset.view"}, "ref": "r1"}),
            tool_call_id="call-view",
            tool_name="view_asset",
            round_id=round_id,
            round_role=None,
            is_round_canonical=False,
        ),
    ]
    monkeypatch.setattr(
        chat_context,
        "_rehydrate_asset_view_marker",
        AsyncMock(return_value=[current_part]),
    )

    _, messages = await _build(
        monkeypatch,
        history_override=None,
        history=history,
        current_images=[SimpleNamespace(asset_ref="r1")],
        resolve=AsyncMock(return_value=([current_part], "")),
    )

    assert messages[-1].role.value == "tool"


@pytest.mark.asyncio
async def test_override_tool_result_replays_deferred_asset_part(monkeypatch):
    round_id = uuid4()
    replayed = _part()
    monkeypatch.setattr(
        chat_context, "_rehydrate_asset_view_marker", AsyncMock(return_value=[replayed])
    )

    _, messages = await _build(
        monkeypatch,
        history_override=[
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "call-view", "name": "view_asset", "arguments": {}}
                ],
                "round_id": str(round_id),
                "round_role": "assistant_step",
            },
            {
                "role": "tool",
                "content": json.dumps({"display": {"kind": "asset.view"}, "ref": "r1"}),
                "tool_call_id": "call-view",
                "tool_name": "view_asset",
                "round_id": str(round_id),
                "round_role": "tool_result",
            },
        ],
    )

    assert messages[-1].role.value == "user"
    assert messages[-1].content == "follow-up question"
    assert messages[-2].role.value == "user"
    assert messages[-2].content == [replayed]


@pytest.mark.asyncio
async def test_active_round_delta_replays_asset_part_after_current_user_message(
    monkeypatch,
):
    round_id = uuid4()
    replayed = _part()
    monkeypatch.setattr(
        chat_context, "_rehydrate_asset_view_marker", AsyncMock(return_value=[replayed])
    )

    _, messages = await _build(
        monkeypatch,
        history_override=[
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "call-view", "name": "view_asset", "arguments": {}}
                ],
                "round_id": str(round_id),
                "round_role": "assistant_step",
            },
            {
                "role": "tool",
                "content": json.dumps({"display": {"kind": "asset.view"}, "ref": "r1"}),
                "tool_call_id": "call-view",
                "tool_name": "view_asset",
                "round_id": str(round_id),
                "round_role": "tool_result",
            },
        ],
        protected_round_id=round_id,
    )

    assert [message.role.value for message in messages] == [
        "system",
        "user",
        "assistant",
        "tool",
        "user",
    ]
    assert messages[1].content == "follow-up question"
    assert messages[-1].content == [replayed]


@pytest.mark.asyncio
async def test_persisted_view_marker_envelope_is_unwrapped_and_rehydrated(
    monkeypatch,
):
    conversation = _conversation()
    asset = _asset()
    part = _part()
    marker = _marker(conversation, asset)
    resolve = AsyncMock(return_value=(asset, part, json.dumps(marker)))
    monkeypatch.setattr("app.services.asset_view.resolve_view_content", resolve)

    persisted = json.dumps(
        {
            "kind": "asset.view.persisted",
            "version": 1,
            "display": {"kind": "asset.view"},
            "marker": json.dumps(marker),
        }
    )

    replayed = await chat_context._rehydrate_asset_view_marker(
        persisted,
        tool_name="view_asset",
        user=SimpleNamespace(id=uuid4()),
        conversation=conversation,
        agent=_agent(),
        model_config=SimpleNamespace(),
    )

    assert replayed == [
        ContentPart(
            type=ContentType.TEXT,
            text="Viewed attachment pic.png (image).",
        ),
        part,
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "content",
    [
        "not-json",
        json.dumps({"kind": "asset.view.persisted", "version": 1, "marker": 7}),
        json.dumps({"kind": "asset.view.persisted", "version": 1, "marker": "bad"}),
        json.dumps({"kind": "other", "version": 1}),
        json.dumps({"kind": "asset.view", "version": 2}),
        json.dumps({"kind": "asset.view", "version": 1, "ref": 7, "checksum": "c"}),
        json.dumps({"kind": "asset.view", "version": 1, "ref": "r1", "checksum": None}),
    ],
)
async def test_malformed_view_markers_are_not_replayed(monkeypatch, content):
    resolve = AsyncMock()
    monkeypatch.setattr("app.services.asset_view.resolve_view_content", resolve)

    result = await chat_context._rehydrate_asset_view_marker(
        content,
        tool_name="view_asset",
        user=SimpleNamespace(id=uuid4()),
        conversation=_conversation(),
        agent=_agent(),
        model_config=SimpleNamespace(),
    )

    assert result is None


@pytest.mark.asyncio
async def test_foreign_scope_or_stale_view_marker_fails_closed(monkeypatch):
    conversation = _conversation()
    asset = _asset()
    marker = _marker(conversation, asset)
    resolve = AsyncMock(return_value=(asset, _part(), json.dumps(marker)))
    monkeypatch.setattr("app.services.asset_view.resolve_view_content", resolve)

    foreign = json.dumps(_marker(conversation, asset, scope_id=str(uuid4())))
    with pytest.raises(BusinessError) as foreign_error:
        await chat_context._rehydrate_asset_view_marker(
            foreign,
            tool_name="view_asset",
            user=SimpleNamespace(id=uuid4()),
            conversation=conversation,
            agent=_agent(),
            model_config=SimpleNamespace(),
        )
    assert foreign_error.value.code == 4040
    assert foreign_error.value.msg_key == "file_not_found"

    changed = _asset(checksum="changed")
    stale_resolve = AsyncMock(return_value=(changed, _part(), json.dumps(marker)))
    monkeypatch.setattr("app.services.asset_view.resolve_view_content", stale_resolve)
    with pytest.raises(BusinessError) as stale_error:
        await chat_context._rehydrate_asset_view_marker(
            json.dumps(marker),
            tool_name="view_asset",
            user=SimpleNamespace(id=uuid4()),
            conversation=conversation,
            agent=_agent(),
            model_config=SimpleNamespace(),
        )
    assert stale_error.value.msg_key == "file_not_found"

    missing_part = AsyncMock(return_value=(asset, None, json.dumps(marker)))
    monkeypatch.setattr("app.services.asset_view.resolve_view_content", missing_part)
    with pytest.raises(BusinessError):
        await chat_context._rehydrate_asset_view_marker(
            json.dumps(marker),
            tool_name="view_asset",
            user=SimpleNamespace(id=uuid4()),
            conversation=conversation,
            agent=_agent(),
            model_config=SimpleNamespace(),
        )


@pytest.mark.asyncio
async def test_refreshed_file_urls_are_persisted_for_later_turns(monkeypatch):
    build = AsyncMock(return_value=("parsed", ["https://fresh"]))
    monkeypatch.setattr(
        "app.api.v1.endpoints.chat_tools.build_file_content_for_context", build
    )

    source = SimpleNamespace(
        file_urls=["https://expired"],
        save=AsyncMock(),
    )
    content = await chat_context._build_file_content_for_user_message(
        agent=_agent(),
        file_urls=["https://expired"],
        legacy_files=None,
        user_locale="en",
        tool_timeouts=None,
        user=SimpleNamespace(id=uuid4()),
        source_message=source,
    )

    assert content == "parsed"
    assert source.file_urls == ["https://fresh"]
    source.save.assert_awaited_once_with(update_fields=["file_urls"])

    unchanged = SimpleNamespace(file_urls=["https://fresh"], save=AsyncMock())
    await chat_context._build_file_content_for_user_message(
        agent=_agent(),
        file_urls=["https://fresh"],
        legacy_files=None,
        user_locale="en",
        tool_timeouts=None,
        user=SimpleNamespace(id=uuid4()),
        source_message=unchanged,
    )
    unchanged.save.assert_not_awaited()
