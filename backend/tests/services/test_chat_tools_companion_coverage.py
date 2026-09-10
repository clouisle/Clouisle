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
    _get_builtin_tool_credentials,
)
from app.models.agent_run import AgentRunInputKind, AgentRunInputStatus, AgentRunStatus
from app.models.tool import CustomToolType, ToolType
from app.services.agent_run_store import (
    validate_user_answers,
    consume_next_input,
    drop_pending_inputs,
    get_cached_run_status,
    has_pending_inputs,
)
from app.llm.tools.builtin.rss import _clean_html_text, read_rss_feed
from app.llm.tools.builtin.web_search import (
    _clean_ddg_href,
    _parse_ddg_html,
    web_search,
    fetch_webpage,
)


# ==================== chat_tools Database branch ====================
@pytest.mark.anyio
async def test_execute_tool_call_database_custom_type():
    tool = SimpleNamespace(
        id=uuid4(),
        name="my_db_tool",
        type=ToolType.CUSTOM,
        custom_type=CustomToolType.DATABASE,
        database_config={"db_type": "postgresql", "host": "127.0.0.1"},
    )
    agent = SimpleNamespace(id=uuid4(), team_id=uuid4(), tools_config=[])

    with patch("app.models.tool.Tool.filter") as tool_filter:
        query = MagicMock()
        query.first = AsyncMock(return_value=tool)
        tool_filter.return_value = query

        with patch(
            "app.llm.tools.builtin.db_executor.execute_database_tool",
            new=AsyncMock(return_value={"tables": ["users"], "success": True}),
        ):
            res_str = await execute_tool_call(
                "custom_my_db_tool", {"action": "schema"}, agent=agent
            )
            data = json.loads(res_str)
            assert data["success"] is True
            assert data["tables"] == ["users"]

        # Error branch in custom database execution
        with patch(
            "app.llm.tools.builtin.db_executor.execute_database_tool",
            side_effect=RuntimeError("connection dropped"),
        ):
            err_str = await execute_tool_call(
                "custom_my_db_tool", {"action": "schema"}, agent=agent
            )
            err_data = json.loads(err_str)
            assert "error" in err_data


@pytest.mark.anyio
async def test_get_builtin_tool_credentials_branches():
    # 1. agent.tools_config override with api_key and engine
    agent = SimpleNamespace(
        tools_config=[
            {
                "name": "web_search",
                "config": {
                    "api_key": "bocha_key",
                    "engine": "bocha",
                    "TAVILY_API_KEY": "t_key",
                },
            }
        ]
    )
    with patch("app.models.tool_config.ToolConfig.filter") as mock_filter:
        team_q = MagicMock()
        team_q.first = AsyncMock(return_value=None)
        mock_filter.return_value = team_q

        creds = await _get_builtin_tool_credentials(
            "web_search", agent=agent, agent_tool_config=agent.tools_config[0]["config"]
        )
        assert creds["BOCHA_API_KEY"] == "bocha_key"
        assert creds["TAVILY_API_KEY"] == "t_key"

    # 2. agent.tools_config override with engine = tavily
    agent_tavily = SimpleNamespace(
        tools_config=[
            {
                "name": "web_search",
                "config": {"api_key": "tavily_key", "engine": "tavily"},
            }
        ]
    )
    with patch("app.models.tool_config.ToolConfig.filter") as mock_filter:
        team_q = MagicMock()
        team_q.first = AsyncMock(return_value=None)
        mock_filter.return_value = team_q

        creds = await _get_builtin_tool_credentials(
            "web_search",
            agent=agent_tavily,
            agent_tool_config=agent_tavily.tools_config[0]["config"],
        )
        assert creds["TAVILY_API_KEY"] == "tavily_key"


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

    # 2. workflow_run_id branch
    with (
        patch(
            "app.llm.tools.tool_registry.get_tool",
            return_value=SimpleNamespace(handler=lambda: None),
        ),
        patch(
            "app.llm.tools.tool_registry.execute",
            new=AsyncMock(return_value={"done": True}),
        ) as exec_mock,
    ):
        await execute_tool_call(
            "time",
            {},
            workflow_run_id="wf-123",
        )
        assert exec_mock.call_args.kwargs["workflow_run_id"] == "wf-123"

    # 3. memory subgraph with non-list entity_ids and relation_types
    with patch(
        "app.services.memory.MemoryService.handle_get_memory_subgraph",
        new=AsyncMock(return_value={"nodes": []}),
    ) as mem_mock:
        res = await execute_tool_call(
            "get_memory_subgraph",
            {
                "action": "get_subgraph",
                "entity_ids": "not_list",
                "relation_types": "not_list",
                "max_depth": "99",
            },
            user=SimpleNamespace(id=uuid4()),
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
def test_clean_html_text_and_ddg_href_branches():
    assert _clean_html_text(None) == ""
    assert _clean_html_text("") == ""
    assert _clean_html_text("<p>Hello &amp; World</p>") == "Hello & World"

    assert _clean_ddg_href(None) == ""
    assert _clean_ddg_href("") == ""
    assert _clean_ddg_href("//example.com/path") == "https://example.com/path"
    assert (
        _clean_ddg_href(
            "https://duckduckgo.com/l/?uddg=https%3A%2F%2Ftarget.org%2Fpage&rut=1"
        )
        == "https://target.org/page"
    )


def test_parse_ddg_html_branches():
    html_sample = """
    <div class="result badge--ad">Sponsored Ad</div>
    <div class="result"><div class="no-anchor">No link</div></div>
    <div class="result"><a class="result__a" href="javascript:void(0)">JS link</a></div>
    <div class="result">
        <a class="result__a" href="https://news.ycombinator.com">Hacker News</a>
        <div class="result__snippet">Tech news and discussions</div>
    </div>
    <div class="result">
        <a class="result__a" href="https://example.com">Example</a>
        <a class="result__snippet" href="https://example.com">Example snippet</a>
    </div>
    """
    results = _parse_ddg_html(html_sample, max_results=1)
    assert len(results) == 1
    assert results[0]["title"] == "Hacker News"
    assert results[0]["url"] == "https://news.ycombinator.com"
    assert results[0]["content"] == "Tech news and discussions"


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
    # 1. web_search auto fallback: tavily fails -> duckduckgo succeeds
    with (
        patch(
            "app.llm.tools.builtin.web_search._tavily_search",
            new=AsyncMock(return_value={"success": False}),
        ),
        patch(
            "app.llm.tools.builtin.web_search._duckduckgo_search",
            new=AsyncMock(
                return_value={"success": True, "results": [{"title": "DDG"}]}
            ),
        ),
    ):
        res = await web_search("python", search_engine="auto")
        assert res["success"] is True
        assert res["search_engine"] == "duckduckgo"

    # 2. web_search bocha without api_key
    res_bocha = await web_search("python", search_engine="bocha", credentials={})
    assert res_bocha["success"] is False
    assert "Bocha API key is not configured" in str(res_bocha.get("error", ""))

    # 3. fetch_webpage non-http URL truncation
    fake_conv = SimpleNamespace(text_content="A" * 100, title="Doc")
    with patch("markitdown.MarkItDown.convert", return_value=fake_conv):
        res_doc = await fetch_webpage("data:text/plain;base64,abc", max_length=10)
        assert res_doc["success"] is True
        assert len(res_doc["content"]) == 13  # 10 chars + '...'

    # 4. fetch_webpage non-http with response status code error
    class CustomErr(Exception):
        response = SimpleNamespace(status_code=403)

    with patch("markitdown.MarkItDown.convert", side_effect=CustomErr("forbidden")):
        res_err = await fetch_webpage("file:///restricted.pdf")
        assert res_err["success"] is False

    # 5. fetch_webpage http 404
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    with patch("httpx.AsyncClient") as mock_client_cls:
        client = AsyncMock()
        client.get.return_value = mock_resp
        client.__aenter__.return_value = client
        mock_client_cls.return_value = client

        res_404 = await fetch_webpage("https://example.com/notfound")
        assert res_404["success"] is False

    # 6. fetch_webpage http success with max_length truncation
    mock_resp_ok = MagicMock()
    mock_resp_ok.status_code = 200
    mock_resp_ok.text = "<html><body>Long article text here</body></html>"
    with patch("httpx.AsyncClient") as mock_client_cls:
        client = AsyncMock()
        client.get.return_value = mock_resp_ok
        client.__aenter__.return_value = client
        mock_client_cls.return_value = client

        with patch(
            "app.llm.tools.builtin.web_search._extract_readable_content",
            return_value=("Extracted " * 20, "Title"),
        ):
            res_trunc = await fetch_webpage(
                "https://example.com/article", max_length=15
            )
            assert res_trunc["success"] is True
            assert res_trunc["content"].endswith("...")
