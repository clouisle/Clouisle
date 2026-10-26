# Agent Prompt Generation Alignment Design Document

## Background & Goals
- The orchestration editor already supplies tools, knowledge bases, variables, RAG and media/memory/attachment settings, but omits the user-question capability. The generic generator template does not explain current runtime boundaries and prefers display labels over callable names.
- Success: generation uses the current editor settings, distinguishes disabled capabilities and RAG modes, preserves callable names and supported variable placeholders, and does not promise unavailable tools or duplicate runtime-managed instructions.
- Existing saved prompts, model selection, SSE transport and Agent execution remain unchanged.

## High-Level Design
- Extend the existing frontend capability context with user-question and citation flags; reuse the existing memoized orchestration context and generator request.
- Update the existing bilingual backend meta-prompts and context renderer. Business behavior belongs in the generated prompt; tool schemas, platform-managed rules and runtime availability remain authoritative.

## Implementation Plan

### Stage 1: Align context and generation instructions
- **Files modified**: `frontend/lib/api/prompts.ts`, `frontend/app/(platform)/app/apps/[id]/_components/agent-orchestration-form.tsx`, `backend/app/api/v1/endpoints/prompt_generator.py`.
- **Specific logic**: Forward current user-question/citation flags; render explicit capability availability and only enabled capability configs; retain callable names alongside display labels; explain RAG modes, configured-only variable placeholders, skills, attachment evidence and runtime-managed behavior in both languages.
- **Validation**: Exercise context rendering with enabled/disabled capabilities and different tool labels; reproduce missing `ask_user` context before the fix.

### Stage 2: Verify and document the contract
- **Files modified**: `backend/tests/api/test_prompt_generator.py`, `docs/guide/api-reference/endpoints/prompts.md`, `docs/IMPLEMENTATION_PLAN.md`, this plan.
- **Specific logic**: Remove incidental exact-wording assertions where affected; retain behavior coverage for capability availability. Document context semantics and non-retroactive generation.
- **Validation**: Run focused backend and frontend tests, static checks and a throwaway direct execution of the context-to-generation/SSE path without starting services or a browser. Real model quality and visual verification require an explicitly permitted live environment.

## Testing Strategy
- Happy paths: bilingual metadata, callable/display names, enabled user questions and citations, populated current editor context.
- Negative paths: disabled capabilities with stale config must not be advertised as enabled; absent context must retain its existing fallback; existing missing-model/provider-error paths must remain intact.
- Regression scope: prompt generator SSE tests, prompt API tests and orchestration component tests. No new source-text or mock-forwarding permanent tests.

## Risks & Mitigation
- A language model may still ignore instructions. Check the actual assembled request, but do not claim live generation quality without exercising a real model.
- Supplied context is a generation hint, not authorization or proof of runtime tool availability. Runtime schemas remain authoritative.
- Rollback: revert this isolated adaptation; no database migration or saved-prompt rewrite is involved.

## Verification Status
- Completed: editor capability context, bilingual runtime-aware templates, callable/display-name preservation, disabled-capability config filtering and API documentation.
- Before the fix, a direct context-rendering probe omitted enabled `ask_user` and included disabled memory configuration. Both behaviors are corrected.
- Backend generator regression suite: 10 passed (`--no-cov`; existing coverage artifacts untouched). Frontend orchestration, prompt API and dialog suites: 22 passed.
- Ruff lint/format checks and ESLint for modified code passed.
- Direct execution smoke: 12 language/RAG/capability combinations verified context availability, stale-config filtering, template brace formatting, runtime variable resolution and conditional user-question instructions.
- In-process ASGI smoke: HTTP 422 for missing required input; bilingual POST generation emitted ordered start/content/complete SSE events with matching lengths; absent default model emitted an error without completion. An explicit offline adapter replaced the provider for this probe; no real model output quality was evaluated.
- No application service or browser was started. Visual behavior and live model generation quality were not verified. Existing saved prompts remain unchanged.

### Memory semantics follow-up
- Scope: refine only the existing bilingual generator templates and API documentation; no memory runtime changes.
- Confirmed `get_agent_tools` keeps `search_memory`/`get_memory_subgraph` with `auto_extract=false`, while filtering all memory writes. The earlier generic capability sentence did not explain that boundary.
- Generate task-specific retrieval/storage conditions, distinguish history/KB/user memory, and avoid fabricated relationships, sensitive/transient writes or automatic-persistence promises. Do not duplicate runtime schemas or turn memory configuration keys into invented tool arguments.
- Validation completed: generator and chat-tool suites passed (47 tests, `--no-cov`); Ruff lint and format checks passed. Direct execution of actual `get_agent_tools` confirmed no memory tools when disabled, two read tools with `auto_extract=false`, and all five tools with `true` or the omitted default. Both language templates formatted successfully for every case. No database writes, real provider calls, browser sessions or services were used; live generated-output quality remains unverified.
