# Builtin Tool Output Encoding Evaluation

Status: measured experiment, 2026-10-24. This evaluation changed no production
code. The renderer under test is an uncommitted worktree implementation, not
released code. TOON is **not** adopted as a dependency. Results reflect
`backend/app/utils/tool_output.py` at mtime 2026-10-24 17:44; re-run the
benchmark after the renderer freezes or changes.

## Scope

Evaluate the model-facing representation of builtin and configured tool results
for the TODO item "优化内置工具模型侧 output". The full display payload
(`display_result`, frontend/citations/Assets) is unchanged in every variant; only
the string sent to the model is measured.

Questions answered:

1. Does TOON beat current JSON for the actual payload shapes returned by Memory,
   database, MCP, Skill, Asset read/search/list, and RSS-style results?
2. How much do compact JSON and dedicated text save under the runtime tokenizer?
3. How much of the Asset read/search payload is the continuation cursor, and can
   a compact cursor encoding remove most of it?
4. Which fields must be preserved for Memory and configured database/MCP/Skill
   outputs? (See [Preserve-field inventory](#preserve-field-inventory).)

Not measured: model comprehension / answer quality. That requires a live model
and is explicitly out of scope of this token-only benchmark. Do not treat token
counts as proof that a rendering is understood equally well.

## Method

- Fixtures: `backend/scripts/benchmark_tool_output_tokens.py`.
- Tokenizer: the repository's own `app.llm.token_counter.count_tokens`, mapped
  through `MODEL_ENCODING_MAP` (`backend/app/llm/token_counter.py`), measured
  with `tiktoken 0.14.0`:
  `gpt-4` → `cl100k_base` (also the provider default for Anthropic/DeepSeek/Qwen/
  TypeSafe in this repo) and `gpt-4o` → `o200k_base`.
- Encodings compared:
  - **current JSON**: `json.dumps(payload, ensure_ascii=False)`. This is what a
    raw tool returns and what `get_tool_execution_payloads` still sends verbatim
    for tools outside `KNOWN_OUTPUT_TOOLS` (database, MCP, Skill, custom).
  - **compact JSON**: same, `separators=(",", ":")`.
  - **TOON**: official `toon-format==1.2.0` Python package, default options,
    installed only in a throwaway environment.
  - **dedicated text**: the current (uncommitted) repository renderer
    (`app/utils/tool_output.py::render_tool_output`) for every tool in
    `KNOWN_OUTPUT_TOOLS` (Asset read/search/list, web/knowledge search, RSS,
    Memory, small built-ins, sandbox). Database, Skill, and MCP renderings are
    candidate functions in the benchmark only; those tools are not in
    `KNOWN_OUTPUT_TOOLS` and production keeps their original JSON.
- Fixtures are modeled on the actual return values (field names and nesting) of:
  `MemoryService.handle_search_memory`, `handle_get_memory_subgraph`,
  `app/llm/tools/builtin/{postgresql,mysql_db,db_executor}.py`,
  `app/api/v1/endpoints/chat_tools.py` MCP branch,
  `app/services/skill_executor.py::to_llm_payload`, and
  `app/services/asset_{document,access}.py`.
- No network, service, or model calls. The only network access was installing the
  throwaway `tiktoken`/`toon-format` benchmark environment outside the repository.

Reproduce:

```bash
uv venv /tmp/toolout_bench_venv --python 3.13
uv pip install --python /tmp/toolout_bench_venv/bin/python \
    "tiktoken>=0.12.0" "toon-format==1.2.0"
cd backend
PYTHONPATH=. /tmp/toolout_bench_venv/bin/python \
    scripts/benchmark_tool_output_tokens.py
```

Add `--json` to emit the case totals, per-encoding token counts, RSS layout,
and cursor measurements as one machine-readable document (useful for refreshing
the snapshot after the renderer freezes).

The script falls back to loading `app/llm/token_counter.py` by path when the full
`app.llm` package (provider SDKs) is unavailable; the encoding map and counting
logic are still the repository's.

## Results

Percentages are relative to current JSON for the same case. For known tools,
current JSON is the raw tool payload before rendering; how much of it production
still sends depends on `KNOWN_OUTPUT_TOOLS`. Exact round-trip means decoding the
encoded string reproduces the payload exactly; dedicated text is intentionally
lossy (display data is still stored separately) and its preservation checks
assert that every listed id/date/value literal survives.

| Case | Encoding | gpt-4 (cl100k_base) | gpt-4o (o200k_base) | Exact round-trip |
|---|---|---|---|---|
| memory_search_zh | current JSON | 631 (100%) | 570 (100%) | yes |
| memory_search_zh | compact JSON | 550 (87%) | 493 (86%) | yes |
| memory_search_zh | TOON | 608 (96%) | 545 (96%) | yes |
| memory_search_zh | dedicated text | 538 (85%) | 479 (84%) | lossy |
| memory_subgraph_zh | current JSON | 894 (100%) | 858 (100%) | yes |
| memory_subgraph_zh | compact JSON | 781 (87%) | 750 (87%) | yes |
| memory_subgraph_zh | TOON | 861 (96%) | 824 (96%) | yes |
| memory_subgraph_zh | dedicated text | 750 (84%) | 720 (84%) | lossy |
| memory_search_empty | current JSON | 45 (100%) | 38 (100%) | yes |
| memory_search_empty | compact JSON | 40 (89%) | 33 (87%) | yes |
| memory_search_empty | TOON | 40 (89%) | 32 (84%) | yes |
| memory_search_empty | dedicated text | 28 (62%) | 21 (55%) | lossy |
| memory_error | current JSON | 16 (100%) | 15 (100%) | yes |
| memory_error | compact JSON | 14 (88%) | 13 (87%) | yes |
| memory_error | TOON | 12 (75%) | 11 (73%) | yes |
| memory_error | dedicated text | 14 (88%) | 13 (87%) | lossy |
| db_rows_paged (30 rows × 9 cols) | current JSON | 1945 (100%) | 1687 (100%) | yes |
| db_rows_paged | compact JSON | 1691 (87%) | 1434 (85%) | yes |
| db_rows_paged | TOON | 1845 (95%) | 1567 (93%) | yes |
| db_rows_paged | dedicated text | 1696 (87%) | 1439 (85%) | lossy |
| db_rows_empty | current JSON | 26 (100%) | 26 (100%) | yes |
| db_rows_empty | compact JSON | 21 (81%) | 21 (81%) | yes |
| db_rows_empty | TOON | 20 (77%) | 20 (77%) | yes |
| db_rows_empty | dedicated text | 13 (50%) | 13 (50%) | lossy |
| db_error | current JSON | 13 (100%) | 13 (100%) | yes |
| db_error | compact JSON | 11 (85%) | 11 (85%) | yes |
| db_error | TOON | 9 (69%) | 9 (69%) | yes |
| db_error | dedicated text | 11 (85%) | 11 (85%) | lossy |
| skill_result (2 artifacts) | current JSON | 224 (100%) | 215 (100%) | yes |
| skill_result | compact JSON | 185 (83%) | 178 (83%) | yes |
| skill_result | TOON | 180 (80%) | 175 (81%) | yes |
| skill_result | dedicated text | 157 (70%) | 150 (70%) | lossy |
| mcp_json_text_result | current JSON | 81 (100%) | 76 (100%) | yes |
| mcp_json_text_result | compact JSON | 80 (99%) | 75 (99%) | yes |
| mcp_json_text_result | TOON | 77 (95%) | 72 (95%) | yes |
| mcp_json_text_result | dedicated text | 74 (91%) | 69 (91%) | lossy |
| mcp_structured_result | current JSON | 57 (100%) | 57 (100%) | yes |
| mcp_structured_result | compact JSON | 44 (77%) | 45 (79%) | yes |
| mcp_structured_result | TOON | 37 (65%) | 37 (65%) | yes |
| mcp_structured_result | dedicated text | 44 (77%) | 45 (79%) | lossy |
| read_asset_code (47 lines) | current JSON | 1165 (100%) | 1157 (100%) | yes |
| read_asset_code | compact JSON | 929 (80%) | 925 (80%) | yes |
| read_asset_code | TOON | 699 (60%) | 691 (60%) | yes |
| read_asset_code | dedicated text | 460 (39%) | 452 (39%) | lossy |
| read_asset_long_escaped_line | current JSON | 968 (100%) | 716 (100%) | yes |
| read_asset_long_escaped_line | compact JSON | 940 (97%) | 689 (96%) | yes |
| read_asset_long_escaped_line | TOON | 935 (97%) | 683 (95%) | yes |
| read_asset_long_escaped_line | dedicated text | 897 (93%) | 643 (90%) | lossy |
| search_asset_zh (2 matches) | current JSON | 324 (100%) | 288 (100%) | yes |
| search_asset_zh | compact JSON | 270 (83%) | 237 (82%) | yes |
| search_asset_zh | TOON | 284 (88%) | 247 (86%) | yes |
| search_asset_zh | dedicated text | 205 (63%) | 168 (58%) | lossy |
| list_assets_paged (10 items) | current JSON | 760 (100%) | 755 (100%) | yes |
| list_assets_paged | compact JSON | 610 (80%) | 607 (80%) | yes |
| list_assets_paged | TOON | 724 (95%) | 711 (94%) | yes |
| list_assets_paged | dedicated text | 608 (80%) | 604 (80%) | lossy |
| list_assets_empty | current JSON | 16 (100%) | 16 (100%) | yes |
| list_assets_empty | compact JSON | 14 (88%) | 14 (88%) | yes |
| list_assets_empty | TOON | 12 (75%) | 12 (75%) | yes |
| list_assets_empty | dedicated text | 7 (44%) | 7 (44%) | lossy |
| rss_feed_zh (10 articles) | current JSON | 1220 (100%) | 1061 (100%) | yes |
| rss_feed_zh | compact JSON | 1087 (89%) | 929 (88%) | yes |
| rss_feed_zh | TOON | 981 (80%) | 815 (77%) | yes |
| rss_feed_zh | dedicated text | 1043 (85%) | 884 (83%) | lossy |

Totals (sum of the fixtures above):

| Encoding | gpt-4 (cl100k_base) | gpt-4o (o200k_base) |
|---|---:|---:|
| current JSON | 8385 (100%) | 7548 (100%) |
| compact JSON | 7267 (87%) | 6454 (86%) |
| TOON | 7324 (87%) | 6451 (85%) |
| dedicated text | 6545 (78%) | 5718 (76%) |

## Findings and measured decisions

### 1. Dedicated text is the only consistently strong win

For tools with a current worktree or candidate renderer, text is 15–61% smaller
than current JSON:

- `read_asset` code: 39% of current (61% saved).
- `search_asset`: 63% / 58% (cl100k / o200k).
- `list_assets`: 80% / 80% (20% saved). The current layout retains
  `origin`/`created_at` and the `capabilities` array; a leaner layout would save
  more but risks dropping fields the model uses to choose a tool.
- Memory search/subgraph: 85% / 84% (15–16% saved).
- Skill result (candidate): 70%.
- RSS articles: 85% / 83% with the current layout. A tighter
  one-line-per-article layout measured 958 / 790 (79% / 74%), which also beats
  TOON; RSS is the one case where the current generic `_entries` layout leaves
  measurable savings on the table.
- Empty/list states: 44–62% for empty JSON payloads, though absolute counts are
  tiny.

This supports using text only for explicitly known tools. Unknown payloads must
not be rewritten.

### 2. Compact JSON is a free baseline for anything that stays JSON

Dropping separator whitespace alone saves 11–15% on the large fixtures
(`db_rows_paged` 1945 → 1691; `read_asset_code` 1165 → 929; `list_assets` 760 →
610). For payloads that are definitely JSON (SQL tools, Skill), compacting at
the producer or safely re-serializing after `json.loads` requires no schema
knowledge. Do not parse arbitrary MCP text just to compact it; the 1% gain on an
embedded JSON string is not worth changing the contract, and non-JSON text would
be corrupted.

### 3. TOON does not help the actual Memory/DB/Asset shapes

TOON round-trips exactly, but measured results contradict the usual tabular
assumption because the real payloads are not flat object arrays:

- Memory results/entities contain nested `properties`; TOON is 96% of current
  JSON, **worse than compact JSON (87%)**.
- `list_assets` items contain a nested `capabilities` array; TOON is 95% vs
  compact 80%.
- The SQL tools return `columns` + `rows` (arrays of arrays). TOON adds per-row
  `[N]:` markers: 1845 vs compact 1691 (95% vs 87%). A dedicated `|`-table
  renderer is only 1696 — statistically tied with compact JSON, so it does not
  justify a renderer.
- Diagnostic on the same 30 rows converted to flat same-key objects: TOON 1722
  vs compact 2245 vs row-array compact 1691. TOON wins only for the flat-object
  shape (23% below compact), but that shape is **larger than the current row
  array** (1722 > 1691), so converting rows to objects to enable TOON would be
  counterproductive.
- RSS is the one shape where TOON helps: homogeneous article objects without
  nested arrays give 981 vs compact 1087 (80% / 89%). Even there, an optimized
  text layout can beat it (958 / 790); the current shared layout is 1043 / 884,
  so a few percent are available without adding a TOON dependency.

Decision: do not add `toon-format` or any global TOON conversion. Keep JSON
(compact) for arbitrary/configured outputs. If a future tool emits a genuinely
flat, homogeneous array, TOON can be reconsidered with a model-quality test, not
on token counts alone; a tailored text line format can match or beat it without
a new dependency.

### 4. MCP / custom outputs: preserve semantics, do not parse

MCP and custom tool names are dynamic, and their `result` is arbitrary text,
JSON text, or a list of content strings. Measured:

- Embedded JSON text: current 81 → compact 80 (99%) → TOON 77 (95%) → unwrap
  labeled text 74 (91%).
- Structured result list: compact 44; TOON 37; no text renderer (same as JSON).

The only safe gain is unwrapping a single string `result` into a labeled block
(`success · result_chars=N` + raw text). That removes one JSON string escaping
layer but makes the boundary delimiter-dependent; it must not parse or reformat
the content. Recommend compact JSON as the default for MCP/custom outputs, and
only unwrap when `result` is a single `str` and the wrapper is explicitly
declared. Never move MCP tools into the known-tool renderer.

### 5. Skill: text is worthwhile

Skill results are produced by this repository and have a stable shape
(`SkillExecutionResult.to_llm_payload`). Text at 70% preserves success, result,
error, artifact fields, duration, status, and the already-truncated stdout/stderr
summaries. Recommended as a known renderer, but still keep `display_result`
complete.

### 6. Errors and empty states

- Errors: keep compact JSON (`{"error": "...", "success": false}`). TOON saves a
  few tokens but reduces clarity of the failure contract; not worth it.
- Empty known tools: emit an explicit short line (`No results.` / `No rows.`)
  rather than a JSON envelope. This is a large relative win on tiny payloads and
  keeps the empty state explicit.

## Continuation cursor evaluation

Originally, `app/services/asset_document.py` encoded cursors as sorted-key JSON
→ urlsafe base64 without padding. A read cursor embeds the 36-char parent UUID,
the 64-hex representation checksum, and the 64-hex representation version. A
search cursor additionally embeds a 16-hex query hash, `context_lines`, and
`limit`. The parent-owned implementation has since adopted zlib wrapping (same
fields, default zlib level, bounded decompress); the **current JSON** row below
is the pre-change baseline used to measure the saving, and the **zlib** row
matches the shipped encode shape.

Measured with deterministic high-entropy identities (`uuid5` parent + SHA-256
checksum/version/query hashes), not repeated placeholder hex. Entropy matters:
patterned `a/b` placeholders make zlib look far better than real cursors. Offsets
are 1,234,567 / line 50,000 for read; 2,345,678 / line 60,000 / context 2 /
limit 20 for search:

| Cursor | chars | cl100k | o200k |
|---|---:|---:|---:|
| read current JSON | 302 | 227 | 199 |
| read zlib(JSON) | 220 | 159 | 147 |
| read JSON array + 16-byte binding (hex) | 72 | 54 | 50 |
| read binary tuple + binding | 40 | 25 | 25 |
| search current JSON | 352 | 271 | 230 |
| search zlib(JSON) | 250 | 180 | 171 |
| search JSON array + 16-byte binding (hex) | 104 | 79 | 67 |
| search binary tuple + binding | 55 | 37 | 35 |

The search rows retain the query hash, context lines, and limit; dropping the
query hash would break the existing stale-query check and is not an option.
With real entropy, zlib removes only 30–34% of cursor tokens (227→159,
271→180), not the ~50% suggested by low-entropy placeholders. The JSON array
removes key names but keeps hex expansion; the binary tuple is strongest and
needs explicit bounds/version validation on decode.

Full result payload, using the current read/search text renderer:

| Result payload | cl100k | o200k |
|---|---:|---:|
| read_asset current cursor | 683 | 647 |
| read_asset zlib cursor | 614 | 594 |
| read_asset JSON-array cursor | 509 | 497 |
| read_asset packed cursor | 480 | 472 |
| search_asset current cursor | 474 | 396 |
| search_asset zlib cursor | 382 | 336 |
| search_asset JSON-array cursor | 281 | 232 |
| search_asset packed cursor | 240 | 201 |

A compact binary encoding removes 85–89% of the cursor itself and 30–49% of the
whole result page; zlib removes 10–20% of the page. Proposed binary layout
(stdlib `struct`, urlsafe base64):

- 1 byte version, 1 byte kind (`read` / `search`), 8-byte offset, 4-byte line.
- search only: 1-byte context, 2-byte limit, 8-byte query hash.
- 16-byte `sha256(parent_id + representation_id + representation_version +
  query_hash)[:16]` binding.

The binding replaces the embedded UUID/checksums while preserving the existing
staleness contract; decode recomputes it from the current parent/representation
and rejects a mismatch. The current cursor is unsigned, so an unkeyed truncated
hash does not weaken an existing security boundary (scope authorization happens
before cursor use; offsets only address the already-authorized document). If
tamper evidence is wanted, use an HMAC with the application secret instead of a
plain hash at the same size. A server-side opaque ID is smaller still but adds
state, which the current stateless design avoids.

Every cursor token is paid twice in a tool loop (once in the tool result, once
when the model passes it back), so these savings roughly double in practice.

Chosen implementation (parent-owned, not part of this evaluation): zlib-wrap the
existing sorted JSON before base64, keep the same payload validation, and bound
decompression (for example 2048 bytes) so a crafted cursor cannot expand
unboundedly. This is the smallest change and preserves the exact current fields
and stale-check semantics. Tradeoff: with high-entropy hashes it saves only
30–34% of cursor tokens (10–20% of a page), far less than the binary layout, but
it does not require a new decoder schema.

Because the chosen decoder has no raw-v1 fallback, cursors issued before deploy
become unreadable. `asset_document` must map that to an explicit invalid/expired
cursor error telling the caller to reread from the start line; it must not
silently resume at an empty or partial offset. In-flight continuations across a
rolling deploy therefore need one fresh bounded read. The JSON-array and binary
variants remain future options if the larger savings justify their complexity;
all variants must retain the search query hash and the
parent/representation/version binding. This evaluation changed no production
code.

## Preserve-field inventory

These are the exact model-visible fields observed in the current handlers. The
display payload always keeps everything; the list below is the minimum a known
renderer may not drop.

### Memory (`backend/app/services/memory.py`)

- `search_memory`: `success`, `count`, `message`; each result:
  `id`, `name`, `type`, `description`, `properties` (arbitrary object),
  `updated_at`. Empty result still has `results: []`, `count: 0`, `message`.
- `get_memory_subgraph`: `success`, `truncated`; each entity: `id`, `name`,
  `type`, `description`, `properties`, `depth`; each relation: `id`,
  `source_entity_id`, `source_name`, `relation_type`, `target_entity_id`,
  `target_name`, `description`, `properties`.
- `create_memory_entity`: `success`, `entity_id`, `message`,
  `similar_entities` (names or `null`).
- `create_memory_relation`: `success`, `relation_id`, `message`.
- `update_memory_entity`: `success`, `entity_id`, `message`.
- All failures: `success: false`, `error`. The graph result may be
  `truncated: true`; node/relation limits are 30/100 and input entity ids are
  capped at 5 before querying.

Notes: ids are UUID strings and must survive verbatim; `updated_at` is a
`YYYY-MM-DD` string; `properties` is business data and must not be flattened
away. The current `_memory_search` renderer keeps `message` and `count=`;
they are presentation/duplication and could be dropped only if the empty/result
count stays explicit. Keep them in `display_result` regardless.

### Database tools (`builtin/{postgresql,mysql_db,db_executor}.py`)

- SQL query: `success`, `error`; `columns` (list of names), `rows` (list of
  positional arrays), `total_rows`, `truncated`. Empty: `columns: []`,
  `rows: []`, `total_rows: 0`, `truncated: false`.
- SQL schema: `success`, `database`, `tables`, `selected_schemas`
  (`table -> {columns: [{name, type, nullable, primary_key, default, comment}],
  samples: [{column: value}] | null}`).
- Connection test: `success`, `message`, `ping`; failure: `success`, `error`.
- Redis: `success`, `error`; scan `{pattern, total_found, keys: [{key, type,
  ttl_seconds}]}`; get `{key, exists, type, ttl_seconds, value}`; command
  `{command, key, result}`.
- MongoDB: `success`, `error`; schema `{database, collections | collection,
  fields_schema, samples}`; find/aggregate `{collection, count, results}`;
  count `{collection, count}`.

Notes: `rows` is deliberately positional; do not convert it to objects to enable
TOON (measured larger). Preserve `truncated`/`total_rows`/`total_found` and
`NULL` versus empty string distinctions. Any renderer must be dialect-agnostic
or restricted to the query shape; schema/connection/Redis/Mongo shapes should
stay compact JSON.

### MCP (`backend/app/llm/tools/mcp_client.py`, `chat_tools.py`)

- Wrapper produced by `execute_tool_call`: `success`, `result`, `error`.
- `result` is a single text string when the server returned one content item, a
  list of strings for multiple items, or `null` for none. `error` is the
  resolved user-visible error when `isError` is set.
- Preserve the exact `result` payload; never parse/reformat/truncate it. MCP tool
  names are dynamic (`mcp_<server>_<tool>`) and must not be routed through a
  builtin renderer.

### Skill (`backend/app/services/skill_executor.py::to_llm_payload`)

`success`, `result`, `error`, `artifact_count`, `duration_ms`, `status`,
`artifacts` (only when non-empty; each: `path`, `url`, `filename`, `size`,
`content_type`), `stdout_summary` (last 2000 chars, only when present),
`stderr_summary` (same). The full stdout/stderr remain in `display_result` via
`to_dict`. `status` is the sandbox status value or `null`.

## Unknowns / follow-ups

- **Model comprehension is unmeasured.** The evaluation only proves token cost.
  Any TOON or text adoption should be justified by task accuracy on a real model,
  especially for escaped/long lines and heterogeneous memory graphs.
- **Tokenizer proxy.** Non-OpenAI providers are mapped to `cl100k_base` in this
  repo, so cl100k is the representative column for Anthropic/DeepSeek/Qwen here;
  it is not the vendors' actual tokenizer.
- **Cursor security choice.** Packed binding as measured uses an unkeyed hash,
  matching the current unsigned cursor. If cursors are meant to be
  tamper-evident, an HMAC variant is required; that is a product decision, not a
  token decision.
- **MCP text boundary.** The 9% unwrap gain depends on a delimiter convention for
  arbitrary text. It is not worth adding unless a concrete MCP payload is shown
  to benefit after escaping.
- **Long escaped lines** only save 7–10% under text because the payload is
  dominated by escaped content. Text still wins, but the gain is not the 60%
  seen on structured reads.

## Related

- Design: `docs/plan/builtin-tool-output.md`
- Renderer: `backend/app/utils/tool_output.py`
- Benchmark: `backend/scripts/benchmark_tool_output_tokens.py`
