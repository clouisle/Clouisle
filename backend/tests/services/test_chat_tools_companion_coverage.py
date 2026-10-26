"""
Companion branch coverage tests for chat_tools, agent_run_store, rss, and web_search.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
import feedparser
import json
import pytest

from app.api.v1.endpoints.chat_tools import (
    execute_tool_call,
)
from app.models.agent_run import AgentRunInputKind, AgentRunInputStatus, AgentRunStatus
from app.services.agent_run_store import (
    validate_user_answers,
    consume_next_input,
    drop_pending_inputs,
    get_cached_run_status,
    has_pending_inputs,
)
from app.llm.tools.builtin.rss import _clean_html_text, read_rss_feed
from app.llm.tools.builtin.web_search import (
    fetch_webpage,
)


# ==================== chat_tools Database branch ====================
async def _run_invoke(definition, operation, arguments, context, invoke, **_kwargs):
    """Skip persistence but keep the real operation wiring."""
    return await invoke(arguments, None)


@pytest.mark.anyio
async def test_chat_tools_ask_user_and_memory_branches():
    # 1. ask_user call branch
    with patch(
        "app.llm.tools.tool_registry.execute",
        new=AsyncMock(return_value={"asked": True}),
    ) as exec_mock:
        res = await execute_tool_call("ask_user", {"questions": []})
        assert res == {"asked": True}
        exec_mock.assert_awaited_once_with("ask_user", {"questions": []})

    # 2. workflow_run_id reaches the stored builtin boundary
    user = SimpleNamespace(id=uuid4())
    agent = SimpleNamespace(id=uuid4(), team_id=uuid4(), tools_config=[])
    with (
        patch(
            "app.llm.tools.tool_registry.get_tool",
            return_value=SimpleNamespace(handler=lambda: None),
        ),
        patch(
            "app.llm.tools.tool_registry.get_sandbox_tool_class",
            return_value=None,
        ),
        patch(
            "app.services.tool.ToolExecutor.execute_builtin_tool",
            new=AsyncMock(return_value={"done": True}),
        ) as execute,
        patch("app.models.user.User.get_or_none", new=AsyncMock(return_value=user)),
    ):
        await execute_tool_call(
            "time",
            {},
            agent=agent,
            user=user,
            workflow_run_id="wf-123",
        )
    assert execute.await_args.kwargs["workflow_run_id"] == "wf-123"

    # 3. memory subgraph with non-list entity_ids and relation_types
    user = SimpleNamespace(id=uuid4())
    agent = SimpleNamespace(id=uuid4(), team_id=uuid4())
    with (
        patch(
            "app.services.memory.MemoryService.handle_get_memory_subgraph",
            new=AsyncMock(return_value={"nodes": []}),
        ) as mem_mock,
        patch(
            "app.services.tool_execution.execute_stored_tool",
            new=_run_invoke,
        ),
        patch(
            "app.services.builtin_tools.get_builtin_definition",
            new=AsyncMock(return_value=SimpleNamespace(id=uuid4(), name="definition")),
        ),
        patch("app.models.user.User.get_or_none", new=AsyncMock(return_value=user)),
    ):
        res = await execute_tool_call(
            "get_memory_subgraph",
            {
                "action": "get_subgraph",
                "entity_ids": "not_list",
                "relation_types": "not_list",
                "max_depth": "99",
            },
            user=user,
            agent=agent,
        )
        data = json.loads(res)
        assert data["nodes"] == []
        mem_mock.assert_awaited_once()
        assert mem_mock.call_args.kwargs["entity_ids"] == []
        assert mem_mock.call_args.kwargs["relation_types"] is None
        assert mem_mock.call_args.kwargs["max_depth"] == 3


# ==================== agent_run_store ask_user validation ====================
def test_validate_ask_user_answer_branches():
    # pending_input not dict
    with pytest.raises(ValueError, match="pending questions are invalid"):
        validate_user_answers("not_dict", {})

    # questions not list
    with pytest.raises(ValueError, match="pending questions are invalid"):
        validate_user_answers({"questions": "none"}, {})

    # answers not dict
    with pytest.raises(ValueError, match="answers must be an object"):
        validate_user_answers(
            {"questions": [{"id": "q1", "question": "What?"}]}, "not_dict"
        )

    # skipped not bool
    with pytest.raises(ValueError, match="skipped must be a boolean"):
        validate_user_answers(
            {"questions": [{"id": "q1", "question": "What?"}]}, {}, skipped="true"
        )  # type: ignore

    # item in questions not dict
    with pytest.raises(ValueError, match="pending questions are invalid"):
        validate_user_answers({"questions": ["not_a_dict"]}, {})

    # question_id invalid
    with pytest.raises(ValueError, match="pending questions are invalid"):
        validate_user_answers({"questions": [{"id": "", "question": "What?"}]}, {})

    # duplicate question_id
    with pytest.raises(ValueError, match="pending questions are invalid"):
        validate_user_answers(
            {
                "questions": [
                    {"id": "q1", "question": "Q1"},
                    {"id": "q1", "question": "Q2"},
                ]
            },
            {},
        )

    # question text invalid
    with pytest.raises(ValueError, match="pending questions are invalid"):
        validate_user_answers({"questions": [{"id": "q1", "question": ""}]}, {})

    # options invalid
    with pytest.raises(ValueError, match="pending questions are invalid"):
        validate_user_answers(
            {"questions": [{"id": "q1", "question": "What?", "options": [123]}]}, {}
        )

    # required not bool
    with pytest.raises(ValueError, match="pending questions are invalid"):
        validate_user_answers(
            {"questions": [{"id": "q1", "question": "What?", "required": "yes"}]}, {}
        )

    # skipped with non-empty answers
    with pytest.raises(ValueError, match="skipped answers must be empty"):
        validate_user_answers(
            {"questions": [{"id": "q1", "question": "What?"}]},
            {"q1": "ans"},
            skipped=True,
        )

    # skipped happy path
    validate_user_answers(
        {"questions": [{"id": "q1", "question": "What?"}]}, {}, skipped=True
    )

    # unknown question id in answers
    with pytest.raises(ValueError, match="answers contain an unknown question id"):
        validate_user_answers(
            {"questions": [{"id": "q1", "question": "What?"}]}, {"q2": "ans"}
        )

    # required question missing
    with pytest.raises(ValueError, match="answer required for q1"):
        validate_user_answers(
            {"questions": [{"id": "q1", "question": "What?", "required": True}]},
            {"q1": ""},
        )

    # optional question with options and invalid non-string answer
    with pytest.raises(ValueError, match="answer must be a non-empty string for q1"):
        validate_user_answers(
            {
                "questions": [
                    {
                        "id": "q1",
                        "question": "What?",
                        "required": False,
                        "options": ["A", "B"],
                    }
                ]
            },
            {"q1": 123},
        )

    # optional question with empty answer passes
    validate_user_answers(
        {
            "questions": [
                {
                    "id": "q1",
                    "question": "What?",
                    "required": False,
                    "options": ["A", "B"],
                }
            ]
        },
        {"q1": ""},
    )

    # valid required answer
    validate_user_answers(
        {
            "questions": [
                {
                    "id": "q1",
                    "question": "What?",
                    "required": True,
                    "options": ["A", "B"],
                }
            ]
        },
        {"q1": "A"},
    )


@pytest.mark.anyio
async def test_agent_run_store_pending_inputs_branches():
    run_id = uuid4()

    # 1. consume_next_input: none vs entry
    with patch("app.models.agent_run.AgentRunInput.filter") as filter_mock:
        order_mock = MagicMock()
        order_mock.first = AsyncMock(return_value=None)
        filter_mock.return_value.order_by.return_value = order_mock

        assert await consume_next_input(run_id) is None

        fake_entry = SimpleNamespace(status=None, consumed_at=None, save=AsyncMock())
        order_mock.first = AsyncMock(return_value=fake_entry)
        consumed = await consume_next_input(run_id)
        assert consumed is fake_entry
        assert consumed.status == AgentRunInputStatus.CONSUMED

    # 2. drop_pending_inputs: empty vs entries
    with patch("app.models.agent_run.AgentRunInput.filter") as filter_mock:
        query_mock = MagicMock()
        query_mock.all = AsyncMock(return_value=[])
        filter_mock.return_value = query_mock
        assert await drop_pending_inputs(run_id) == 0

        e1 = SimpleNamespace(status=None, consumed_at=None, save=AsyncMock())
        e2 = SimpleNamespace(status=None, consumed_at=None, save=AsyncMock())
        query_mock.all = AsyncMock(return_value=[e1, e2])
        assert await drop_pending_inputs(run_id) == 2
        assert e1.status == AgentRunInputStatus.DROPPED
        assert e2.status == AgentRunInputStatus.DROPPED

    # 3. get_cached_run_status
    with patch("app.services.agent_run_store.get_redis") as redis_mock:
        redis = AsyncMock()
        redis_mock.return_value = redis

        redis.get.return_value = None
        assert await get_cached_run_status(run_id) is None

        redis.get.return_value = json.dumps({"status": "running"})
        assert await get_cached_run_status(run_id) == AgentRunStatus.RUNNING

    # 4. has_pending_inputs with and without kind
    with patch("app.models.agent_run.AgentRunInput.filter") as filter_mock:
        qs_mock = MagicMock()
        qs_mock.exists = AsyncMock(return_value=True)
        filter_mock.return_value = qs_mock
        assert await has_pending_inputs(run_id) is True

        qs_mock.filter.return_value = qs_mock
        assert await has_pending_inputs(run_id, kind=AgentRunInputKind.STEER) is True
        qs_mock.filter.assert_called_once_with(kind=AgentRunInputKind.STEER)


# ==================== rss and web_search branch tests ====================
def test_clean_html_text_branches():
    assert _clean_html_text(None) == ""
    assert _clean_html_text("") == ""
    assert _clean_html_text("<p>Hello &amp; World</p>") == "Hello & World"


@pytest.mark.anyio
async def test_read_rss_feed_branches():
    mock_resp = MagicMock()
    mock_resp.content = b"<xml>broken</xml>"
    mock_resp.status_code = 200

    with patch("httpx.AsyncClient") as mock_client_cls:
        client = AsyncMock()
        client.get.return_value = mock_resp
        client.__aenter__.return_value = client
        mock_client_cls.return_value = client

        # 1. Bozo error
        bozo_feed = SimpleNamespace(
            bozo=1, entries=[], feed={}, get=lambda k, d=None: "syntax error"
        )
        with patch("feedparser.parse", return_value=bozo_feed):
            res = await read_rss_feed("https://feed.org/rss")
            assert res["success"] is False

        # 2. Rich entries
        entry_dict = {
            "title": "Post 1",
            "link": "https://tech.blog/p1",
            "published": "2026-01-01",
            "author": "John",
            "summary": "",
            "description": "",
            "content": [{"value": "<b>Full post</b>"}],
        }
        rich_feed = SimpleNamespace(
            bozo=0,
            entries=[feedparser.FeedParserDict(entry_dict)],
            get=lambda k, d=None: (
                {
                    "title": "Tech Blog",
                    "link": "https://tech.blog",
                    "description": "<p>Daily updates</p>",
                }
                if k == "feed"
                else d
            ),
        )
        with patch("feedparser.parse", return_value=rich_feed):
            res2 = await read_rss_feed("https://tech.blog/rss")
            assert res2["success"] is True
            assert res2["feed_title"] == "Tech Blog"
            assert res2["feed_description"] == "Daily updates"
            assert len(res2["articles"]) == 1
            assert res2["articles"][0]["summary"] == "Full post"
            assert res2["articles"][0]["author"] == "John"


@pytest.mark.anyio
async def test_web_search_and_fetch_webpage_branches():
    # 3. fetch_webpage persists a complete non-HTML document
    from app.services import asset_url_import
    from app.schemas.response import BusinessError

    preview = {
        "filename": "payload.txt",
        "start_line": 1,
        "total_lines": 1,
        "segments": [{"line": 1, "text": "A" * 100, "continuation": False}],
        "next_cursor": None,
        "eof": True,
    }
    persisted = SimpleNamespace(asset=SimpleNamespace(id=uuid4()), ref="abcd")
    with (
        patch.object(
            asset_url_import,
            "resolve_document_scope",
            return_value=(asset_url_import.AssetScopeType.CONVERSATION, uuid4()),
        ),
        patch.object(
            asset_url_import,
            "load_url_document",
            new=AsyncMock(
                return_value=asset_url_import.ExternalDocument(
                    content=b"A" * 100,
                    content_type="text/plain",
                    filename="payload.txt",
                    url="data:text/plain;base64,abc",
                    final_url="data:text/plain;base64,abc",
                )
            ),
        ),
        patch.object(
            asset_url_import,
            "persist_scoped_document",
            new=AsyncMock(return_value=persisted),
        ) as persist,
        patch(
            "app.llm.tools.builtin.web_search._read_preview",
            new=AsyncMock(return_value=preview),
        ),
    ):
        res_doc = await fetch_webpage("data:text/plain;base64,abc")
        assert res_doc["success"] is True
        assert res_doc["segments"][0]["text"] == "A" * 100
        assert persist.await_args.args[0] == b"A" * 100

    # 4. fetch_webpage rejects unsupported schemes without network IO
    with (
        patch.object(
            asset_url_import,
            "resolve_document_scope",
            return_value=(asset_url_import.AssetScopeType.CONVERSATION, uuid4()),
        ),
        patch.object(
            asset_url_import,
            "load_url_document",
            new=AsyncMock(
                side_effect=BusinessError(msg_key="fetch_webpage_unsupported_scheme")
            ),
        ),
    ):
        res_err = await fetch_webpage("file:///restricted.pdf")
        assert res_err["success"] is False

    # 5. fetch_webpage maps HTTP failures
    with (
        patch.object(
            asset_url_import,
            "resolve_document_scope",
            return_value=(asset_url_import.AssetScopeType.CONVERSATION, uuid4()),
        ),
        patch.object(
            asset_url_import,
            "load_url_document",
            new=AsyncMock(
                side_effect=BusinessError(
                    msg_key="fetch_webpage_http_error", status_code=404
                )
            ),
        ),
    ):
        res_404 = await fetch_webpage("https://example.com/notfound")
        assert res_404["success"] is False
        assert "404" in res_404["error"]

    # 6. fetch_webpage returns the bounded preview and continuation fields
    preview = dict(
        preview,
        filename="article.md",
        total_lines=40,
        next_cursor="next",
        eof=False,
    )
    with (
        patch.object(
            asset_url_import,
            "resolve_document_scope",
            return_value=(asset_url_import.AssetScopeType.CONVERSATION, uuid4()),
        ),
        patch.object(
            asset_url_import,
            "load_url_document",
            new=AsyncMock(
                return_value=asset_url_import.ExternalDocument(
                    content=b"<html><body>Long article text here</body></html>",
                    content_type="text/html",
                    filename="article",
                    url="https://example.com/article",
                    final_url="https://example.com/article",
                )
            ),
        ),
        patch.object(
            asset_url_import,
            "persist_scoped_document",
            new=AsyncMock(return_value=persisted),
        ),
        patch(
            "app.llm.tools.builtin.web_search._extract_readable_content",
            return_value=("Extracted " * 20, "Title"),
        ),
        patch(
            "app.llm.tools.builtin.web_search._read_preview",
            new=AsyncMock(return_value=preview),
        ),
    ):
        res_doc = await fetch_webpage("https://example.com/article")
        assert res_doc["success"] is True
        assert res_doc["next_cursor"] == "next"
        assert res_doc["eof"] is False
        assert res_doc["total_lines"] == 40
