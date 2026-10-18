"""Web chat submission contract tests against an isolated real ORM.

Covers the two web regressions that matter after the shared extraction:

- a multi-turn conversation continues the existing conversation instead of
  creating a new one per turn,
- an API key without access to the agent creates no run at all.
"""

from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio
from tortoise.context import TortoiseContext

from app.models.agent import Agent, AgentStatus, AgentVisibility, Conversation, Message
from app.models.agent_run import AgentRun, AgentRunMode, AgentRunStatus
from app.models.user import Team, User
from app.schemas.agent import ChatRequest
from app.services import agent_submission


class FakeAPIKey:
    def __init__(self, agents):
        self.id = uuid4()
        self.agents = agents


@pytest_asyncio.fixture
async def db():
    async with TortoiseContext() as context:
        await context.init(
            db_url="sqlite://:memory:", modules={"models": ["app.models"]}
        )
        await context.generate_schemas()
        yield


@pytest_asyncio.fixture
async def world(db, monkeypatch):
    user = await User.create(
        id=uuid4(),
        username="chatter",
        email="chatter@example.test",
        hashed_password="unused",
        is_active=True,
    )
    team = await Team.create(id=uuid4(), name="Chat team")
    agent = await Agent.create(
        id=uuid4(),
        name="Chat agent",
        team=team,
        created_by=user,
        status=AgentStatus.PUBLISHED,
        visibility=AgentVisibility.TEAM,
    )
    from app.models.user import TeamMember

    await TeamMember.create(team=team, user=user, role="member")

    published = []
    monkeypatch.setattr(agent_submission, "_publish", _recording_publish(published))
    return SimpleNamespace(user=user, team=team, agent=agent, published=published)


def _recording_publish(published):
    async def publish(run, payload):
        published.append((run.id, payload))
        run.celery_task_id = str(run.id)
        await run.save(update_fields=["celery_task_id"])

    return publish


@pytest.mark.asyncio
async def test_multi_turn_continues_the_same_conversation(world):
    first = await agent_submission.submit_chat_run(
        world.agent.id,
        ChatRequest(message="first"),
        (world.user, None),
        mode=AgentRunMode.SEND,
    )
    second = await agent_submission.submit_chat_run(
        world.agent.id,
        ChatRequest(message="second", conversation_id=first.conversation_id),
        (world.user, None),
        mode=AgentRunMode.SEND,
    )

    assert first.conversation_id == second.conversation_id
    assert await Conversation.all().count() == 1
    assert await AgentRun.all().count() == 2
    assert len(world.published) == 2
    assert (
        await Message.filter(conversation_id=first.conversation_id, role="user").count()
        == 2
    )


@pytest.mark.asyncio
async def test_api_key_without_agent_access_creates_no_run(world):
    from app.schemas.response import BusinessError

    other_agent = await Agent.create(
        id=uuid4(),
        name="Other agent",
        team=world.team,
        created_by=world.user,
        status=AgentStatus.PUBLISHED,
        visibility=AgentVisibility.TEAM,
    )
    key = FakeAPIKey(agents=SimpleNamespace(all=_granting_only(other_agent)))

    with pytest.raises(BusinessError):
        await agent_submission.submit_chat_run(
            world.agent.id,
            ChatRequest(message="hello"),
            (world.user, key),
            mode=AgentRunMode.SEND,
        )

    assert await AgentRun.all().count() == 0
    assert await Message.all().count() == 0
    assert world.published == []


def _granting_only(agent):
    async def granted():
        return [agent]

    return granted


@pytest.mark.asyncio
async def test_deferred_dispatch_publishes_nothing_until_asked(world):
    submission = await agent_submission.submit_chat_run(
        world.agent.id,
        ChatRequest(message="hello"),
        (world.user, None),
        mode=AgentRunMode.SEND,
        defer_dispatch=True,
    )
    assert world.published == []
    queued = await AgentRun.get(id=submission.run_id)
    assert queued.status == AgentRunStatus.QUEUED

    await submission.dispatch()
    assert len(world.published) == 1
    dispatched = await AgentRun.get(id=submission.run_id)
    assert dispatched.celery_task_id == str(submission.run_id)


@pytest.mark.asyncio
async def test_mode_defaults_to_send(world):
    submission = await agent_submission.submit_chat_run(
        world.agent.id,
        ChatRequest(message="hello"),
        (world.user, None),
        defer_dispatch=True,
    )
    submitted = await AgentRun.get(id=submission.run_id)
    assert submitted.mode == AgentRunMode.SEND
