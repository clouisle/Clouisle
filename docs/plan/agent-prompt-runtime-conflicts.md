# Agent Prompt Runtime Conflict Alignment Design Document

## Background & Goals
- Manual audit found read-only memory prompts advertise writes, partial sandbox configurations advertise every sandbox tool, and generator clarification/language wording can contradict injected instructions.
- Success: tool availability and injected guidance agree; generated business prompts do not duplicate platform protocols. Preserve existing language, citation and tool authorization behavior.

## High-Level Design
- Keep the memory retrieval/temporal base instruction, append write guidance only when the same `auto_extract` gate used by chat tools permits writes.
- Describe sandbox instructions as conditional on actual supplied tools instead of promising a full toolset.
- Make generator rules distinguish internal generation constraints from emitted business content. Runtime owns language, Markdown/citations, memory tool protocol, sandbox operations and ask_user protocol; business content owns purpose, domain workflow, stable-memory subject matter and risk confirmation.

## Implementation Plan

### Stage 1: Runtime capability correctness
- **Files modified**: `backend/app/services/system_prompt.py`, `backend/tests/services/test_system_prompt_manager.py`.
- **Specific logic**: Separate memory read and write guidance; omit writes for disabled auto_extract; remove unconditional tool availability claims and fix relation parameter wording by deferring to actual schemas.
- **Validation**: Reproduce current read-only write claims and single-tool sandbox overclaim; execute final composition with disabled/read-only/writable memory, partial sandbox, chat/workflow gates.

### Stage 2: Generator separation
- **Files modified**: `backend/app/api/v1/endpoints/prompt_generator.py`, `docs/guide/api-reference/endpoints/prompts.md`.
- **Specific logic**: Emit business policies only; do not reproduce generic memory retrieval/write recipes, tool schemas, language protocols, sandbox/citation manuals. Necessary questions use injected ask_user protocol when available; efficient choice batching remains allowed. Preserve high-risk confirmation and user-expressed stable-memory requirements.
- **Validation**: Format bilingual generation requests and combine representative business instructions with runtime sections. No claims of real model generation quality without a live provider.

### Stage 3: Verification and delivery
- **Files modified**: this plan and `docs/IMPLEMENTATION_PLAN.md`.
- **Specific logic**: Record manual audit evidence, verified scope and limits.
- **Validation**: Focused generator/system-prompt/chat-tool regressions, Ruff, direct offline composition and tool exposure smoke. No service, browser or external provider calls.

## Testing Strategy
- Compare read-only prompt guidance with actual chat memory tool exposure; writable/default configs must retain writes, disabled/workflow paths must not inject memory guidance.
- Verify conditional sandbox semantics without changing actual tools.
- Existing language precedence, citation gates, Markdown and temporal behavior remain unchanged.
- Avoid wording/source-text tests; keep a behavior-focused memory permission regression and offline probes for generation instruction changes.

## Risks & Mitigation
- Existing user-saved contradictory prompts are not automatically rewritten; regenerate/review them.
- Prompt instructions are not authorization. Runtime tool schemas and permissions remain authoritative.
- Media require_confirmation is currently configuration metadata, not an independently enforced execution gate; do not claim otherwise or change it in this task.
- Rollback: revert isolated prompt changes; no migrations.

## Verification Status
- Before fix: direct composition confirmed read-only memory advertises create/update and a read-only sandbox selection claims all five tools.
- Completed: memory retrieval guidance is shared; write guidance is appended only when auto_extract permits it, otherwise an explicit read-only boundary is injected. Relation calls defer to real schemas instead of the stale source/target signature. Removed the unconditional prohibition on honestly reporting unavailable memory tools.
- Sandbox instructions now explicitly apply only to supplied tools, without claiming every sandbox tool exists. Sandbox paths and file protocols remain centrally owned by runtime.
- Generator templates no longer emit generic memory/protocol recipes, language overrides, prose-first clarification overrides or competing citation/Markdown rules. Business memory subject matter, high-risk confirmations, priorities and redundancy reduction remain.
- Manual audit also confirmed citation IDs/marker rules belong to citations.py, locale instructions are unconditional and runtime-resolved, and ask_user/memory/citation sections are chat-gated. Existing language precedence and tool execution behavior are intentionally unchanged.
- Ruff lint/format passed. Focused system-prompt, sandbox, generator, chat-tool and i18n suites: 117 passed (`--no-cov`).
- Direct offline composition smoke exercised 64 locale/mode/memory/write/question/citation combinations: injected sections had correct gates and single occurrences, memory guidance agreed with actual chat tool exposure, partial sandbox did not claim a full toolset, and business variable substitution plus bilingual generator formatting worked.
- No browser, service, external model call or database write was used. Real generated output remains probabilistic and was not evaluated; existing saved business prompts were not rewritten.
