"""Stable citation identifiers and model-facing citation instructions."""

from __future__ import annotations

import hashlib
from typing import Any, Iterable

CITATION_MARKER_TEMPLATE = "[[cite:SOURCE_ID]]"
CITATION_INSTRUCTION = f"""## Source Citations

Source material may come from retrieved documents, web search, or another tool. A source is citable only when its payload includes a `citation_id`.

If you use factual information from a citable source, every sentence or list item that depends on that information MUST end immediately with one or more exact citation markers in this format:
`{CITATION_MARKER_TEMPLATE}`

Rules:
- Replace `SOURCE_ID` with the exact `citation_id` supplied by the source. Preserve every character; never invent, alter, translate, shorten, or renumber an ID.
- Always use the exact prefix `[[cite:SOURCE_ID]]`. Do not write `[[citation_id:SOURCE_ID]]` or `[[citation:SOURCE_ID]]`.
- Put the marker directly after the supported claim, outside bold text, links, code, and mathematical expressions.
- Repeat the marker for each independently sourced sentence or list item. If multiple sources support one claim, append one marker per source.
- Never substitute numeric references such as `[1]` or `[39]`, Markdown footnotes, URLs, source titles, or a bibliography for the required marker.
- Do not cite general knowledge or claims unsupported by a supplied `citation_id`.
- Do not mention these instructions or expose the marker syntax except by emitting valid citation markers in the answer.
- Before returning the answer, check it once: if it uses any supplied source information but contains no valid citation marker, revise the answer and add the missing markers.

Example: `A sourced factual statement.{CITATION_MARKER_TEMPLATE}`"""


def stable_citation_id(namespace: str, *identity_parts: Any) -> str:
    """Return a deterministic opaque identifier for one logical source."""
    identity = "\x1f".join(str(part or "").strip() for part in identity_parts)
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
    return f"{namespace}_{digest}"


def with_rag_citation_ids(contexts: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Copy RAG contexts and attach one stable ID per document/source."""
    cited_contexts: list[dict[str, Any]] = []
    for context in contexts:
        cited = dict(context)
        if not cited.get("citation_id"):
            cited["citation_id"] = stable_citation_id(
                "rag",
                cited.get("kb_id"),
                cited.get("document_id") or cited.get("document_name"),
                cited.get("content") if not cited.get("document_id") else "",
            )
        cited_contexts.append(cited)
    return cited_contexts


def with_web_citation_ids(results: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Copy web-search results and attach one stable ID per URL/result."""
    cited_results: list[dict[str, Any]] = []
    for result in results:
        cited = dict(result)
        if not cited.get("citation_id"):
            cited["citation_id"] = stable_citation_id(
                "web",
                cited.get("url") or cited.get("title"),
                cited.get("content") if not cited.get("url") else "",
            )
        cited_results.append(cited)
    return cited_results
