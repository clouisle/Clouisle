# Agent UI Automation Guide

Use this guide to design browser journeys for issue #255. It is deliberately evidence-based: routes, source-visible text, and existing unit/API tests were inspected. It does **not** prescribe CSS/XPath selectors.

## Validation status and operating rules

- **Browser-environment validation is unavailable.** No browser was run. The repository has no Playwright/Cypress configuration, E2E test directory, browser auth-state fixture, or `test:e2e` script.
- The landmarks below are source-visible UI text. Confirm their rendered role, accessible name, locale, responsive visibility, focus behavior, and timing in the target browser before relying on them.
- Prefer visible headings, labels associated with inputs, placeholders, and named buttons. Do not use undocumented DOM structure, generated classes, or icon-only controls without first inspecting the rendered accessibility tree.
- Use a unique, traceable test-data prefix such as `e2e-<run-id>-`. Record every created ID/name and clean up only those records.
- Test least privilege separately from successful administration. Permission guards can hide an action rather than display a denial.

## Test data baseline

Prepare authorized, disposable accounts and data:

- unauthenticated browser state;
- standard user; user with TOTP and a non-secret test backup code; forced-password-change and unverified-email accounts when supported by the environment;
- team owner, admin, member, viewer, and a user outside the team;
- an administrator with access to the requested dashboard route;
- a disposable agent, workflow, knowledge base, uploadable non-sensitive document, and notification payload;
- an embedding model for knowledge-base creation and any model authorization required by the test environment;
- API key/webhook test configuration only when explicitly approved. Never place real secrets in prompts, screenshots, logs, or reports.

## Journey matrix

### 1. Authentication and access

- **Purpose:** establish session, redirect, verification, recovery, MFA, and permission-boundary behavior.
- **Routes:** `/login`, `/register`, `/verify`, `/forgot-password`, `/reset-password`, `/change-password`, `/totp-setup`, `/sso-callback`; protected platform routes under `/app/**`; dashboard routes such as `/dashboard`.
- **Landmarks:** `Welcome back`; `Username or email`; `Password`; `Login`; `Forgot password?`; `Human verification`; `Verify your email`; `Verification Code`; `Reset Password`; `Current Password`; `New Password`; `Confirm Password`; `Two-Factor Authentication Required`; `6-digit code`; `Use backup code instead`; `Scan QR Code`; QR image accessible name `TOTP QR Code`; `Or enter this code manually`; `Copy Code`; `Code copied!`; `Save Backup Codes`; password-warning text `Your password will expire in {days} days`; `Change Password Now`.
- **Happy scenarios:** log in with a valid authorized account; verify that a protected-route request returns to the intended route after login; complete email verification or submit a token-based password reset with disposable data, verify the token and new password are sent, then use the visible login action; change a disposable account password and confirm the requested `redirect` destination; during TOTP setup, verify the QR image, reveal the read-only manual secret, and copy it only to an approved ephemeral clipboard; for a non-exempt account expiring within seven days, verify the warning links to `/profile` and can be dismissed.
- **Error/access scenarios:** submit blank/invalid credentials; submit mismatched new/confirmation passwords in both change-password and token-reset flows and confirm no request is sent; submit an invalid or expired reset token and verify the failure state; submit an invalid TOTP or backup code; confirm the password warning stays hidden for exempt users and status-request failures; open a protected route without a token; use a user lacking the mapped route permission; provide an unsafe SSO redirect value and confirm the application does not navigate off-site. The backend test suite covers unsafe redirect rejection and normalizes registration locale values.
- **Side effects/cleanup:** login writes local session state; verification/reset requests send email; changing a password invalidates the old credential; TOTP setup generates recovery material and copying writes the secret to the system clipboard; dismissing the expiration warning changes only component state. Clear browser storage/session and clipboard, restore or invalidate only test credentials, and do not print or retain TOTP secrets or recovery codes.

### 2. Chat

- **Purpose:** exercise agent chat, conversation lifecycle, attachments, runtime variables, and generated-link confirmation.
- **Routes:** `/chat/[id]`; `/chat/[id]?conversation=[conversationId]`; `/run/[id]?type=agent`; `/run/[id]?type=workflow`; `/run/[id]?type=workflow&debug=true`; `/embed/agent/[id]`.
- **Landmarks:** `Login Required`; `Agent not found`; `New Chat`; `No conversations`; `Rename Conversation`; `Delete Conversation`; `Conversation Title`; `How can I help you today?`; `Type a message...`; `Type your message...`; `Send`; `Stop`; `Attach file`; `Fill in Variables`; `Start Chat`; `Open link?`; `This link was generated in the chat. Please confirm before opening it.` Image-preview controls are semantic only after browser inspection: zoom percentage, prompt toggle, `zoomOut`, `zoomIn`, `rotate`, `download`, and `close`.
- **Happy scenarios:** open a known agent; start a new chat; send a harmless prompt; complete required variables; rename a test conversation; verify the route includes its conversation ID; render a message with an available source and verify its source-content landmark; test the confirmation path before opening a generated link. For a disposable image/video preview, open and close the lightbox, verify Escape and backdrop behavior, change zoom/rotation, and verify scrolling is restored after close.
- **Error/access scenarios:** open a chat logged out; use an unknown agent/resource ID; send with required variables omitted; attach an unsupported or intentionally invalid test file only if upload validation is available in the environment. Do not claim a download succeeds unless the browser confirms its filename, download handling, and cleanup; intentionally failed image retrieval must leave the preview usable.
- **Side effects/cleanup:** creates messages and conversations; may upload files, download media, and open external links. Delete only created conversations and uploaded test artifacts; remove downloaded test media. Do not treat streaming timing, attachment rendering, image/video controls, or browser scroll restoration as verified until run in a browser.

### 3. Workflow

- **Purpose:** validate workflow creation/editing, draft versus published execution, publication validation, and operational views.
- **Routes:** `/app/apps`; `/app/apps/workflow/[id]`; `/app/apps/workflow/[id]/monitor`; `/app/apps/workflow/[id]/logs`; `/app/apps/workflow/[id]/api`; `/run/[id]?type=workflow`; `/run/[id]?type=workflow&debug=true`; `/embed/workflow/[id]`.
- **Landmarks:** `Workflow Editor`; `Nodes`; `Start`; `End`; `Run`; `Publish`; `Published`; `Unpublished`; `Checklist`; `Resolve all issues before publishing`; `All checks passed`; `Test Run`; `Start Run`; `Cancel Run`; `Please publish workflow first`; `Debug (use draft)`; `API Documentation`; `Webhook URL`; `API Key Required`; `Workflow Monitor`; `No workflow runs yet`.
- **Happy scenarios:** create a named workflow for a selected test team; add/configure a minimal valid graph; run the draft in debug mode; publish after checks pass; run the published workflow; inspect monitor/log/API views.
- **Error/access scenarios:** attempt to publish an incomplete graph; attempt a non-debug published run before publishing; visit with a user without app access; use an invalid workflow ID.
- **Side effects/cleanup:** creates app/workflow versions and execution records; API/webhook tests can expose credentials or invoke external systems. Do not call a real webhook or use a production API key. Delete the test workflow if permitted; workflow runtime data also has server-side retention cleanup.

### 4. Knowledge bases

- **Purpose:** validate team-scoped knowledge-base management, document processing, search, and destructive-data safeguards.
- **Routes:** `/app/kb`; `/app/kb/[id]`; `/app/kb/[id]/search`; `/app/kb/[id]/documents/[docId]`; `/knowledge-bases`; `/knowledge-bases/[id]`; `/knowledge-bases/[id]/search`.
- **Landmarks:** `Knowledge Bases`; `Create Knowledge Base`; `Enter knowledge base name`; `Select a team`; `Embedding Model`; `No embedding models available`; `Documents`; `Upload Document`; `Import URL`; `Drag and drop files here, or click to select`; `Reprocess`; `Edit Chunks`; `Apply Re-chunking`; `Search Test`; `Enter your search query...`; `Hybrid`; `Vector`; `Fulltext`; `No results found`.
- **Happy scenarios:** create a KB for a test team with an available embedding model; upload a harmless test document; wait for processing only when the environment exposes its result; run a search using each available search mode; inspect a document/chunk view.
- **Error/access scenarios:** create with missing name/team/model; test search with no matching text; access a team KB as an outsider; access admin KB routes with only low-level `kb:read` permission. Existing backend tests distinguish team-scoped access from admin knowledge-base permissions.
- **Side effects/cleanup:** uploading creates documents/chunks/embeddings. Rechunking deletes and regenerates chunks/embeddings and discards manual chunk edits; deleting a KB deletes its documents/chunks. Do not rechunk or delete shared data. Delete only the test KB and its test document.

### 5. Team permissions

- **Purpose:** verify membership role boundaries, ownership transfer, model authorization, and quota administration.
- **Route:** `/teams`.
- **Landmarks:** `Team Management`; `Create Team`; `Team Name`; `Members`; `Add Member`; `Role`; `Change Role`; `Remove Member`; `Transfer Ownership`; `Leave Team`; `Model Authorization`; `Authorize Model`; `Quota Settings`; `Revoke Authorization`.
- **Happy scenarios:** create a disposable team; add a test member; assign each supported role (`owner`, `admin`, `member`, `viewer`) in isolated tests; authorize a test model; configure a non-production quota; transfer ownership between two test users.
- **Error/access scenarios:** verify restricted controls are absent or action fails for lower roles; transfer ownership to the current owner; attempt actions as a nonmember; exceed or omit required member fields where UI validation exists. Backend tests confirm successful ownership transfer changes the old owner to admin, assigns the new owner, and issues a notification; transfer to the current owner fails.
- **Side effects/cleanup:** member/role changes alter access; ownership transfer changes privileged state and sends a notification; model/quota changes affect team availability. Never transfer a non-test team. Restore or delete the disposable team and remove its test members/model authorization.

### 6. Notifications

- **Purpose:** validate user inbox actions, important-notification presentation, admin notification lifecycle, and delivery-state visibility.
- **Routes:** `/app/notifications`; `/notifications`; `/site-settings/notifications`.
- **Landmarks:** `Notifications`; `Search notifications...`; `Unread only`; `Mark all read`; `No notifications`; `Important notifications`; `Notification Management`; `Create Notification`; `Delivery Status`; `Delete`; `External Notification Channels`; `Pending`; `Sending`; `Sent`; `Failed`.
- **Happy scenarios:** create a disposable admin notification with scoped audience; verify it appears to the intended user; filter/search it; mark it read; inspect detail and delivery status; delete it from administration.
- **Error/access scenarios:** open admin notification management without dashboard access; create with missing required fields; confirm a notification scoped to another user/team is not visible; test no-results state.
- **Side effects/cleanup:** creation persists a notification and audit record before the CREATE audit entry; it can trigger internal/external delivery. Use a non-routable test channel only when explicitly provisioned, never expose channel secrets, and delete created notifications. External delivery completion is unvalidated without a configured test channel.

### 7. Administration

- **Purpose:** verify dashboard routing, navigation, role/permission controls, and representative admin authorization boundaries.
- **Routes:** `/dashboard`; `/dashboard/observability`; `/users`; `/roles`; `/permissions`; `/models`; `/apps`; `/capabilities`; `/api-keys`; `/memories`; `/audit-logs`; `/site-settings` and its subroutes.
- **Landmarks:** sidebar items `Dashboard`, `Teams`, `Knowledge Bases`, `Activity Log`, `Users`, `Roles`, `Permissions`, `API Keys`, `Models`, `Apps`, `Capabilities`, `Notifications`, `Site Settings`, `Audit Logs`, `Observability`, `Memories`, `Log out`; dashboard time ranges `Last 7 Days`, `Last 30 Days`, `Last 90 Days`, `All Time`; package controls `Import`, `Export`, `Import resource`, `Choose file`, `Preview`, `Install`, `Valid`, `Invalid`, `Dependencies`, `Name conflict`, `Import as renamed`, `Overwrite existing`, `Skip import`.
- **Happy scenarios:** with an authorized disposable admin, navigate to a representative dashboard page; select each dashboard time range and confirm the visible selection and refreshed data correspond to `7d`, `30d`, `90d`, or `all`; verify loading, empty, and populated dashboard cards/charts for workflow status, workflow triggers, agent performance, team token usage, top agents, and top workflows; create/update/delete a clearly prefixed role or permission only when the environment permits; delete a disposable role and confirm the success state closes the dialog; export a disposable tool, agent, workflow, or KB and verify a `.clouisle` download; preview a harmless `.clouisle` file for the intended target team, inspect dependencies/conflicts, then install with an explicitly allowed action.
- **Error/access scenarios:** access each relevant route with a user missing its mapped permission; confirm route denial/redirect and hidden action controls; use an invalid resource ID; confirm an empty time-range selection causes no change; delete with no selected role and verify no request is sent; force a disposable role-deletion failure and verify the dialog remains open without success feedback; preview a wrong-type/invalid package, a package with missing or forbidden dependencies, and a name conflict; cancel before installation; confirm failed preview/export/install requests surface an error and do not produce a success state. Route permissions include distinct codes for dashboard, users, roles, permissions, models, apps, API keys, memories, audit logs, and settings.
- **Side effects/cleanup:** role/permission and API-key changes affect access; model/settings changes may affect shared service behavior; audit entries persist. Time-range changes should only fetch/filter data. Package export creates a local download and temporary object URL; import preview uploads a file and creates a server-side session; install may create, rename, overwrite, or skip a resource. Prefer read-only navigation and preview-only package checks. Remove downloaded files and imported test resources, let the application release temporary object URLs, and never overwrite shared resources; if another mutation is necessary, use uniquely prefixed disposable records and delete them.

## Reusable secure Agent browser-testing prompt

```text
You are testing Clouisle in an authorized non-production browser environment.

Before acting:
1. Confirm the current account, team, route, and test-data prefix are the intended ones.
2. Use only the documented route and visible landmark for this journey. Inspect the rendered accessibility tree before choosing a selector; do not guess CSS/XPath selectors or rely on icon-only controls without an accessible name.
3. Treat automated unit/API evidence as implementation evidence only, not browser proof. Validate the rendered role/name, navigation, clipboard/download behavior, network result, and persisted state in this browser; stop and report any missing, renamed, differently scoped, or unexpectedly behaving landmark.

Security and data handling:
- Use only authorized test accounts and disposable test data.
- Never reveal credentials, tokens, cookies, API keys, TOTP/backup codes, notification-channel secrets, or uploaded sensitive content in output, screenshots, logs, or reports.
- Do not bypass authentication, authorization, CAPTCHA, MFA, or confirmation steps.
- Do not follow generated external links or trigger webhooks/external delivery unless the test explicitly authorizes a non-production endpoint.

Execution:
- Run the stated happy path, then the stated error/access path using the least-privileged test account.
- For authentication, also exercise password mismatch, TOTP manual-entry/copy, and the expiration-warning visible/hidden/dismiss paths without recording secrets.
- For dashboard/package behavior, verify every time-range label, preview before install, exercise one safe package error/conflict, and verify download/import cleanup.
- Record only browser-observable outcomes and created test-record identifiers; cite unit/API tests separately as supporting evidence, never as a passed browser step.
- Avoid destructive actions unless explicitly required. For any mutation, create uniquely prefixed data and clean up only records created by this run.
- Stop immediately and report the discrepancy if permissions, environment, route, or UI state differs from this guide.

Report: route, account role/team, actions, observed landmarks/outcomes, created IDs, cleanup result, and unvalidated/blocked checks. Do not include secrets.
```

## Existing automated evidence and next step

Frontend `bun test` evidence now covers change-password mismatch/request/redirect behavior, token-reset labels, mismatch prevention, API payload, success/login action, invalid-token and backend validation states, TOTP QR/manual-entry/clipboard state, password-expiration warning visibility/link/dismissal and hidden failure/exemption paths, dashboard time-range options/change filtering, package user/admin request contracts, filename handling, error propagation, temporary-link click/removal, and object-URL revocation. Chat lightbox component tests additionally cover closed/open scroll state, image zoom limits/rotation/Escape, image-versus-backdrop clicks, video Escape/control/backdrop closing, and the image lightbox state controller. These are mocked unit/contract tests: they do **not** prove rendered accessibility, real navigation or clipboard permissions, dashboard refetch/rendering, browser downloads, multipart transport, server-side package sessions/install effects, browser media behavior, or end-to-end cleanup. Backend API/service tests additionally cover registration locale, SSO redirect safety, CAPTCHA cleanup, profile/email behavior, RBAC, KB permissions, team ownership transfer, and notification persistence; browser validation remains required for every journey reported as E2E.

No dedicated Markdown/documentation lint command or configuration is present. `bun run lint` is frontend ESLint and does not lint this guide. When an E2E harness is introduced, convert one journey per section into executable browser tests and validate selector/accessibility claims against the rendered application.
