"""Known builtin tool payload renderers.

These renderers only choose the model-facing prose for explicitly recognized
payload schemas. Unknown fields inside a known payload are emitted as compact
JSON so no business data is dropped; unknown tools never reach this module.
"""

from __future__ import annotations

from typing import Any

from app.utils.tool_output import (
    PERSISTED_RESULT_KIND,
    format_continuation,
    format_numbered_lines,
    json_output,
)


def _field(value: Any) -> str:
    """Keep metadata on one line without changing the document body."""
    return str(value).replace("\r", "\\r").replace("\n", "\\n")


_IDENTITY_KEYS = {
    "ref",
    "citation_id",
    "url",
    "title",
    "filename",
    "document_name",
    "kb_name",
    "name",
}


def _identity(payload: dict[str, Any]) -> str:
    return " · ".join(
        f"{key}={_field(payload[key])}"
        for key in (
            "ref",
            "citation_id",
            "url",
            "title",
            "filename",
            "document_name",
            "kb_name",
            "name",
        )
        if payload.get(key) is not None
    )


def _line_range(segments: list[dict[str, Any]], total: Any) -> str:
    if not segments:
        return ""
    return f"lines {segments[0]['line']}–{segments[-1]['line']}/{total if total is not None else '?'}"


def _extras(payload: dict[str, Any], known: set[str]) -> str:
    """Keep fields outside the known presentation contract, unmodified."""
    extra = {key: value for key, value in payload.items() if key not in known}
    return json_output(extra) if extra else ""


def _document(payload: dict[str, Any]) -> str:
    segments = payload.get("segments")
    if not isinstance(segments, list):
        return json_output(payload)
    header = " · ".join(
        filter(
            None,
            [
                _identity(payload),
                _line_range(segments, payload.get("total_lines")),
            ],
        )
    )
    return "\n".join(
        filter(
            None,
            [
                header,
                "<document>",
                format_numbered_lines(segments),
                "</document>",
                format_continuation(payload),
                _extras(
                    payload,
                    _IDENTITY_KEYS
                    | {
                        "segments",
                        "start_line",
                        "total_lines",
                        "next_cursor",
                        "eof",
                        "kind",
                        "success",
                        "asset_id",
                        "representation_id",
                        "content",
                    },
                ),
            ],
        )
    )


def _document_files(payload: dict[str, Any]) -> str:
    """Render the bounded multi-file preview produced by ``markitdown``."""
    files = payload.get("files")
    if not isinstance(files, list):
        return json_output(payload)
    output: list[str] = []
    for index, item in enumerate(files, 1):
        if not isinstance(item, dict):
            output.append(json_output(item))
            continue
        header = f"{index}. {_identity(item)}"
        if item.get("error") is not None:
            output.append(f"{header}\nerror: {_field(item['error'])}")
            continue
        segments = item.get("segments")
        if not isinstance(segments, list):
            # Whole-call budget exhaustion: keep the ref/citation header and the
            # reading hint instead of echoing the structured entry as JSON.
            if item.get("reading"):
                output.append(f"{header}\n{_field(item['reading'])}")
                output.append(
                    _extras(
                        item,
                        _IDENTITY_KEYS
                        | {
                            "reading",
                            "preview_omitted",
                            "success",
                            "error",
                            "segments",
                        },
                    )
                )
                continue
            output.extend([header, json_output(item)])
            continue
        range_text = _line_range(segments, item.get("total_lines"))
        if range_text:
            header += f" · {range_text}"
        output.extend(
            [
                header,
                "<document>",
                format_numbered_lines(segments),
                "</document>",
                format_continuation(item),
                _extras(
                    item,
                    _IDENTITY_KEYS
                    | {
                        "segments",
                        "start_line",
                        "total_lines",
                        "next_cursor",
                        "eof",
                        "error",
                        "kind",
                        "success",
                        "asset_id",
                        "representation_id",
                        "content",
                    },
                ),
            ]
        )
    if not files:
        output.append("No files.")
    output.append(_extras(payload, {"kind", "success", "files"}))
    return "\n".join(filter(None, output))


def _merge_context_line(
    merged: dict[int, list[dict[str, Any]]], segment: dict[str, Any]
) -> None:
    """Deduplicate overlapping context lines, preferring complete text."""
    line = segment.get("line")
    if not isinstance(line, int):
        return
    variants = merged.setdefault(line, [])
    text = segment.get("text", "")
    truncated = bool(segment.get("truncated"))
    for index, previous in enumerate(variants):
        previous_text = previous.get("text", "")
        if previous_text == text:
            if truncated and not previous.get("truncated"):
                return
            if not truncated and previous.get("truncated"):
                variants[index] = dict(segment)
            return
        if not truncated and text and previous_text in text:
            variants[index] = dict(segment)
            return
        if previous_text and not previous.get("truncated") and text in previous_text:
            return
    variants.append(dict(segment))


def _context_is_covered(segment: dict[str, Any], matches: list[dict[str, Any]]) -> bool:
    """Drop context that a match snippet on the same line already contains."""
    for match in matches:
        if match.get("line") != segment.get("line"):
            continue
        match_text = match.get("text") or ""
        text = segment.get("text") or ""
        if match_text == text:
            return True
        if not match.get("truncated") and text and text in match_text:
            return True
    return False


def _document_search(payload: dict[str, Any]) -> str:
    matches = payload.get("matches")
    if not isinstance(matches, list):
        return json_output(payload)
    output = [_identity(payload), f"Search: {_field(payload.get('query', ''))}"]
    matched: list[dict[str, Any]] = []
    context: dict[int, list[dict[str, Any]]] = {}
    for match in matches:
        if not isinstance(match, dict):
            output.append(json_output(match))
            continue
        matched.append(match)
        output.append(
            " ".join(
                filter(
                    None,
                    [
                        f"Match line {match.get('line')}",
                        f"columns {match.get('match_start', 0)}–{match.get('match_end', 0)}",
                        "(snippet clipped; read this line)"
                        if match.get("truncated")
                        else "",
                    ],
                )
            )
        )
        # Every hit keeps its own snippet, including multiple hits on one line.
        output.append(format_numbered_lines([match]))
        for segment in match.get("context") or []:
            if isinstance(segment, dict):
                _merge_context_line(context, segment)
    context_segments = [
        variant
        for line in sorted(context)
        for variant in context[line]
        if not _context_is_covered(variant, matched)
    ]
    if context_segments:
        output.extend(
            [
                "<search context>",
                format_numbered_lines(context_segments),
                "</search context>",
            ]
        )
    output.append(format_continuation(payload))
    output.append(
        _extras(
            payload,
            _IDENTITY_KEYS
            | {
                "matches",
                "query",
                "total_lines",
                "next_cursor",
                "eof",
                "kind",
                "success",
                "asset_id",
                "representation_id",
            },
        )
    )
    return "\n".join(filter(None, output))


def _rows(
    rows: Any,
    *,
    identity_fields: tuple[str, ...],
    body_fields: tuple[str, ...] = (),
    suppressed: tuple[str, ...] = (),
) -> list[str]:
    output: list[str] = []
    if not isinstance(rows, list):
        return output
    known = {*identity_fields, *body_fields, *suppressed}
    for index, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            output.append(json_output(row))
            continue
        identity = " · ".join(
            f"{field}={_field(row[field])}"
            for field in identity_fields
            if row.get(field) is not None
        )
        body = ""
        for field in body_fields:
            value = row.get(field)
            if value:
                body = value if isinstance(value, str) else json_output(value)
                break
        entry = f"{index}. {identity}" if identity else f"{index}."
        if body:
            entry += f"\n{body}"
        output.append(entry)
        extra = {key: value for key, value in row.items() if key not in known}
        if extra:
            output.append(json_output(extra))
    return output


def _entries(
    payload: dict[str, Any],
    key: str,
    *,
    identity_fields: tuple[str, ...],
    body_fields: tuple[str, ...] = (),
    suppressed: tuple[str, ...] = (),
) -> str:
    rows = payload.get(key)
    if not isinstance(rows, list):
        return json_output(payload)
    output = [_identity(payload)]
    if payload.get("answer"):
        output.append(f"Answer: {payload['answer']}")
    if payload.get("message"):
        output.append(str(payload["message"]))
    output.extend(
        _rows(
            rows,
            identity_fields=identity_fields,
            body_fields=body_fields,
            suppressed=suppressed,
        )
    )
    if not rows:
        output.append("No results.")
    output.append(format_continuation(payload))
    output.append(
        _extras(
            payload,
            _IDENTITY_KEYS
            | {
                key,
                "answer",
                "message",
                "query",
                "success",
                "kind",
                "has_more",
                "next_cursor",
                "eof",
            },
        )
    )
    return "\n".join(filter(None, output))


def _knowledge_search(payload: dict[str, Any]) -> str:
    contexts = payload.get("contexts")
    if not isinstance(contexts, list):
        return json_output(payload)
    output: list[str] = []
    if payload.get("query"):
        output.append(f"Query: {_field(payload['query'])}")
    identity_fields = (
        "citation_id",
        "kb_name",
        "kb_id",
        "document_name",
        "document_id",
        "score",
        "search_type",
    )
    known = {*identity_fields, "content", "context_chunks", "citation_chunk_ids"}
    for index, context in enumerate(contexts, 1):
        if not isinstance(context, dict):
            output.append(json_output(context))
            continue
        identity = " · ".join(
            f"{field}={_field(context[field])}"
            for field in identity_fields
            if context.get(field) is not None
        )
        output.append(f"{index}. {identity}" if identity else f"{index}.")
        content = context.get("content")
        if content:
            output.append(str(content))
        citation_ids = context.get("citation_chunk_ids")
        if isinstance(citation_ids, list):
            output.append(f"citation_chunk_ids={json_output(citation_ids)}")
        chunks = context.get("context_chunks")
        if isinstance(chunks, list):
            chunk_contents = [
                chunk.get("content") for chunk in chunks if isinstance(chunk, dict)
            ]
            joined = "\n\n".join(
                part for part in chunk_contents if isinstance(part, str)
            )
            content_matches = (
                isinstance(content, str)
                and len(chunk_contents) == len(chunks)
                and all(isinstance(part, str) for part in chunk_contents)
                and joined == content
            )
            # Drop chunk bodies only when the concatenation proves they are
            # already present as ``content``; all identifiers/metadata stay.
            metadata = (
                [
                    {key: value for key, value in chunk.items() if key != "content"}
                    for chunk in chunks
                ]
                if content_matches
                else chunks
            )
            output.append(f"context_chunks={json_output(metadata)}")
        extra = {key: value for key, value in context.items() if key not in known}
        if extra:
            output.append(json_output(extra))
    if not contexts:
        output.append("No results.")
    output.append(_extras(payload, {"contexts", "query", "success", "kind"}))
    return "\n".join(filter(None, output))


def _memory_search(payload: dict[str, Any]) -> str:
    results = payload.get("results")
    if not isinstance(results, list):
        return json_output(payload)
    output: list[str] = []
    if payload.get("message"):
        output.append(str(payload["message"]))
    if payload.get("count") is not None:
        output.append(f"count={payload['count']}")
    identity_fields = ("id", "name", "type", "updated_at")
    for index, result in enumerate(results, 1):
        if not isinstance(result, dict):
            output.append(json_output(result))
            continue
        identity = " · ".join(
            f"{field}={_field(result[field])}"
            for field in identity_fields
            if result.get(field) is not None
        )
        output.append(f"{index}. {identity}" if identity else f"{index}.")
        if result.get("description"):
            output.append(str(result["description"]))
        extra = {
            key: value
            for key, value in result.items()
            if key not in {*identity_fields, "description"}
        }
        if extra:
            output.append(json_output(extra))
    output.append(_extras(payload, {"results", "message", "count", "success", "kind"}))
    return "\n".join(filter(None, output))


def _memory_mutation(payload: dict[str, Any]) -> str:
    output: list[str] = []
    if payload.get("message"):
        output.append(str(payload["message"]))
    for field in ("entity_id", "relation_id"):
        if payload.get(field) is not None:
            output.append(f"{field}={_field(payload[field])}")
    similar = payload.get("similar_entities")
    if isinstance(similar, list) and similar:
        output.append("similar_entities=" + ", ".join(_field(item) for item in similar))
    output.append(
        _extras(
            payload,
            {
                "message",
                "entity_id",
                "relation_id",
                "similar_entities",
                "success",
                "kind",
            },
        )
    )
    rendered = "\n".join(filter(None, output))
    return rendered if rendered else json_output(payload)


def _memory_subgraph(payload: dict[str, Any]) -> str:
    entities = payload.get("entities")
    relations = payload.get("relations")
    if not isinstance(entities, list) or not isinstance(relations, list):
        return json_output(payload)
    output = [f"entities={len(entities)} · relations={len(relations)}"]
    if payload.get("truncated"):
        output.append("Result truncated.")
    for index, entity in enumerate(entities, 1):
        if not isinstance(entity, dict):
            output.append(json_output(entity))
            continue
        identity = " · ".join(
            f"{field}={_field(entity[field])}"
            for field in ("id", "name", "type", "depth")
            if entity.get(field) is not None
        )
        output.append(f"E{index}. {identity}")
        if entity.get("description"):
            output.append(str(entity["description"]))
        extra = {
            key: value
            for key, value in entity.items()
            if key not in {"id", "name", "type", "depth", "description"}
        }
        if extra:
            output.append(json_output(extra))
    for index, relation in enumerate(relations, 1):
        if not isinstance(relation, dict):
            output.append(json_output(relation))
            continue
        source = relation.get("source_name") or relation.get("source_entity_id")
        target = relation.get("target_name") or relation.get("target_entity_id")
        identity = " · ".join(
            f"{field}={_field(relation[field])}"
            for field in ("id", "source_entity_id", "target_entity_id")
            if relation.get(field) is not None
        )
        output.append(
            f"R{index}. {_field(source)} -[{_field(relation.get('relation_type', ''))}]-> {_field(target)}"
            + (f" · {identity}" if identity else "")
        )
        if relation.get("description"):
            output.append(str(relation["description"]))
        extra = {
            key: value
            for key, value in relation.items()
            if key
            not in {
                "id",
                "source_entity_id",
                "target_entity_id",
                "source_name",
                "target_name",
                "relation_type",
                "description",
            }
        }
        if extra:
            output.append(json_output(extra))
    output.append(
        _extras(payload, {"entities", "relations", "truncated", "success", "kind"})
    )
    return "\n".join(filter(None, output))


def _asset_metadata(payload: dict[str, Any]) -> str:
    output = [
        " · ".join(
            f"{field}={_field(payload[field])}"
            for field in (
                "ref",
                "filename",
                "content_type",
                "size",
                "source",
                "path",
                "url",
            )
            if payload.get(field) is not None
        )
    ]
    known = {
        "ref",
        "filename",
        "content_type",
        "size",
        "source",
        "path",
        "url",
        "asset_id",
        "checksum",
        "representation_id",
    }
    extra = {key: value for key, value in payload.items() if key not in known}
    if extra:
        output.append(json_output(extra))
    return "\n".join(filter(None, output))


def _rss(payload: dict[str, Any]) -> str:
    articles = payload.get("articles")
    if not isinstance(articles, list):
        return json_output(payload)
    output: list[str] = []
    if payload.get("feed_title"):
        output.append(f"Feed: {_field(payload['feed_title'])}")
    if payload.get("feed_description"):
        output.append(_field(payload["feed_description"]))
    output.append(_identity(payload))
    output.extend(
        _rows(
            articles,
            identity_fields=("title", "link", "citation_id", "published", "author"),
            body_fields=("summary",),
        )
    )
    if not articles:
        output.append("No articles.")
    if payload.get("total_articles") is not None:
        output.append(f"total_articles={payload['total_articles']}")
    output.append(
        _extras(
            payload,
            _IDENTITY_KEYS
            | {
                "feed_title",
                "feed_description",
                "feed_link",
                "articles",
                "total_articles",
                "success",
                "kind",
            },
        )
    )
    return "\n".join(filter(None, output))


def _sandbox_output(tool_name: str, payload: dict[str, Any]) -> str | None:
    try:
        from app.utils.sandbox_output import (
            SANDBOX_OUTPUT_TOOLS,
            render_sandbox_output,
        )
    except ImportError:  # pragma: no cover - module ships with the tools
        return None
    if tool_name not in SANDBOX_OUTPUT_TOOLS:
        return None
    return render_sandbox_output(tool_name, payload)


def render_tool_output(tool_name: str | None, payload: Any) -> str:
    """Render a known payload without changing its stored/display representation."""
    if not isinstance(payload, dict):
        return json_output(payload)
    if payload.get("kind") == PERSISTED_RESULT_KIND:
        llm_result = payload.get("llm_result")
        return llm_result if isinstance(llm_result, str) else json_output(payload)

    # Sandbox failures/executions are formatted as text, so they precede the
    # generic error fallback.
    sandbox = _sandbox_output(tool_name or "", payload)
    if sandbox is not None:
        return sandbox

    if payload.get("error") is not None:
        return json_output(payload)
    if tool_name == "markitdown" or payload.get("kind") == "document.files":
        return _document_files(payload)
    if (
        tool_name in {"read_asset", "view_asset", "fetch_webpage"}
        and "segments" in payload
    ):
        return _document(payload)
    if tool_name == "search_asset":
        return _document_search(payload)
    if tool_name == "list_assets":
        key = "assets" if "assets" in payload else "items"
        return _entries(
            payload,
            key,
            identity_fields=(
                "ref",
                "name",
                "type",
                "size",
                "origin",
                "created_at",
            ),
        )
    if tool_name == "web_search":
        return _entries(
            payload,
            "results",
            identity_fields=("citation_id", "title", "url", "score"),
            body_fields=("content",),
        )
    if tool_name in {"knowledge_search", "search_knowledge_base"}:
        return _knowledge_search(payload)
    if tool_name == "rss_feed_reader":
        return _rss(payload)
    if tool_name == "search_memory":
        return _memory_search(payload)
    if tool_name in {
        "create_memory_entity",
        "create_memory_relation",
        "update_memory_entity",
    }:
        return _memory_mutation(payload)
    if tool_name == "get_memory_subgraph":
        return _memory_subgraph(payload)
    if tool_name == "calculate" and "result" in payload:
        expression = payload.get("expression")
        line = (
            f"{expression} = {payload['result']}"
            if expression
            else f"Result: {payload['result']}"
        )
        return "\n".join(
            filter(
                None,
                [line, _extras(payload, {"expression", "result", "success"})],
            )
        )
    if tool_name == "unit_convert" and "result" in payload:
        line = f"{payload.get('value')} {payload.get('from_unit')} = {payload['result']} {payload.get('to_unit')}"
        return "\n".join(
            filter(
                None,
                [
                    line,
                    _extras(
                        payload,
                        {"value", "from_unit", "to_unit", "result", "success"},
                    ),
                ],
            )
        )
    if tool_name == "get_current_time" and "datetime" in payload:
        line = (
            f"{payload['datetime']} · {payload.get('weekday')} · "
            f"{payload.get('timezone')} · timestamp={payload.get('timestamp')}"
        )
        return "\n".join(
            filter(
                None,
                [
                    line,
                    _extras(
                        payload,
                        {
                            "datetime",
                            "date",
                            "time",
                            "weekday",
                            "timezone",
                            "timestamp",
                            "success",
                        },
                    ),
                ],
            )
        )
    if tool_name == "format_datetime" and "formatted" in payload:
        line = f"{payload['formatted']} · {payload.get('timezone')} · timestamp={payload.get('timestamp')}"
        return "\n".join(
            filter(
                None,
                [
                    line,
                    _extras(
                        payload,
                        {"formatted", "timezone", "timestamp", "success"},
                    ),
                ],
            )
        )
    if tool_name in {"inspect_asset", "materialize_asset"}:
        return _asset_metadata(payload)
    return json_output(payload)
