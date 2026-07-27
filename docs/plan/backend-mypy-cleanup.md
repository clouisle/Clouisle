# Backend Mypy Cleanup Design Document

## Background & Goals

The backend currently reports 39 mypy errors across 17 files. Most are incomplete ORM annotations or lost type narrowing at API, persistence, JSON, and helper boundaries. One error also reveals that the embed upload route fails to forward the request required by the shared upload handler.

Success criteria:

- `uv run mypy app/` reports zero errors. ✅
- Runtime behavior remains unchanged except for forwarding the missing embed upload request.
- No mypy configuration relaxation, broad suppression, or unvalidated cast is introduced.
- The existing uncommitted Retrieval Lab interactive-only cleanup remains intact.

## High-Level Design

Fix types at their source rather than at every consumer:

- Declare Tortoise-generated UUID IDs and nullable scalar fields accurately.
- Validate loose retrieval-mode values once before narrowing to the shared Literal type.
- Express optional traversal and lookup state explicitly.
- Replace heterogeneous untyped dictionaries with explicit keywords or `TypedDict` structures.
- Use narrow casts only for confirmed Tortoise `values_list(flat=True)` stub limitations.
- Carry values already narrowed by a caller into helper signatures as required arguments.

## Implementation Plan

### Stage 1: ORM and Retrieval Boundaries

- **Files modified**: knowledge-base/tool models, retrieval service, direct search and production retrieval callers.
- **Specific logic**: correct generated UUID/nullability annotations, add validated mode narrowing, exclude missing adjacent chunks, and align storage-backed download response typing.
- **Validation**: retrieval, knowledge-base, Chat, Agent, Tool, and Workflow focused tests.

### Stage 2: Chat and Administrative Typing

- **Files modified**: message branching, chat context, conversation analytics, admin agent/workflow filters.
- **Specific logic**: nullable traversal cursor, explicit compaction arguments, typed usage counters and safe token normalization, narrow flat-query result casts.
- **Validation**: branching, compaction, analytics, and filter tests.

### Stage 3: Remaining Boundaries

- **Files modified**: Runway video adapter, embed upload endpoint, tools endpoint, site-settings validation, Clouisle package services.
- **Specific logic**: pass a required start image to the helper, forward embed request context, mark raising validation helpers as non-returning, and narrow optional ORM lookup results after guards.
- **Validation**: media, embed, tools, settings, and package focused tests.

### Stage 4: Full Convergence

- **Files modified**: only additional sites exposed by a fresh full mypy run, if any.
- **Specific logic**: apply the same source-typing and boundary-narrowing principles; do not broaden scope into unrelated refactors.
- **Validation**: full mypy, Ruff, format check, pytest, and working-tree comparison.

## Validation Results

- `uv run mypy app/`: passed, zero errors across 315 source files.
- `uv run ruff check .`: passed.
- `uv run ruff format --check .`: passed for all 913 files.
- Focused regression suites: passed.
- `git diff --check`: passed.
- Full backend suite without coverage overhead: 6,358 passed, 3 skipped.
- Retrieval test doubles were aligned with the existing `KnowledgeBase.settings` contract, and direct-search mode narrowing now accepts the schema's string enum value directly.

## Testing Strategy

Happy paths:

- All retrieval modes flow from API, ORM, and workflow configuration into the shared retrieval service.
- Existing Chat, Agent, Workflow, media, tool, package, and settings behavior remains unchanged.
- Embed upload forwards authorization and audit request context.

Error paths:

- Invalid retrieval modes fail fast.
- Missing neighbors, parent IDs, teams, and knowledge bases preserve existing outcomes.
- Invalid site settings and absent Runway seed images retain existing errors.
- Missing or nullable token counters contribute zero safely.

Regression scope:

- Production multi-KB retrieval and direct knowledge-base search.
- Chat context compaction and message branching.
- Admin analytics and filter metadata.
- Tool ownership, media generation, package import/export, and embed upload.

## Risks & Mitigation

- **Runtime drift from type cleanup**: prefer annotations and explicit forwarding; verify each changed branch with existing tests.
- **ORM schema drift**: generated ID annotations describe existing columns only; do not add fields or migrations.
- **Hidden mypy errors**: rerun full mypy after each stage because error ordering can hide local diagnostics.
- **Loss of existing cleanup**: compare working-tree status before and after; never reset, restore, or stash.

## Rollback Plan

Each typing stage is localized and can be reverted independently. The Retrieval Lab cleanup is not part of this rollback boundary and must remain untouched.
