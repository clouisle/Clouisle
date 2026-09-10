"""
Tests for multi-engine web search (auto, bocha, duckduckgo, tavily).
"""

from unittest.mock import AsyncMock
import pytest

from app.llm.tools.builtin import web_search as subject
from app.services.citations import stable_citation_id


@pytest.mark.anyio
async def test_web_search_auto_routes_to_tavily_when_tavily_key_present(monkeypatch):
    tavily_mock = AsyncMock(
        return_value={"success": True, "results": [{"title": "Tavily result"}]}
    )
    monkeypatch.setattr(subject, "_tavily_search", tavily_mock)

    res = await subject.web_search(
        "test query", credentials={"TAVILY_API_KEY": "tvly-123"}
    )
    assert res["success"] is True
    tavily_mock.assert_awaited_once_with(
        "test query", 5, {"TAVILY_API_KEY": "tvly-123"}
    )


@pytest.mark.anyio
async def test_web_search_auto_routes_to_bocha_when_bocha_key_present(monkeypatch):
    bocha_mock = AsyncMock(
        return_value={"success": True, "results": [{"title": "Bocha result"}]}
    )
    monkeypatch.setattr(subject, "_bocha_search", bocha_mock)

    res = await subject.web_search(
        "test query", credentials={"BOCHA_API_KEY": "sk-bocha-123"}
    )
    assert res["success"] is True
    bocha_mock.assert_awaited_once_with(
        "test query", 5, {"BOCHA_API_KEY": "sk-bocha-123"}
    )


@pytest.mark.anyio
async def test_web_search_auto_falls_back_to_duckduckgo_when_no_keys(monkeypatch):
    ddg_mock = AsyncMock(
        return_value={"success": True, "results": [{"title": "DDG result"}]}
    )
    monkeypatch.setattr(subject, "_duckduckgo_search", ddg_mock)

    res = await subject.web_search("test query", credentials={})
    assert res["success"] is True
    ddg_mock.assert_awaited_once_with("test query", 5)


@pytest.mark.anyio
async def test_web_search_auto_falls_back_to_duckduckgo_when_tavily_fails(monkeypatch):
    tavily_mock = AsyncMock(return_value={"success": False, "error": "api_error"})
    ddg_mock = AsyncMock(
        return_value={"success": True, "results": [{"title": "Fallback DDG result"}]}
    )
    monkeypatch.setattr(subject, "_tavily_search", tavily_mock)
    monkeypatch.setattr(subject, "_duckduckgo_search", ddg_mock)

    res = await subject.web_search(
        "test query", search_engine="auto", credentials={"TAVILY_API_KEY": "bad_key"}
    )
    assert res["success"] is True
    assert res["results"][0]["title"] == "Fallback DDG result"
    ddg_mock.assert_awaited_once_with("test query", 5)


@pytest.mark.anyio
async def test_bocha_search_posts_and_normalizes_results(monkeypatch):
    bocha_response_data = {
        "code": 200,
        "data": {
            "webPages": {
                "value": [
                    {
                        "name": "Bocha Article",
                        "url": "https://example.com/bocha",
                        "snippet": "This is snippet from Bocha",
                    }
                ]
            }
        },
    }

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return bocha_response_data

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, headers=None, json=None):
            assert "Bearer sk-bocha" in headers.get("Authorization", "")
            assert json.get("query") == "ai tech"
            return FakeResponse()

    monkeypatch.setattr(subject.httpx, "AsyncClient", lambda **kwargs: FakeClient())

    result = await subject._bocha_search("ai tech", 3, {"BOCHA_API_KEY": "sk-bocha"})
    assert result["success"] is True
    assert len(result["results"]) == 1
    assert result["results"][0]["title"] == "Bocha Article"
    assert result["results"][0]["url"] == "https://example.com/bocha"
    assert result["results"][0]["citation_id"] == stable_citation_id(
        "web", "https://example.com/bocha", ""
    )


@pytest.mark.anyio
async def test_duckduckgo_search_normalizes_results(monkeypatch):
    ddg_raw = [
        {
            "title": "DDG Title",
            "href": "https://duckduckgo.com/example",
            "body": "DDG Body snippet",
        }
    ]

    monkeypatch.setattr(subject, "_sync_ddg_search", lambda query, num_results: ddg_raw)

    result = await subject._duckduckgo_search("privacy search", 2)
    assert result["success"] is True
    assert len(result["results"]) == 1
    assert result["results"][0]["title"] == "DDG Title"
    assert result["results"][0]["url"] == "https://duckduckgo.com/example"
    assert result["results"][0]["content"] == "DDG Body snippet"
    assert result["results"][0]["citation_id"] == stable_citation_id(
        "web", "https://duckduckgo.com/example", ""
    )
