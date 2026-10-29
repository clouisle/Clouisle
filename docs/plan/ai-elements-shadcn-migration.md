# AI Elements shadcn/ui Migration Design Document

## Background & Goals

AI SDK Elements is moving to shadcn/ui. Existing copied components remain functional, but this project will adopt the shadcn Base UI patterns and remove the old CLI dependency. Preserve the existing chat interactions and local customizations, including streaming, citations, attachments, accessibility and pending questions.

## High-Level Design

Use shadcn/ui Base UI primitives and patterns from the official migration guidance. Rebuild local components in place where the upstream migration retains their public contracts; the application-specific prompt generation dialog is not an upstream element. Do not change backend or durable run semantics.

## Implementation Plan

### Stage 1: Trace patterns
- **Files modified**: `frontend/components/ui/trace.tsx`, `frontend/components/ai-elements/chain-of-thought.tsx`, `tool.tsx`, `reasoning.tsx`, `task.tsx` and associated tests.
- **Specific logic**: Adopt the Base UI trace primitives and preserve controlled/uncontrolled open state, streaming, status, localization and scrolling.
- **Validation**: Exercise waiting, running, error, completion, keyboard toggling and streaming transitions.

### Stage 2: Message and supporting patterns
- **Files modified**: `frontend/components/ai-elements/message.tsx`, `inline-citation.tsx`, `conversation.tsx`, `code-block.tsx`, `shimmer.tsx`, related UI primitives, consumers and tests.
- **Specific logic**: Follow corresponding shadcn migration guidance while preserving actual product behavior and accessible interactions.
- **Validation**: Exercise message rendering, attachment previews, citation interaction, code rendering, copy and scrolling.

### Stage 3: Dependency cutover
- **Files modified**: `frontend/package.json`, `frontend/bun.lock` and affected consumers.
- **Specific logic**: Remove the obsolete `ai-elements` package after migrating its usages. Keep dependencies still needed by application components.
- **Validation**: Type check, lint and run affected component and chat tests without application servers or browsers.

### Stage 4: Documentation and regression
- **Files modified**: `docs/guide/CHANGELOG.md`, `docs/guide/CHANGELOG_zh-CN.md`, this plan and `docs/IMPLEMENTATION_PLAN.md`.
- **Specific logic**: Document the migration and record results.
- **Validation**: Run targeted regressions and real component rendering smoke checks; report that browser visual validation requires explicit permission.

Verification: 140 targeted component and chat tests passed, TypeScript and ESLint passed, and a server-side render smoke check confirmed an open Trace disclosure displays its result. No browser or application server was started; visual validation remains unverified. Conversation uses Message Scroller's API rather than unsupported legacy spring configuration. The shared Collapsible primitive remains Radix-based, so Trace adapts the shadcn pattern to the project's existing primitive.

## Testing Strategy

- Happy path: chat messages, thought steps, tool calls, questions, citations, code and attachments.
- Error path: failed tool calls, malformed/empty output, missing citation links and unavailable clipboard.
- Regression: streaming and reconnect, controlled collapse, keyboard controls and chat rendering across Agent surfaces.

## Risks & Mitigation

- Upstream primitives may alter layout or accessibility: preserve local contracts and cover interaction semantics; browser validation is not authorized in this session.
- Replacing copied files can discard product fixes: apply surgical changes and retain existing behavior.
- Rollback by reverting the migration commits together, including dependency and lockfile changes.
