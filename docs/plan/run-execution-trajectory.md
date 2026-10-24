# Run Execution Trajectory Design Document

## Background & Goals
The run diagnostic currently exposes tool/retrieval spans without the model context that caused them. Replace the drawer with a directly addressable execution inspector. Success means an operator can follow actual model input, tool request/result and subsequent model output; old runs remain explicitly unrecorded.

## High-Level Design
Retain run summaries and existing tool payloads. Capture bounded, durable model-call snapshots at the AgentLoop request boundary, with call ordering and tool-call identities. Expose lightweight trajectory summaries separately from selected payload detail under the existing observability authorization boundary. The frontend uses a shared run inspector: timeline lanes, ordered trajectory, and selected-item summary/preview/raw views. Workflow entries preserve node semantics.

## Implementation Plan
### Stage 1: Runtime capture
- **Files modified**: `backend/app/services/agent_loop.py`, new `observability_trajectory.py`, `backend/app/models/observability_payload.py`, model registration, `backend/app/core/init_data.py`, and `backend/app/main.py`.
- **Specific logic**: Record actual messages/tools/model options per invocation, actual responses and call IDs, timestamps, bounded payload state. Never reconstruct historical context from current agent configuration. Reuse existing payload and retention conventions.
- **Validation**: Exercise successive model/tool rounds, failure and cancellation; ensure immutable snapshots and no credentials from transport configuration.
### Stage 2: Detail API
- **Files modified**: backend/app/services/observability_v2.py; backend/app/api/v1/admin/endpoints/observability.py; relevant schemas/tests.
- **Specific logic**: Expose ordered, correlated summaries and on-demand payloads. Preserve existing read authorization and distinguish missing, expired and truncated records. Include workflow node inputs/outputs without inventing chat roles.
- **Validation**: Authorized/unauthorized reads, selected-payload isolation, historical missing records, oversized content and retention.
### Stage 3: Execution inspector
- **Files modified**: frontend/app/(dashboard)/dashboard/observability/page.tsx; new run detail route/components; frontend/lib/api/admin/observability.ts; frontend/i18n/en/dashboard.json; frontend/i18n/zh/dashboard.json.
- **Specific logic**: Direct URL from run list, shared timeline selection and ordered list, side inspector with summary/preview/raw data, filters and responsive layout. Remove obsolete drawer-only rendering.
- **Validation**: Selection, filters, parallel calls, failure, old records, route refresh and model/tool payload rendering through isolated tests and throwaway non-service smoke scripts. Browser/services require explicit user permission.
### Stage 4: Verification and operator documentation
- **Files modified**: existing relevant guide documentation, tests and docs/IMPLEMENTATION_PLAN.md.
- **Specific logic**: Document captured content, access, size/retention limits and historical limitations. Complete acceptance checks and mark stages only when verified.
- **Validation**: Focused backend/frontend suites and actual capture-to-API smoke scenario without starting services.

## Testing Strategy
Happy paths cover ordinary answers and multiple model/tool rounds with exact input/output linkage. Error paths cover model failure, cancellation, absent payloads, payload limits, unauthorized access and stale selection requests. Regression scope includes existing observability summaries, workflow traces, tool output rendering, retention and durable agent execution.

## Risks & Mitigation
Context contains user/team data: reuse operator authorization, exclude transport secrets, document retention and bound stored content. Capture must not materially delay first token: follow existing fail-open bounded persistence patterns and measure overhead. Parallel calls must preserve IDs rather than infer causality from timestamps. Historical runs display unavailable context. Rollback removes new capture/read surfaces while preserving existing run summaries; schema additions remain backward compatible.

## Implementation Decisions
- Requests are application-normalized snapshots, not byte-exact provider requests. Full tool definitions and allowlisted inference settings are captured; configured context/output budgets are labeled separately from effective provider parameters.
- The existing global operator permission `admin:dashboard:access` protects summaries and content reads. Entry lookup is scoped by source and run. There is no automatic redaction of secrets inside user messages or tool outputs; transport credentials/configuration are excluded.
- Input and output snapshots are each capped at 256 KiB, with 100 ms best-effort persistence per write. Summary reads select lightweight columns only. Expired snapshots are deleted by bounded row-ID batches after 30 days, including snapshots whose run summary never persisted.
- Empty-stream fallback is a separate model invocation. Tool execution uses the requesting model entry as parent and preserves tool-call IDs. Provider-returned reasoning is captured; hidden reasoning is never inferred.
- The direct route is `/dashboard/observability/runs/[source]/[runId]`. Timeline bars and the ordered list share selection; overlapping calls use subtracks. Input markers denote request boundaries, not invented input durations. Workflow nodes retain their own lane and data semantics.

## Verification Evidence
- Final backend focused capture/API/agent-loop/maintenance run: **205 passed**; changed-file Ruff passed. Covers immutable requests, tool result entering subsequent model context, streaming, cancellation, authorization, run isolation, historical data, size bounds, completeness semantics and retention.
- In-process SQLite smoke exercised the actual AgentLoop through model → tool → model, then run detail and selected payload reads. Both payloads recorded; parent correlation preserved. Same-sequence capture-disabled/enabled local timing was 0.11/0.78 ms (0.67 ms delta). This is not a production or provider latency measurement. Throwaway smoke removed afterward.
- Final frontend isolated verification: **66 passed across 4 files** (list/navigation, inspector interactions, API serialization and utility behavior); TypeScript no-emit check and changed-file ESLint passed. A no-server static route-render smoke also passed and was removed afterward. Diagnostic durations retain fractional-second precision; model/workflow errors and late payload selection are regression-covered.
- No application service or browser was started. CSS layout and real-provider/deployed-PostgreSQL behavior are not visually/integration verified by these checks.
- All four implementation stages are complete. No deployment was performed; the new trajectory table is registered through the existing startup schema bootstrap. Full context appears only for newly captured runs after the updated backend/worker is deployed.
- Push-gate coverage follow-up: added 30 behavioral boundary tests for trajectory serialization/privacy, bounded writes, historical payload availability, retention batching, multimodal/tool interaction errors, steering and telemetry fail-open behavior. Full backend suite: **9546 passed, 4 skipped**; line coverage **96.68%**, branch coverage **95.10%** (both meet the 95% gate). No coverage exclusions or thresholds were changed.
