# PR 124 Security Review Fixes Design Document

## Background & Goals

- PR #124 has CodeQL and Gemini review comments for path traversal, SSRF, ReDoS, XXE, sensitive logging, and elapsed-time measurement.
- Goal: address all review findings with localized defensive changes and keep existing behavior where safe.

Success criteria:
- Untrusted package paths cannot escape their intended roots.
- HTTP fetch helpers reject private/internal/localhost targets unless the call is a known internal relative upload URL.
- Data URL parsing avoids regex backtracking on uncontrolled input.
- XML-like user input parsing avoids XML parsers on LLM-controlled text.
- Missing translation logging does not emit potentially sensitive keys.
- Duration measurement uses a monotonic clock.

## High-Level Design

- Keep fixes local to the reviewed files.
- Add root-bound path resolution helpers for skill import/package handling.
- Add external HTTP URL validation in shared HTTP tool execution and reject external upload URLs in builtin file parsing.
- Replace broad regex/XML parsing with bounded string parsing.

## Implementation Plan

### Stage 1: Path traversal hardening
- **Files modified**: `backend/app/services/skill_package.py`, `backend/app/services/skill_import.py`
- **Specific logic**: Resolve package paths through root-bound helpers before reads, manifest hashing, extraction, install, copy, and private spec building.
- **Validation**: Run backend lint/type checks where possible and targeted syntax checks.

### Stage 2: SSRF and ReDoS hardening
- **Files modified**: `backend/app/llm/tools/executors.py`, `backend/app/api/v1/endpoints/chat_tools.py`
- **Specific logic**: Validate outbound HTTP URLs against local/private/reserved hosts and avoid regex parsing for data URLs. Only allow uploaded-file parsing for relative application URLs.
- **Validation**: Run static grep for reviewed vulnerable patterns and backend checks.

### Stage 3: XXE, logging, and timing fixes
- **Files modified**: `backend/app/api/v1/endpoints/chat_helpers/general.py`, `backend/app/core/i18n.py`, `backend/app/api/v1/admin/endpoints/models.py`
- **Specific logic**: Replace XML parser usage with limited tag extraction, avoid logging translation keys, and use `time.monotonic()` for latency.
- **Validation**: Run static grep and relevant backend checks.

## Testing Strategy

- `python3 -m compileall backend/app/services/skill_package.py backend/app/services/skill_import.py backend/app/llm/tools/executors.py backend/app/api/v1/endpoints/chat_tools.py backend/app/api/v1/endpoints/chat_helpers/general.py backend/app/core/i18n.py backend/app/api/v1/admin/endpoints/models.py`
- `uv run ruff check backend/app/services/skill_package.py backend/app/services/skill_import.py backend/app/llm/tools/executors.py backend/app/api/v1/endpoints/chat_tools.py backend/app/api/v1/endpoints/chat_helpers/general.py backend/app/core/i18n.py backend/app/api/v1/admin/endpoints/models.py`
- `uv run mypy app/` if backend environment is available.
- Re-check PR comments after pushing.

## Risks & Mitigation

- Blocking internal HTTP URLs can affect custom tools that intentionally call internal services.
  - **Mitigation**: Treat this as the safer default for LLM/user-influenced tools; internal upload parsing still supports relative app URLs.
- Manual XML tag parsing is narrower than full XML.
  - **Mitigation**: The feature only needs `question` and `option` text extraction from a constrained block.
