import json
from datetime import UTC, datetime
from uuid import uuid4

from app.schemas.agent import MessageOut, MessageRoundStep
from app.utils.tool_output import (
    ToolExecutionResult,
    get_tool_execution_payloads,
    json_output,
    persistable_model_result,
    persisted_tool_output_parts,
    render_tool_output,
    unwrap_persisted_display,
)


def _segment(line: int, text: str, **extra) -> dict:
    return {"line": line, "text": text, **extra}


def test_unknown_payloads_keep_every_field_type_and_whitespace():
    payload = {
        "custom": "line1\nline2",
        "nested": {"a": [1, 2], "flag": True},
        "none": None,
    }
    original = json.dumps(payload)

    display, llm = get_tool_execution_payloads(original, "custom_http_tool")

    assert display == original
    assert llm == original
    assert json.loads(llm) == payload


def test_unknown_string_results_are_byte_identical():
    result = '{ "custom": "kept  exactly", "unicode": "中文" }'

    assert get_tool_execution_payloads(result, "mcp_server_tool") == (result, result)
    assert get_tool_execution_payloads(result, None) == (result, result)


def test_structured_results_expose_display_and_explicit_model_text():
    result = ToolExecutionResult(
        display_result={"ref": "A1", "nested": {"count": 2}},
        llm_result="explicit summary",
    )

    display, llm = get_tool_execution_payloads(result, "read_asset")

    assert json.loads(display) == {"ref": "A1", "nested": {"count": 2}}
    assert llm == "explicit summary"


def test_read_document_renders_bounded_lines_refs_and_exact_cursor():
    payload = {
        "ref": "A1B2",
        "citation_id": "asset_abc123",
        "filename": "report.txt",
        "start_line": 4,
        "total_lines": 10,
        "segments": [
            _segment(4, "hello"),
            _segment(5, "a" * 5000, continuation=True),
            _segment(6, "世界"),
        ],
        "next_cursor": "v1.cursor+/= with spaces",
        "eof": False,
    }

    rendered = render_tool_output("read_asset", payload)

    assert "ref=A1B2" in rendered
    assert "citation_id=asset_abc123" in rendered
    assert "lines 4–6/10" in rendered
    assert "5│" + "a" * 5000 + " [line continues]" in rendered
    assert "6│世界" in rendered
    assert "cursor=v1.cursor+/= with spaces" in rendered
    assert payload["next_cursor"] == "v1.cursor+/= with spaces"


def test_search_merges_overlapping_context_and_preserves_clip_flags():
    payload = {
        "ref": "A1",
        "citation_id": "asset_x",
        "filename": "doc.txt",
        "query": "beta",
        "total_lines": 5,
        "matches": [
            {
                "line": 2,
                "text": "beta",
                "match_start": 0,
                "match_end": 4,
                "truncated": False,
                "context": [
                    _segment(1, "clipped head", truncated=True),
                    _segment(3, "gamma", truncated=False),
                ],
            },
            {
                "line": 3,
                "text": "gamma full match",
                "match_start": 6,
                "match_end": 10,
                "truncated": False,
                "context": [_segment(2, "be", truncated=True)],
            },
        ],
        "next_cursor": "cursor::raw",
        "eof": False,
    }

    rendered = render_tool_output("search_asset", payload)

    assert rendered.count("1│clipped head") == 1
    assert "1│clipped head [line clipped]" in rendered
    # Each hit keeps its own snippet, even when it shares a line/context.
    assert rendered.count("2│beta") == 1
    assert rendered.count("3│gamma full match") == 1
    assert "<search context>" in rendered
    assert "cursor=cursor::raw" in rendered
    assert payload["matches"][1]["context"][0]["truncated"] is True


def test_search_truncated_match_keeps_clipped_marker():
    payload = {
        "matches": [
            {
                "line": 2,
                "text": "hana",
                "match_start": 0,
                "match_end": 4,
                "truncated": True,
                "context": [],
            }
        ],
        "eof": True,
    }

    rendered = render_tool_output("search_asset", payload)

    assert "snippet clipped; read this line" in rendered
    assert "2│hana [line clipped]" in rendered
    assert "End of results." in rendered


def test_search_keeps_every_hit_on_the_same_line():
    payload = {
        "matches": [
            {
                "line": 7,
                "text": "foo ... foo",
                "match_start": 0,
                "match_end": 3,
                "truncated": False,
                "context": [],
            },
            {
                "line": 7,
                "text": "foo ... foo",
                "match_start": 8,
                "match_end": 11,
                "truncated": False,
                "context": [],
            },
        ],
        "eof": True,
    }

    rendered = render_tool_output("search_asset", payload)

    assert rendered.count("7│foo ... foo") == 2
    assert rendered.count("Match line 7") == 2
    assert "columns 0–3" in rendered
    assert "columns 8–11" in rendered


def test_list_assets_keeps_action_metadata_and_pagination():
    payload = {
        "items": [
            {
                "ref": "A1",
                "name": "chart.png",
                "type": "image/png",
                "size": 42,
                "origin": "upload",
                "created_at": "2026-01-01T00:00:00+00:00",
                "capabilities": {"read": True, "view": True},
            }
        ],
        "has_more": True,
        "next_cursor": "A1",
    }

    rendered = render_tool_output("list_assets", payload)

    assert "ref=A1" in rendered
    assert "origin=upload" in rendered
    assert "created_at=2026-01-01T00:00:00+00:00" in rendered
    assert '"capabilities":{"read":true,"view":true}' in rendered
    assert "cursor=A1" in rendered


def test_web_search_renders_citations_and_answer_without_dropping_extra_fields():
    payload = {
        "query": "q",
        "answer": "direct",
        "results": [
            {
                "title": "T",
                "url": "https://example.com",
                "content": "body",
                "score": 0.5,
                "citation_id": "web_1",
                "provider_extra": {"a": 1},
            }
        ],
        "success": True,
    }

    rendered = render_tool_output("web_search", payload)

    assert "Answer: direct" in rendered
    assert "1. T · web_1 · 0.5" in rendered
    assert "https://example.com" in rendered
    assert "body" in rendered
    assert '"provider_extra":{"a":1}' in rendered
    assert "success" not in rendered


def test_web_search_omits_provider_routing_and_keeps_hits_compact():
    rendered = render_tool_output(
        "web_search",
        {
            "query": "上海 天气",
            "results": [
                {
                    "title": "A",
                    "url": "https://a.test",
                    "content": "x",
                    "citation_id": "w1",
                },
                {
                    "title": "B",
                    "url": "https://b.test",
                    "content": "y",
                    "citation_id": "w2",
                },
            ],
            "success": True,
            "search_engine": "duckduckgo",
        },
    )

    assert rendered.splitlines() == [
        "Search: 上海 天气",
        "1. A · w1",
        "https://a.test",
        "x",
        "2. B · w2",
        "https://b.test",
        "y",
    ]
    assert "duckduckgo" not in rendered
    assert "title=" not in rendered


def test_rss_renders_feed_metadata_and_article_entries():
    payload = {
        "url": "https://example.com/feed",
        "feed_title": "News",
        "feed_link": "https://example.com",
        "feed_description": "desc",
        "citation_id": "web_feed",
        "total_articles": 1,
        "articles": [
            {
                "title": "Post",
                "link": "https://example.com/post",
                "citation_id": "web_post",
                "published": "2026-01-01",
                "author": "A",
                "summary": "summary",
            }
        ],
    }

    rendered = render_tool_output("rss_feed_reader", payload)

    assert "Feed: News" in rendered
    assert "desc" in rendered
    assert "url=https://example.com/feed" in rendered
    assert "citation_id=web_post" in rendered
    assert "summary" in rendered
    assert "total_articles=1" in rendered


def test_knowledge_search_renders_retrieval_identity_and_content():
    payload = {
        "contexts": [
            {
                "citation_id": "rag_1",
                "kb_id": "kb-1",
                "kb_name": "KB",
                "document_id": "doc-1",
                "document_name": "spec.md",
                "content": "evidence\n\nmore",
                "score": 0.9,
                "search_type": "hybrid",
                "context_chunks": [
                    {
                        "chunk_id": "c1",
                        "chunk_index": 0,
                        "token_count": 3,
                        "content": "evidence",
                    },
                    {
                        "chunk_id": "c2",
                        "chunk_index": 1,
                        "token_count": 2,
                        "content": "more",
                    },
                ],
                "citation_chunk_ids": ["c1", "c2"],
                "extra": "kept",
            }
        ]
    }

    rendered = render_tool_output("knowledge_search", payload)

    assert "citation_id=rag_1" in rendered
    assert "kb_id=kb-1" in rendered
    assert "document_id=doc-1" in rendered
    assert "score=0.9" in rendered
    assert "evidence" in rendered
    assert 'citation_chunk_ids=["c1","c2"]' in rendered
    assert '"chunk_id":"c1"' in rendered
    assert '"chunk_index":1' in rendered
    assert '"token_count":3' in rendered
    # Bodies are dropped only because content is their exact concatenation.
    assert '"content":"evidence"' not in rendered
    assert rendered.count("evidence") == 1
    assert '"extra":"kept"' in rendered


def test_knowledge_search_keeps_full_chunks_when_content_does_not_match():
    payload = {
        "contexts": [
            {
                "content": "different",
                "context_chunks": [
                    {
                        "chunk_id": "c1",
                        "chunk_index": 0,
                        "content": "evidence",
                        "highlight": True,
                    }
                ],
                "citation_chunk_ids": ["c1"],
            }
        ]
    }

    rendered = render_tool_output("knowledge_search", payload)

    assert 'citation_chunk_ids=["c1"]' in rendered
    assert '"content":"evidence"' in rendered
    assert '"highlight":true' in rendered


def test_memory_tools_render_actual_service_schemas():
    search = {
        "success": True,
        "count": 1,
        "message": "Found 1 relevant memories.",
        "results": [
            {
                "id": "e1",
                "name": "Alice",
                "type": "person",
                "description": "desc",
                "properties": {"team": "c"},
                "updated_at": "2026-01-01",
            }
        ],
    }
    rendered = render_tool_output("search_memory", search)
    assert "Found 1 relevant memories." in rendered
    assert "id=e1" in rendered
    assert "updated_at=2026-01-01" in rendered
    assert '"properties":{"team":"c"}' in rendered

    entity = {
        "success": True,
        "entity_id": "e2",
        "message": "created",
        "similar_entities": ["Alice"],
    }
    rendered = render_tool_output("create_memory_entity", entity)
    assert "entity_id=e2" in rendered
    assert "similar_entities=Alice" in rendered

    subgraph = {
        "success": True,
        "truncated": False,
        "entities": [
            {
                "id": "e1",
                "name": "Alice",
                "type": "person",
                "depth": 0,
                "description": "desc",
                "properties": {},
            },
            {"id": "e2", "name": "Bob", "type": "person", "depth": 1},
        ],
        "relations": [
            {
                "id": "r1",
                "source_entity_id": "e1",
                "source_name": "Alice",
                "relation_type": "knows",
                "target_entity_id": "e2",
                "target_name": "Bob",
                "description": "friends",
                "properties": {},
            }
        ],
    }
    rendered = render_tool_output("get_memory_subgraph", subgraph)
    assert "entities=2 · relations=1" in rendered
    assert "Alice -[knows]-> Bob" in rendered
    assert "source_entity_id=e1" in rendered
    assert "friends" in rendered


def test_small_tools_keep_units_values_and_time_semantics():
    assert (
        render_tool_output(
            "calculate", {"expression": "2+2", "result": 4, "success": True}
        )
        == "2+2 = 4"
    )
    assert (
        render_tool_output(
            "unit_convert",
            {
                "value": 1,
                "from_unit": "m",
                "to_unit": "cm",
                "result": 100,
                "success": True,
            },
        )
        == "1 m = 100 cm"
    )
    time_rendered = render_tool_output(
        "get_current_time",
        {
            "timezone": "UTC",
            "datetime": "2026-01-01T00:00:00+00:00",
            "date": "2026-01-01",
            "time": "00:00:00",
            "weekday": "Thursday",
            "timestamp": 1767225600,
        },
    )
    assert "2026-01-01T00:00:00+00:00" in time_rendered
    assert "Thursday" in time_rendered
    assert "timestamp=1767225600" in time_rendered
    assert (
        render_tool_output(
            "format_datetime",
            {"formatted": "2026-01-01", "timezone": "UTC", "timestamp": 1},
        )
        == "2026-01-01 · UTC · timestamp=1"
    )


def test_inspect_and_materialize_keep_capabilities_and_paths():
    inspect_payload = {
        "ref": "A1",
        "filename": "f.pdf",
        "content_type": "application/pdf",
        "size": 10,
        "source": "upload",
        "capabilities": {"read": True, "view": False},
    }
    rendered = render_tool_output("inspect_asset", inspect_payload)
    assert "ref=A1" in rendered
    assert '"capabilities":{"read":true,"view":false}' in rendered

    materialize = {
        "ref": "A1",
        "path": "/workspace/f.pdf",
        "filename": "f.pdf",
        "size": 10,
    }
    rendered = render_tool_output("materialize_asset", materialize)
    assert "path=/workspace/f.pdf" in rendered
    assert "size=10" in rendered


def test_markitdown_renders_each_bounded_file():
    payload = {
        "kind": "document.files",
        "success": True,
        "files": [
            {
                "url": "https://example.com/a.md",
                "filename": "a.md",
                "title": "A",
                "ref": "A1",
                "citation_id": "web_a",
                "segments": [_segment(1, "alpha"), _segment(2, "beta")],
                "start_line": 1,
                "total_lines": 2,
                "eof": True,
                "next_cursor": None,
            },
            {"url": "https://example.com/b.pdf", "filename": "b.pdf", "error": "bad"},
        ],
    }

    rendered = render_tool_output("markitdown", payload)

    assert "filename=a.md" in rendered
    assert "1│alpha" in rendered
    assert "2│beta" in rendered
    assert "End of results." in rendered
    assert "filename=b.pdf" in rendered
    assert "error: bad" in rendered


def test_unknown_render_preserves_escaping_and_never_truncates():
    text = "中文" * 2000 + ' "quoted" \\ slash\nnewline'
    payload = {"custom": text, "second": True}

    rendered = render_tool_output("some_custom_tool", payload)

    assert json.loads(rendered) == payload
    assert json.loads(rendered)["custom"] == text


def test_persist_envelope_only_for_explicit_non_reproducible_model_text():
    bash_display = {
        "success": True,
        "status": "completed",
        "stdout": "ok",
        "stderr": "",
        "exit_code": 0,
    }
    derived = render_tool_output("bash", bash_display)
    assert (
        persistable_model_result(
            "bash", json_output(bash_display), derived, explicit=True
        )
        is None
    )

    envelope = persistable_model_result(
        "generate_image",
        json_output({"kind": "media.image", "images": []}),
        "Generated 1 image.",
        explicit=True,
    )
    assert envelope is not None
    assert persisted_tool_output_parts(envelope) == (
        {"kind": "media.image", "images": []},
        "Generated 1 image.",
    )
    assert render_tool_output("generate_image", json.loads(envelope)) == (
        "Generated 1 image."
    )
    assert json.loads(unwrap_persisted_display(envelope)) == {
        "kind": "media.image",
        "images": [],
    }

    # Plain dict results never carry an explicit representation.
    assert (
        persistable_model_result(
            "custom_http_tool", '{"a": 1}', "different", explicit=False
        )
        is None
    )


def test_durable_replay_uses_the_explicit_model_result():
    from app.services.chat_context import summarize_tool_result_for_llm

    envelope = json.dumps(
        {
            "kind": "tool.result.persisted",
            "version": 1,
            "display": {"kind": "media.image", "images": [{"ref": "A1"}]},
            "llm_result": "Generated 1 image. Refs: A1",
        }
    )

    assert (
        summarize_tool_result_for_llm("generate_image", envelope)
        == "Generated 1 image. Refs: A1"
    )
    # Deterministic known outputs replay identically from their display payload.
    display = json.dumps({"query": "q", "results": [], "success": True})
    assert summarize_tool_result_for_llm("web_search", display) == render_tool_output(
        "web_search", json.loads(display)
    )


def test_markitdown_renders_omitted_preview_as_reading_hint():
    payload = {
        "kind": "document.files",
        "success": True,
        "files": [
            {
                "url": "https://example.com/a.pdf",
                "filename": "a.pdf",
                "ref": "A1",
                "citation_id": "web_a",
                "preview_omitted": True,
                "reading": "Use read_asset with this ref.",
            }
        ],
    }

    rendered = render_tool_output("markitdown", payload)

    assert "filename=a.pdf" in rendered
    assert "ref=A1" in rendered
    assert "Use read_asset with this ref." in rendered
    assert "preview_omitted" not in rendered
    assert "{" not in rendered


def test_unknown_flags_are_preserved_for_known_tools():
    subgraph = {
        "success": True,
        "truncated": False,
        "partial": True,
        "hops": 2,
        "entities": [],
        "relations": [],
    }
    rendered = render_tool_output("get_memory_subgraph", subgraph)
    assert "entities=0 · relations=0" in rendered
    assert '"partial":true' in rendered
    assert '"hops":2' in rendered

    knowledge = {"contexts": [], "diagnostics": [{"code": "timeout"}]}
    rendered = render_tool_output("knowledge_search", knowledge)
    assert '"diagnostics":[{"code":"timeout"}]' in rendered

    listing = {"items": [], "has_more": False, "next_cursor": None, "view": "all"}
    rendered = render_tool_output("list_assets", listing)
    assert '"view":"all"' in rendered


def test_document_keeps_unknown_continuation_flags():
    payload = {
        "ref": "A1",
        "segments": [_segment(1, "x")],
        "total_lines": 1,
        "eof": True,
        "partial": True,
    }

    rendered = render_tool_output("read_asset", payload)

    assert "End of results." in rendered
    assert '"partial":true' in rendered


def test_message_schemas_expose_display_but_leave_orm_content_alone():
    display = {"ref": "A1", "kind": "media.image", "images": []}
    envelope = json.dumps(
        {
            "kind": "tool.result.persisted",
            "version": 1,
            "display": display,
            "llm_result": "summary",
        }
    )

    message = MessageOut(
        id=uuid4(),
        conversation_id=uuid4(),
        role="tool",
        content=envelope,
        created_at=datetime.now(UTC),
    )
    step = MessageRoundStep(
        id=uuid4(),
        role="tool",
        content=envelope,
        created_at=datetime.now(UTC),
    )

    assert json.loads(message.content) == display
    assert json.loads(step.content) == display
    assert "tool.result.persisted" in envelope


def test_document_and_file_renderers_cover_empty_and_malformed_shapes():
    # _line_range empty and document_files empty-range branch.
    rendered = render_tool_output(
        "read_asset", {"segments": [], "total_lines": 0, "eof": True}
    )
    assert "<document>" in rendered and "End of results." in rendered

    # _document non-list segments -> JSON fallback.
    rendered = render_tool_output("read_asset", {"segments": "bad"})
    assert json.loads(rendered)["segments"] == "bad"

    # markitdown: non-list files, non-dict entry, no segments/reading, empty list.
    assert (
        json.loads(render_tool_output("markitdown", {"files": "bad"}))["files"] == "bad"
    )
    assert '"bad"' in render_tool_output("markitdown", {"files": ["bad"]})
    fallback = render_tool_output("markitdown", {"files": [{"filename": "x"}]})
    assert json.loads(fallback.splitlines()[-1]) == {"filename": "x"}
    empty_range = render_tool_output(
        "markitdown",
        {"files": [{"filename": "x", "segments": [], "total_lines": 0, "eof": True}]},
    )
    assert "1. filename=x" in empty_range and "<document>" in empty_range
    assert render_tool_output("markitdown", {"files": []}) == "No files."


def test_search_context_dedup_variants_and_malformed_entries():
    matches = [
        {
            "line": 10,
            "text": "hit",
            "context": [
                {"line": 1, "text": "same", "truncated": True},
                {"line": 2, "text": "same", "truncated": False},
                {"line": 3, "text": "abc", "truncated": False},
                {"line": 4, "text": "unique", "truncated": False},
                {"line": 5, "text": "abcdef", "truncated": False},
                {"line": "bad", "text": "ignored", "truncated": False},
            ],
        },
        {
            "line": 11,
            "text": "hit2",
            "context": [
                {"line": 1, "text": "same", "truncated": False},
                {"line": 2, "text": "same", "truncated": True},
                {"line": 3, "text": "abcdef", "truncated": False},
                {"line": 4, "text": "unique", "truncated": False},
                {"line": 5, "text": "abc", "truncated": False},
                {"line": 6, "text": "other", "truncated": False},
            ],
        },
    ]

    rendered = render_tool_output("search_asset", {"matches": matches, "eof": True})

    assert rendered.count("1│same") == 1
    assert rendered.count("3│abcdef") == 1
    assert rendered.count("5│abcdef") == 1
    assert "ignored" not in rendered
    assert "other" in rendered
    # Contained/same-line context is still removed; the match snippet remains.
    assert "4│unique" in rendered

    non_list = render_tool_output("search_asset", {"matches": "bad"})
    assert json.loads(non_list)["matches"] == "bad"
    malformed = render_tool_output("search_asset", {"matches": [1], "eof": True})
    assert malformed.splitlines()[1] == "1"


def test_entry_rows_cover_malformed_and_fallback_shapes():
    assert (
        json.loads(render_tool_output("web_search", {"results": "bad"}))["results"]
        == "bad"
    )
    assert render_tool_output("list_assets", {"items": [1]}) == "1"
    body_object = render_tool_output(
        "web_search",
        {"results": [{"title": "T", "content": {"parts": [1]}}], "has_more": True},
    )
    assert '"parts":[1]' in body_object
    no_body = render_tool_output(
        "web_search", {"results": [{"title": "T", "content": 0}]}
    )
    assert "1. T" in no_body


def test_knowledge_renderer_covers_malformed_and_optional_fields():
    assert (
        json.loads(render_tool_output("knowledge_search", {"contexts": "bad"}))[
            "contexts"
        ]
        == "bad"
    )
    malformed = render_tool_output(
        "knowledge_search",
        {
            "contexts": [
                1,
                {
                    "context_chunks": "bad",
                    "citation_chunk_ids": "bad",
                    "extra": True,
                },
            ],
            "diagnostics": ["x"],
        },
    )
    assert malformed.splitlines()[1] == "2."
    assert '"extra":true' in malformed
    assert '"diagnostics":["x"]' in malformed


def test_memory_renderers_cover_empty_partial_and_malformed_rows():
    assert (
        json.loads(render_tool_output("search_memory", {"results": "bad"}))["results"]
        == "bad"
    )
    rendered = render_tool_output(
        "search_memory",
        {"results": [1, {"id": "e1"}, {"id": "e2", "description": "d", "x": 1}]},
    )
    assert rendered.splitlines()[1] == "2. id=e1"
    assert "3. id=e2" in rendered and '"x":1' in rendered

    assert (
        render_tool_output(
            "create_memory_entity", {"entity_id": "e1", "similar_entities": []}
        )
        == "entity_id=e1"
    )
    assert json.loads(
        render_tool_output("update_memory_entity", {"similar_entities": []})
    ) == {"similar_entities": []}

    assert (
        json.loads(
            render_tool_output(
                "get_memory_subgraph", {"entities": "bad", "relations": []}
            )
        )["entities"]
        == "bad"
    )
    partial = render_tool_output(
        "get_memory_subgraph",
        {
            "truncated": True,
            "entities": [
                1,
                {"id": "e1"},
            ],
            "relations": [
                1,
                {"id": "r1", "source_entity_id": "e1", "target_entity_id": "e2"},
            ],
            "hops": 2,
        },
    )
    assert "Result truncated." in partial
    assert partial.splitlines()[3] == "E2. id=e1"
    assert "R2. e1 -[]-> e2" in partial
    assert '"hops":2' in partial


def test_rss_renderer_covers_empty_and_missing_metadata():
    assert (
        json.loads(render_tool_output("rss_feed_reader", {"articles": "bad"}))[
            "articles"
        ]
        == "bad"
    )
    empty = render_tool_output("rss_feed_reader", {"articles": []})
    assert "No articles." in empty
    assert "Feed:" not in empty
    assert "total_articles" not in empty


def test_renderer_error_fallback_preserves_payload():
    payload = {"error": "boom", "retryable": True}
    rendered = render_tool_output("read_asset", payload)
    assert json.loads(rendered) == payload


def test_web_search_keeps_non_dict_rows_and_alternate_result_fields():
    rendered = render_tool_output(
        "web_search",
        {
            "results": [
                "raw-row",
                {
                    "name": "Named",
                    "link": "https://named.test",
                    "summary": "s",
                    "provider": 1,
                },
                {"title": "Untitled body", "content": 0},
            ],
            "has_more": True,
        },
    )

    assert rendered.splitlines()[0] == '"raw-row"'
    assert "Named" in rendered and "https://named.test" in rendered
    assert '"provider":1' in rendered
    assert "3. Untitled body" in rendered
    assert "More results available." in rendered
