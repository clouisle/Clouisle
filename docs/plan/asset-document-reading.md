# Asset Document Reading Design Document

## Background & Goals
Persist complete extracted document text as an Asset-derived representation. Models must reach the last character through bounded reads and search, without automatic document-text injection or silent truncation. Preserve native media and original-Asset authorization.

## High-Level Design
Reuse Asset.parent and existing upload storage. A versioned text representation and sparse line index support range reads. Authorize original scope/ref and active conversation branch before every operation. First use extracts complete text; subsequent operations reuse persisted representation. Read/search outputs are bounded and carry version-bound continuation positions, including offsets inside oversized lines. No vectors, OCR service, cross-document search, or new application services.

## Implementation Plan
### Stage 1: Complete extraction and persistence
- **Files modified**: services/file_parser.py, services/upload_storage.py, new services/asset_document.py; model/bootstrap only if durable uniqueness requires it.
- **Specific logic**: untruncated extraction separate from legacy truncating parse; persist derived UTF-8 text and sparse line offsets; immutable checksum/version identity; atomic publication and cross-process serialization; range reads for local/object storage. Explicit unsupported, empty extraction, resource limit and failed extraction errors.
- **Validation**: real long text and document fixture extraction; repeated/concurrent reads reuse complete output; local and object range behavior.

### Stage 2: Bounded reader and search
- **Files modified**: new document service, focused tests.
- **Specific logic**: one-based lines, deterministic UTF-8 budget, oversized-line continuation, literal search with bounded snippets and continuation; reject invalid/stale cursor and invalid parameters. No partial-success truncation.
- **Validation**: reconstruct full normalized text including last character; Unicode/long lines/empty lines; late search and search paging.

### Stage 3: Tools and context cutover
- **Files modified**: chat_tools.py, tool registration/dispatch/prompt definitions, chat_context.py, asset_view.py, relevant schemas/i18n/UI configuration only where affected.
- **Specific logic**: read_asset/search_asset use shared service, retire parse_asset everywhere; document attachments yield references not full text; preserve native image/audio/video and explicit PDF viewing; active-branch and scope authorization on every read/search. Migrate obsolete truncation settings only where no consumers remain.
- **Validation**: tool invocation through real dispatcher; revoked/hidden scope fails; first model context excludes document text; all common Agent/Workflow channel paths retain tool availability.

### Stage 4: Verification and delivery
- **Files modified**: behavioral regression tests, existing public Asset/tool documentation and implementation index.
- **Specific logic**: exercise file-to-tool-to-EOF and search-to-read with throwaway smoke; update obsolete contract tests, preserve global coverage gates. Commit verified logical changes without pushing unless requested.
- **Validation**: targeted and full applicable suites, formatter/lint/type checks. No service/browser startup. Actual model behavior requires credentials and explicit runtime permission; report that limit.

## Testing Strategy
Happy path: complete extraction, persistent cache reuse, range continuation, literal search and native media. Negative paths: permissions, hidden branches, deleted/expired parent, malformed/version-mismatched cursor, invalid ranges, conversion and storage failures. Regression: existing parser consumers and shared Agent/Workflow tool dispatch.

## Risks & Mitigation
Parser completeness is not OCR/layout fidelity: report empty/failed extraction, retain native originals. Atomic metadata publication must not expose unfinished text; stale workers must not replace newer versions. Avoid loading full stored text per read or search; sparse offsets plus range reads. Roll back via reverting code commits; derived content remains non-authoritative and inaccessible without parent authorization.

## Implemented Contract
- `Asset.representation_key` provides durable unique publication identity. Pending claims become available only after complete immutable storage writes; failed or stale claims can be reclaimed by a later request.
- Derived text uses `AssetSource.DERIVED_TEXT`, inherits parent ownership/expiry, has no scope refs, and cannot be independently attached or downloaded through public upload routes.
- `read_asset(ref, start_line=1, line_count=100, cursor=None)` returns line-numbered `segments`, `total_lines`, `representation_id`, `next_cursor`, `eof`. A segment's `continuation` indicates that its line continues. Repeated segments with the same line number concatenate without an inserted newline.
- `search_asset(ref, query, context_lines=2, limit=20, cursor=None)` is case-sensitive, single-line literal search. Match snippets/context may be explicitly marked truncated; read the indicated line to expand. Search cursors bind query, context size, result limit, parent, and representation version.
- Both response bodies are bounded to 32 KiB serialized UTF-8, with 4 KiB reserved for metadata. Read supports 1–500 requested lines, search 1–50 matches and 0–10 context lines; output budgets may return fewer.
- Complete extraction rejects undecodable/empty text and explicitly fails above 5,000,000 extracted characters; no truncated representation is published. This is an extraction resource ceiling, not a promise to process arbitrarily large input.
- A concurrent cold publication waits up to 30 seconds; `asset_document_in_progress` asks the caller to try a later call. Claims older than 300 seconds can be reclaimed by a later request. No background retry service is added.
- Local and object storage implement native range reads. Deployments must make the configured upload storage available to the executing process; this change does not add a new distributed local-file transport.

## Verification Evidence
- Real DOCX smoke: 204,113 extracted characters, 2,401 lines, 25 bounded reads, largest response 14,104 bytes; searched the last-line sentinel and read it back. One persisted representation reused.
- Final frozen backend suite: 9,373 passed, 4 skipped; line coverage 96.72%, branch coverage 95.04% (unchanged 95% gates). Ruff checks passed.
- Frontend: 2,921 passed, function coverage 95.61%, line coverage 97.91%; all 524 eligible source files represented. TypeScript and ESLint checks passed after narrowing document citation payloads.
- No application service, browser, or live model session started. Model tool-choice behavior itself is not exercised by the deterministic tool smoke.
