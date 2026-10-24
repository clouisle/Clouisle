# Builtin Tool Output Design Document

## Background & Goals
Implement TODO.md's complete builtin output backlog. Preserve structured UI/citation/persisted results while rendering concise model outputs. No silent loss: long document/web/log content must remain reachable. Extract genuinely shared result/rendering helpers into utils; do not force every result into TOON.

## High-Level Design
Canonical result utilities live in app/utils/tool_output.py: ToolExecutionResult with display_result and llm_result; render_tool_output(tool_name,payload) for known builtins only; get_tool_execution_payloads(result,tool_name=None) -> display JSON/string and model string. Media summary remains explicit. Unknown/custom/MCP/database/Skill payloads retain semantics and JSON unless explicitly supplied llm_result. Durable chat replay uses the same renderer and preserves original display payload. Native AssetViewResult marker protocol remains special and unmodified.

## Implementation Plan
### Stage 1: Shared result and rendering contract
- **Files modified**: utils/tool_output.py, media.py, general.py, chat_context.py, agent.py and consumers.
- **Specific logic**: one canonical result type, migrate imports without aliases; known tool renderer used identically live and replay. Keep frontend/citations structured. Preserve ask_user control objects and native view markers.
- **Validation**: live/replay equality, actual dispatcher and Workflow tool loop, unknown output preservation.

### Stage 2: Document and list renderers
- **Files modified**: shared utils, document cursor service only if measured beneficial.
- **Specific logic**: line-prefixed reads with range/ref/citation/continuation; deduplicate overlapping search context; bounded list entries and exact pagination. Internal representation ids omitted from prose, cursor remains version bound.
- **Validation**: oversized Unicode line, EOF, references and search paging; token comparison.

### Stage 3: Sandbox execution and file outputs
- **Files modified**: bash.py, sandbox_files.py, sandbox result transport and tests.
- **Specific logic**: status/stdout/stderr blocks; no empty fields; persist complete logs before any preview reduction and expose scoped ref/path for bounded continuation. Preserve hashline anchors and snapshots. Compact edit/write/artifact results, full display data retained.
- **Validation**: actual throwaway execution/transport smoke without services; long stdout/stderr tail accessible, error/timeout fidelity, artifact refs/links.

### Stage 4: Web and URL-document reading
- **Files modified**: web_search.py, builtin/file_parser.py, shared secure Asset import util, tool schemas/context filtering.
- **Specific logic**: full fetched/extracted source persisted as scoped Assets and read through existing bounded document service. No per-tool truncated document cache. Reuse SSRF checks and private storage; authorize scope before IO. Search and RSS produce compact referenced entries; short status/calculation outputs rendered minimally.
- **Validation**: mocked HTTP transport plus real storage/ORM, late-page text reachable, no redirects into private hosts, citation and scope preservation.

### Stage 5: Knowledge and memory
- **Files modified**: known-output renderer and memory service only where required.
- **Specific logic**: inspect actual schemas; preserve ids/type/update dates/relationships and raw evidence, remove only presentation redundancy. No guessing removal for configured/custom outputs.
- **Validation**: graph references, empty/error/partial states and retrieval evidence preserved.

### Stage 6: Encoding evaluation and delivery
- **Files modified**: behavioral regressions, public guides/changelog, TODO.md, implementation index.
- **Specific logic**: compare real Chinese/table/code/escaping/paging fixtures under actual tokenizer with JSON, compact JSON, TOON and text. Use standards-compliant TOON encoder for experiment, adopt only if useful; no global conversion dependency without evidence. Evaluate custom/database/MCP/Skill separately with default fidelity.
- **Validation**: full backend/frontend applicable suites, unchanged coverage gates, type/lint/i18n, live/replay smoke, no service/browser startup. Commit logical verified changes, no push.

## Testing Strategy
Consumer-visible invariants: full content recoverable, bounded outputs, correct ref/citation/cursor/hashline/task IDs, failure and partial states explicit, first execution equals restored model representation, unknown structured payloads untouched. Model choice quality unverified without live model; tokenizer measurements alone do not prove understanding.

## Risks & Mitigation
Avoid double serialization or frontends parsing prose; retain display payload. Avoid broad field dropping in custom outputs. Keep untrusted document text delimited as content, never instructions. Scope auth before persistence/network IO. Rollback code commits; additive persisted source/log Assets remain protected by existing lifecycle checks.

## Verification Evidence (final)
- Backend full suite: 9,488 passed, 4 skipped; line coverage 96.69%, branch coverage 95.06% (gates unchanged).
- Frontend: 2,924 passed; functions 95.61%, lines 97.91%; all 524 eligible sources in LCOV; TypeScript and ESLint passed (no errors).
- Sandbox smoke: real process emitted a 1,000-line stdout with its tail readable through the hashline reader; an 8 MiB overflow stopped the process and exposed an explicit partial-log reference.
- Real DOCX smoke (prior document-reading change) still applies: 204,113 characters read through 25 bounded calls with the tail reachable.
- Tokenizer benchmark: dedicated text totals 6,545/5,718 (cl100k/o200k) vs current JSON 8,385/7,548; TOON 7,324/6,451. TOON not adopted; compact JSON retained for unknown/configured payloads.
- Cursor compression measured with real entropy: read zlib 159 vs 227 tokens, search 180 vs 271; zlib chosen with bounded decompression. Pre-change cursors are rejected explicitly and must restart from a line range.
- Not verified: live-model answer quality/tool-choice behavior. Deterministic renderer/replay, citation and continuation invariants are covered; token counts do not prove comprehension.
