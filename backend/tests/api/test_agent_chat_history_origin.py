"""Agent chat history separation between the platform chat and API keys.

The platform Agent Chat (JWT) only reaches conversations that no API key
created; an API key only reaches the conversations it created itself. Agent
orchestration logs stay the owner's own full history view. These tests exercise
the real handlers against an in-memory database, so they observe the queries and
the responses the running server produces.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from tortoise import Tortoise

from app.api.chat_history_origin import (
    conversation_matches_origin,
    history_origin_filter,
    run_matches_origin,
)
from app.api.v1.admin.endpoints import conversations as admin_conversations
from app.api.v1.endpoints import agents, embed
from app.api.v1.endpoints import chat as chat_endpoints
from app.models.agent import Agent, Conversation, Message, MessageRole
from app.models.api_key import APIKey
from app.models.user import Permission, Role, Team, TeamMember, User
from app.schemas.response import BusinessError, ResponseCode


@asynccontextmanager
async def _database():
    await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["app.models"]})
    try:
        await Tortoise.generate_schemas()
        yield
    finally:
        await Tortoise.close_connections()


async def _permission(code: str) -> Permission:
    return await Permission.create(id=uuid4(), scope=code.split(":")[0], code=code)


async def _user(label: str, *, permissions: list[str] | None = None) -> User:
    user = await User.create(
        id=uuid4(),
        username=f"{label}_{uuid4().hex[:8]}",
        email=f"{label}_{uuid4().hex[:8]}@origin.test",
        hashed_password="x",
    )
    if permissions:
        role = await Role.create(id=uuid4(), name=f"role_{uuid4().hex[:8]}")
        for code in permissions:
            await role.permissions.add(await _permission(code))
        await user.roles.add(role)
    return await User.get(id=user.id).prefetch_related("roles__permissions")


async def _team(name: str, owner: User) -> Team:
    team = await Team.create(id=uuid4(), name=f"{name}_{uuid4().hex[:8]}")
    await TeamMember.create(id=uuid4(), team_id=team.id, user_id=owner.id, role="owner")
    return team


async def _agent(team: Team, owner: User, label: str) -> Agent:
    return await Agent.create(
        id=uuid4(),
        team=team,
        created_by_id=owner.id,
        name=f"{label}_{uuid4().hex[:8]}",
        conversation_count=1,
        message_count=1,
    )


async def _api_key(owner: User, *, agents: list[Agent] | None = None) -> APIKey:
    key = await APIKey.create(
        id=uuid4(),
        name=f"key_{uuid4().hex[:6]}",
        key_prefix=f"clou_{uuid4().hex[:6]}"[:12],
        key_hash="x",
        user_id=owner.id,
        is_active=True,
    )
    if agents:
        await key.agents.add(*agents)
    return key


async def _conversation(
    agent: Agent,
    owner: User,
    *,
    api_key_id=None,
    origin_unknown: bool = False,
    title: str = "history",
) -> Conversation:
    return await Conversation.create(
        id=uuid4(),
        agent_id=agent.id,
        user_id=owner.id,
        title=title,
        api_key_id=api_key_id,
        api_key_origin_unknown=origin_unknown,
        message_count=1,
    )


async def _message(conversation: Conversation, content: str) -> Message:
    return await Message.create(
        id=uuid4(),
        conversation_id=conversation.id,
        role=MessageRole.USER,
        content=content,
    )


def _titles(payload) -> set[str]:
    return {item["title"] for item in payload["data"]["items"]}


async def _list_chat_history(agent_id, auth_result):
    """Call the chat-history list route with the browser's default filters."""
    return await agents.list_agent_conversations(
        agent_id,
        search=None,
        created_after=None,
        created_before=None,
        sort_by="updated_at",
        page=1,
        page_size=20,
        auth_result=auth_result,
    )


async def _list_log_history(agent_id, current_user, api_key_id=None):
    """Call the orchestration-log list route with the default filters."""
    return await agents.list_agent_log_conversations(
        agent_id,
        search=None,
        created_after=None,
        created_before=None,
        sort_by="updated_at",
        api_key_id=api_key_id,
        page=1,
        page_size=20,
        current_user=current_user,
    )


# ============ Scoping primitives ============


def test_history_origin_filter_targets_one_surface():
    key = type("Key", (), {"id": uuid4()})()

    assert history_origin_filter() == {
        "api_key_id__isnull": True,
        "api_key_origin_unknown": False,
    }
    assert history_origin_filter(key) == {
        "api_key_id": key.id,
        "api_key_origin_unknown": False,
    }


def test_history_origin_filter_fails_closed_without_a_key_id():
    with pytest.raises(BusinessError) as error:
        history_origin_filter(object())

    assert error.value.code == ResponseCode.UNAUTHORIZED
    assert error.value.status_code == 401


def test_conversation_matches_origin_matrix():
    key, other_key = uuid4(), uuid4()
    platform = type("Conv", (), {"api_key_id": None, "api_key_origin_unknown": False})()
    stamped = type("Conv", (), {"api_key_id": key, "api_key_origin_unknown": False})()
    quarantined = type(
        "Conv", (), {"api_key_id": key, "api_key_origin_unknown": True}
    )()
    key_obj = type("Key", (), {"id": key})()
    other_obj = type("Key", (), {"id": other_key})()

    assert conversation_matches_origin(platform)
    assert not conversation_matches_origin(platform, key_obj)
    assert conversation_matches_origin(stamped, key_obj)
    assert not conversation_matches_origin(stamped, other_obj)
    assert not conversation_matches_origin(stamped)
    assert not conversation_matches_origin(quarantined, key_obj)
    assert not conversation_matches_origin(quarantined)
    # An unidentified credential never matches a stamped conversation.
    assert not conversation_matches_origin(stamped, object())


def test_run_matches_origin_never_inherits_unbound_runs():
    key_id, other_key_id = uuid4(), uuid4()
    key = type("Key", (), {"id": key_id, "is_active": True})()
    other_key = type("Key", (), {"id": other_key_id, "is_active": True})()
    inactive = type("Key", (), {"id": key_id, "is_active": False})()

    def run(api_key_id=None, payload=None):
        return type(
            "Run", (), {"api_key_id": api_key_id, "worker_payload": payload or {}}
        )()

    assert run_matches_origin(run())
    assert not run_matches_origin(run(), key)
    assert run_matches_origin(run(api_key_id=key_id), key)
    assert not run_matches_origin(run(api_key_id=key_id), other_key)
    assert not run_matches_origin(run(api_key_id=key_id))
    assert not run_matches_origin(run(api_key_id=key_id), inactive)

    # Payload evidence covers runs written before the run column existed.
    payload = {"tool_entrypoint": "api_key", "tool_entrypoint_id": str(key_id)}
    assert run_matches_origin(run(payload=payload), key)
    assert not run_matches_origin(run(payload={"api_key_id": str(key_id)}), other_key)
    # ... but payload evidence alone is not a platform-chat binding either.
    assert not run_matches_origin(run(payload={"api_key_id": str(key_id)}))

    # Runs without a payload, or with unreadable evidence, carry no credential.
    for payload in (None, {"api_key_id": "not-a-uuid"}):
        unreadable = type("Run", (), {"api_key_id": None, "worker_payload": payload})()
        assert run_matches_origin(unreadable)
        assert not run_matches_origin(unreadable, key)


# ============ Conversation creation and continuation ============


@pytest.mark.asyncio
async def test_continuing_a_conversation_stays_on_its_own_surface():
    async with _database():
        owner = await _user("origin-owner")
        team = await _team("origin-team", owner)
        agent = await _agent(team, owner, "origin-agent")
        key = await _api_key(owner, agents=[agent])
        other_key = await _api_key(owner, agents=[agent])

        platform = await chat_endpoints.get_or_create_conversation(
            agent, owner, None, {}
        )
        keyed = await chat_endpoints.get_or_create_conversation(
            agent, owner, None, {}, key
        )
        assert platform.api_key_id is None
        assert keyed.api_key_id == key.id
        assert keyed.api_key_origin_unknown is False

        # Each surface continues its own history.
        assert (
            await chat_endpoints.get_or_create_conversation(
                agent, owner, platform.id, {}
            )
        ).id == platform.id
        assert (
            await chat_endpoints.get_or_create_conversation(
                agent, owner, keyed.id, {}, key
            )
        ).id == keyed.id

        for conversation_id, api_key in (
            (keyed.id, None),
            (platform.id, key),
            (keyed.id, other_key),
        ):
            with pytest.raises(BusinessError) as denied:
                await chat_endpoints.get_or_create_conversation(
                    agent, owner, conversation_id, {}, api_key
                )
            assert denied.value.code == ResponseCode.CONVERSATION_NOT_FOUND
            assert denied.value.status_code == 404

        await Conversation.filter(id=platform.id).update(api_key_origin_unknown=True)
        for api_key in (None, key):
            with pytest.raises(BusinessError):
                await chat_endpoints.get_or_create_conversation(
                    agent, owner, platform.id, {}, api_key
                )


# ============ Chat history reads ============


@pytest.mark.asyncio
async def test_agent_chat_history_lists_only_the_callers_surface():
    async with _database():
        owner = await _user("list-owner", permissions=["conversation:read"])
        team = await _team("list-team", owner)
        agent = await _agent(team, owner, "list-agent")
        key = await _api_key(owner, agents=[agent])
        other_key = await _api_key(owner, agents=[agent])
        await _conversation(agent, owner, title="platform")
        await _conversation(agent, owner, api_key_id=key.id, title="keyed")
        await _conversation(agent, owner, api_key_id=other_key.id, title="other")
        await _conversation(agent, owner, api_key_id=key.id, origin_unknown=True)

        jwt_list = await _list_chat_history(agent.id, (owner, None))
        assert _titles(jwt_list) == {"platform"}

        key_list = await _list_chat_history(agent.id, (owner, key))
        assert _titles(key_list) == {"keyed"}

        # JWT callers need conversation:read; API keys skip RBAC entirely.
        reader = await _user("list-reader")
        with pytest.raises(BusinessError) as denied:
            await agents._history_reader((reader, None))
        assert denied.value.code == ResponseCode.PERMISSION_DENIED
        assert (await agents._history_reader((owner, None)))[0].id == owner.id
        assert (await agents._history_reader((reader, key)))[1].id == key.id

        # A key bound to another agent cannot read this agent's history.
        other_agent = await _agent(team, owner, "list-other-agent")
        foreign_key = await _api_key(owner, agents=[other_agent])
        with pytest.raises(BusinessError) as denied_key:
            await _list_chat_history(agent.id, (owner, foreign_key))
        assert denied_key.value.code == ResponseCode.PERMISSION_DENIED


@pytest.mark.asyncio
async def test_conversation_detail_is_scoped_to_the_callers_surface():
    async with _database():
        owner = await _user("detail-owner", permissions=["conversation:read"])
        team = await _team("detail-team", owner)
        agent = await _agent(team, owner, "detail-agent")
        key = await _api_key(owner, agents=[agent])
        other_key = await _api_key(owner, agents=[agent])
        platform = await _conversation(agent, owner, title="platform")
        await _message(platform, "platform question")
        keyed = await _conversation(agent, owner, api_key_id=key.id, title="keyed")
        await _message(keyed, "keyed question")

        detail = await agents.get_conversation(keyed.id, auth_result=(owner, key))
        assert detail["data"]["title"] == "keyed"
        assert [m["content"] for m in detail["data"]["messages"]] == ["keyed question"]

        detail = await agents.get_conversation(platform.id, auth_result=(owner, None))
        assert detail["data"]["title"] == "platform"

        for conversation, api_key in (
            (keyed.id, None),
            (platform.id, key),
            (keyed.id, other_key),
        ):
            with pytest.raises(BusinessError) as denied:
                await agents.get_conversation(
                    conversation, auth_result=(owner, api_key)
                )
            assert denied.value.code == ResponseCode.CONVERSATION_NOT_FOUND


@pytest.mark.asyncio
async def test_message_mutations_cannot_reach_key_history():
    async with _database():
        owner = await _user("mutate-owner")
        team = await _team("mutate-team", owner)
        agent = await _agent(team, owner, "mutate-agent")
        key = await _api_key(owner, agents=[agent])
        keyed = await _conversation(agent, owner, api_key_id=key.id)
        message = await _message(keyed, "keyed question")

        with pytest.raises(BusinessError) as denied:
            await chat_endpoints.get_message_version_list(agent.id, message.id, owner)
        assert denied.value.code == ResponseCode.FORBIDDEN

        platform = await _conversation(agent, owner)
        own_message = await _message(platform, "platform question")
        versions = await chat_endpoints.get_message_version_list(
            agent.id, own_message.id, owner
        )
        assert [version.id for version in versions["data"]] == [own_message.id]


@pytest.mark.asyncio
async def test_embed_messages_are_bound_to_exactly_one_key(monkeypatch):
    async with _database():
        owner = await _user("embed-owner")
        team = await _team("embed-team", owner)
        agent = await _agent(team, owner, "embed-agent")
        key = await _api_key(owner, agents=[agent])
        other_key = await _api_key(owner, agents=[agent])
        keyed = await _conversation(agent, owner, api_key_id=key.id)
        await _message(keyed, "keyed question")
        platform = await _conversation(agent, owner)

        monkeypatch.setattr(embed, "_get_embed_agent", _returning(agent))

        messages = await embed.get_embed_conversation_messages(
            agent.id, keyed.id, object(), (owner, key)
        )
        assert [m["content"] for m in messages["data"]] == ["keyed question"]

        for conversation_id, api_key in (
            (keyed.id, other_key),
            (platform.id, key),
        ):
            with pytest.raises(BusinessError) as denied:
                await embed.get_embed_conversation_messages(
                    agent.id, conversation_id, object(), (owner, api_key)
                )
            assert denied.value.code == ResponseCode.CONVERSATION_NOT_FOUND


# ============ Agent orchestration logs ============


@pytest.mark.asyncio
async def test_agent_logs_list_and_read_every_origin():
    async with _database():
        owner = await _user("logs-owner", permissions=["conversation:read"])
        team = await _team("logs-team", owner)
        agent = await _agent(team, owner, "logs-agent")
        key = await _api_key(owner, agents=[agent])
        await _conversation(agent, owner, title="platform")
        keyed = await _conversation(agent, owner, api_key_id=key.id, title="keyed")
        await _conversation(
            agent, owner, api_key_id=key.id, origin_unknown=True, title="quarantined"
        )

        listed = await _list_log_history(agent.id, owner)
        assert _titles(listed) == {"platform", "keyed", "quarantined"}
        filtered = await _list_log_history(agent.id, owner, key.id)
        assert _titles(filtered) == {"keyed", "quarantined"}
        assert _titles(await _list_log_history(agent.id, owner, uuid4())) == set()

        detail = await agents.get_agent_log_conversation(
            agent.id, keyed.id, current_user=owner
        )
        assert detail["data"]["title"] == "keyed"

        # The chat surface still refuses the same conversation.
        with pytest.raises(BusinessError):
            await agents.get_conversation(keyed.id, auth_result=(owner, None))


@pytest.mark.asyncio
async def test_admin_key_filter_respects_accessible_teams():
    async with _database():
        owner = await _user("admin-filter-owner")
        outsider = await _user("admin-filter-outsider")
        team = await _team("admin-filter-team", owner)
        agent = await _agent(team, owner, "admin-filter-agent")
        key = await _api_key(owner, agents=[agent])
        await _conversation(agent, owner, title="web")
        await _conversation(agent, owner, api_key_id=key.id, title="keyed")
        kwargs = dict(
            team_id=None,
            agent_id=None,
            user_id=None,
            search=None,
            untitled_only=False,
            page=1,
            page_size=20,
            api_key_id=key.id,
        )
        assert _titles(
            await admin_conversations.list_all_conversations(
                current_user=owner, **kwargs
            )
        ) == {"keyed"}
        assert (
            _titles(
                await admin_conversations.list_all_conversations(
                    current_user=outsider, **kwargs
                )
            )
            == set()
        )


@pytest.mark.asyncio
async def test_agent_log_delete_reaches_key_origin_conversations():
    async with _database():
        owner = await _user("log-delete-owner", permissions=["conversation:delete"])
        team = await _team("log-delete-team", owner)
        agent = await _agent(team, owner, "log-delete-agent")
        key = await _api_key(owner, agents=[agent])
        keyed = await _conversation(agent, owner, api_key_id=key.id)

        with pytest.raises(BusinessError):
            await agents.delete_conversation(keyed.id, current_user=owner)

        deleted = await agents.delete_agent_log_conversation(
            agent.id, keyed.id, current_user=owner
        )
        assert deleted["data"]["id"] == str(keyed.id)
        assert await Conversation.filter(id=keyed.id).exists() is False
        refreshed = await Agent.get(id=agent.id)
        assert refreshed.conversation_count == 0
        assert refreshed.message_count == 0


def _returning(value):
    """Async replacement for a coroutine function returning ``value``."""

    async def _fake(*_args, **_kwargs):
        return value

    return _fake


# ============ Session gate and edge cases ============


@pytest.mark.asyncio
async def test_inactive_session_cannot_read_chat_history():
    """A login that is no longer active is rejected before any RBAC check."""
    async with _database():
        owner = await _user("inactive-reader", permissions=["conversation:read"])
        await User.filter(id=owner.id).update(is_active=False)
        inactive = await User.get(id=owner.id)

        with pytest.raises(BusinessError) as denied:
            await agents._history_reader((inactive, None))

        assert denied.value.code == ResponseCode.INACTIVE_USER
        # The same user's API key is not gated by the session's active flag.
        key = await _api_key(inactive)
        assert (await agents._history_reader((inactive, key)))[1].id == key.id


@pytest.mark.asyncio
async def test_key_detail_hides_a_conversation_whose_agent_is_gone():
    """Without its Agent a key-bound conversation has no scope to authorize."""
    async with _database():
        owner = await _user("orphan-owner")
        team = await _team("orphan-team", owner)
        agent = await _agent(team, owner, "orphan-agent")
        key = await _api_key(owner, agents=[agent])
        orphan = await Conversation.create(
            id=uuid4(),
            agent_id=None,
            user_id=owner.id,
            title="orphan",
            api_key_id=key.id,
        )

        with pytest.raises(BusinessError) as denied:
            await agents.get_conversation(orphan.id, auth_result=(owner, key))

        assert denied.value.code == ResponseCode.CONVERSATION_NOT_FOUND
        # The log surface still reads it, because it only scopes owner+agent.
        with pytest.raises(BusinessError):
            await agents.get_agent_log_conversation(
                agent.id, orphan.id, current_user=owner
            )


@pytest.mark.asyncio
async def test_agent_log_routes_hide_unknown_conversations():
    """Log read and delete stay scoped to the named Agent and its owner."""
    async with _database():
        owner = await _user("log-missing-owner", permissions=["conversation:read"])
        team = await _team("log-missing-team", owner)
        agent = await _agent(team, owner, "log-missing-agent")
        other_agent = await _agent(team, owner, "log-missing-other")
        conversation = await _conversation(agent, owner)

        with pytest.raises(BusinessError) as missing_read:
            await agents.get_agent_log_conversation(
                other_agent.id, conversation.id, current_user=owner
            )
        assert missing_read.value.code == ResponseCode.CONVERSATION_NOT_FOUND

        with pytest.raises(BusinessError) as missing_delete:
            await agents.delete_agent_log_conversation(
                other_agent.id, conversation.id, current_user=owner
            )
        assert missing_delete.value.code == ResponseCode.CONVERSATION_NOT_FOUND
        assert await Conversation.filter(id=conversation.id).exists() is True


@pytest.mark.asyncio
async def test_attachment_binding_records_the_ref_on_its_own_surface(monkeypatch):
    """A raw attachment id is authorized for this surface and gets its ref."""
    async with _database():
        owner = await _user("attachment-owner")
        team = await _team("attachment-team", owner)
        agent = await _agent(team, owner, "attachment-agent")
        key = await _api_key(owner, agents=[agent])
        asset = SimpleNamespace(id=uuid4())
        binding = SimpleNamespace(ref="conversation:file#1")
        dict_attachment = {"asset_id": str(asset.id)}
        object_attachment = SimpleNamespace(asset_id=str(asset.id), asset_ref=None)
        authorize = AsyncMock(return_value=asset)
        monkeypatch.setattr(
            "app.services.asset_access.authorize_asset_for_scope", authorize
        )
        monkeypatch.setattr(
            "app.services.asset.asset_service.get_or_create_ref",
            AsyncMock(return_value=binding),
        )

        resolved = await chat_endpoints._resolve_message_assets(
            attachments=[dict_attachment, object_attachment],
            agent=agent,
            user=owner,
            conversation_id=uuid4(),
            api_key=key,
        )

    assert [asset_out for asset_out, _role, _position in resolved] == [asset, asset]
    assert dict_attachment["asset_ref"] == binding.ref
    assert object_attachment.asset_ref == binding.ref
    for call in authorize.await_args_list:
        assert call.kwargs["enforce_history_origin"] is True
        assert call.kwargs["api_key"] is key
