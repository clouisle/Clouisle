# Network Allowlist Switches Design Document

## Background & Goals

Provide independent switches for sandbox egress restrictions, model endpoint allowlisting, and outbound SSRF protection in the existing admin security settings. All switches default to enabled (restricted). Only an explicit boolean false disables a restriction. Missing or invalid settings must not open access.

Success: administrators can save each switch, retain configured allowlists, and immediately restore restrictions. Disabled model allowlisting accepts unlisted valid HTTP(S) endpoints. Disabled SSRF protection permits private, loopback and metadata destinations. Disabled sandbox egress restrictions permit arbitrary destinations, protocols and ports while preserving filesystem/resource isolation.

## High-Level Design

Reuse SiteSetting security keys, admin permission checks, audit logging, bulk save and existing Switch controls. Add `model_endpoint_allowlist_enabled`, `ssrf_protection_enabled`, and `sandbox_network_allowlist_enabled`, each boolean true by default and private.

Policy loaders return None only for explicitly disabled restrictions; an empty list continues to mean restricted with no exemptions/approved targets. Synchronous validators default to an empty tuple (restricted), so direct callers do not accidentally bypass protection. Model URLs remain structurally validated even when membership checking is disabled. Sandbox jobs use their existing policy snapshot; unrestricted jobs omit the network namespace/proxy bridge but retain filesystem and resource limits. Package source membership checks are skipped for unrestricted jobs.

## Implementation Plan

### Stage 1: Site settings, model endpoints and SSRF
- **Files modified**: `backend/app/models/site_setting.py`, `backend/app/api/v1/admin/endpoints/site_settings.py`, `backend/app/core/model_endpoint_policy.py`, `backend/app/core/network_security.py`, affected direct callers and backend tests.
- **Specific logic**: Register private booleans; reject non-booleans before persistence. Read current switches per policy load. Propagate disabled policy explicitly through existing HTTP/database validators and direct integrations. Preserve HTTP(S) URL and database host/port syntax validation.
- **Validation**: Exercise missing/true/false/invalid switch values, unlisted endpoints, private and metadata URLs, database targets and malformed URLs; run affected backend tests without application services.

### Stage 2: Sandbox policy and isolation
- **Files modified**: `backend/app/core/sandbox_network_policy.py`, sandbox manager/process launcher/package managers, sandbox tests.
- **Specific logic**: None denotes unrestricted egress; restricted mode remains unchanged. Skip proxy creation and network namespace/bridge for unrestricted jobs. Keep filesystem isolation, resource limits and normal package source syntax checks.
- **Validation**: Verify package sources and actual subprocess output; inspect generated restricted/unrestricted launch commands via existing isolated launcher harness. Run sandbox regression tests. Linux-only bubblewrap execution cannot be verified on macOS without an existing suitable runtime.

### Stage 3: Admin UI and localization
- **Files modified**: security API interfaces/loader, security settings page, English/Chinese translations and translation types, page tests.
- **Specific logic**: Add three labelled Switch controls, safe defaults, explicit unrestricted-access warnings and disabled allowlist editors without discarding values. Keep read-only permissions and save/load behavior.
- **Validation**: Render and interact with the component in existing frontend test harness, save and reload toggles, retain list contents and check read-only state. No browser or application service is started.

### Stage 4: Integrated verification and operator documentation
- **Files modified**: existing security operations guides and this plan/index.
- **Specific logic**: Describe defaults, scope, risk, next-job sandbox application and restoration.
- **Validation**: Run targeted backend/frontend regression suites and throwaway direct policy smoke scenarios; remove temporary scripts after verification.

## Testing Strategy

Happy paths: all switches true; explicit false independently bypasses membership checks; re-enabling restores restrictions; configured lists survive toggles. Error paths: malformed switch values rejected; missing/invalid stored values never open access; URL schemes and invalid ports rejected even when restrictions disabled. Regression: HTTP tools, workflow HTTP nodes, document fetching, database targets, model discovery/testing/runtime, sandbox package sources, launcher isolation and admin permissions.

## Risks & Mitigation

Disabling SSRF permits access to credentials/metadata and internal services; disabling sandbox egress permits direct outbound network access. UI/operator warnings make the boundary explicit. Defaults remain restricted, and only literal false opts out. Filesystem isolation and resource limits are not disabled. Sandbox changes affect new jobs, not running jobs. Rollback: enable all switches before rolling back code; existing versions ignore these keys and enforce restrictions.

## Verification Results

- Completed all four stages on branch `feat/network-allowlist-switches`.
- Backend model/SSRF/settings/HTTP/database/KB/workflow/WeChat regression selection: **590 passed**.
- Service-free sandbox policy and process-launcher selection: **50 passed, 14 deselected**. Package environment and launcher selection: **24 passed, 32 deselected**. Local proxy-server tests and background-child cases were not run, respecting the no-services constraint.
- Frontend security page/API interactions: **20 passed**. TypeScript (`tsc --noEmit --incremental false`), targeted ESLint, Ruff lint and commit-format checks passed. Backend selections total **664 passed**; the excluded proxy-server cases are not part of that count.
- In-process real FastAPI admin PUT route + SQLite smoke: absent switches remain restricted; saving false persists all switches and opens corresponding policies; malformed non-boolean input is rejected; saving true restores restrictions and retains lists. The unrestricted sandbox manager executed a finite real subprocess and returned `manager-payload-ok`.
- No browser or application service was started. Actual Linux Bubblewrap network-namespace behavior was not executed on macOS; generated restricted/unrestricted launch arguments and preserved filesystem/resource/capability limits were exercised by launcher tests. No live internal/cloud metadata endpoint was contacted.
