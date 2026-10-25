# Frontend Conventions

This document collects implementation rules for the Next.js frontend.

## API client usage

Use the shared client from `frontend/lib/api/client.ts`.

### Rules

- Prefer `api.get/post/put/patch/delete` for standard JSON APIs.
- API methods return the unwrapped `data` field.
- Non-zero backend codes throw `ApiError`.
- Auth errors (`2000-2999`) redirect to login automatically.
- Validation errors (`1001`) should be handled with `error.getFieldErrors()`.
- Use `silent: true` if a request should suppress global toasts.
- Preserve localized, user-facing backend error guidance regardless of message length; permission scopes and recovery steps can exceed 200 characters. Message keys and technical details still fall back to generic errors. Verify both HTTP error responses and HTTP 200 business errors.

### File downloads

Use `axiosInstance` directly with `responseType: "blob"` for downloads.

## UI component rules

- shadcn/ui base-vega components use `render`, not `asChild`.
- Use `AlertDialog` instead of native `confirm()`.
- Use `Tooltip` instead of native `title`.
- In dialogs, add `alignItemWithTrigger={false}` to `SelectContent`.

### Select with i18n

If `SelectItem` labels are translated, render the translated label explicitly inside `SelectValue` so raw option values do not appear.

## Input handling

### Chinese IME

Check `e.nativeEvent.isComposing` in keyboard handlers before responding to Enter and similar actions.

### Decimal input

Prefer `type="text"` with `inputMode="decimal"` and regex validation instead of `type="number"` when decimal input must work reliably across browsers.

### Dashboard server search

Main server-backed searches in the dashboard activity, audit, application, capability, knowledge-base, document, memory and model lists use `useDebounce(rawSearch, 300)`. Keep input display immediate; use the debounced term for API parameters and search-driven page resets. When a new term settles on a later page, reset to page 1 before fetching so no abandoned-page request is issued. Discrete filters and pagination remain immediate. Existing 500 ms search integrations retain their durations.

Audit export is an explicit action and uses the current typed search term, even if the table's 300 ms search delay has not yet elapsed.

### Platform paginated lists

Platform `/app` application, knowledge-base, API-key, document, notification, and execution-log lists load subsequent server pages when their bottom sentinel becomes visible. Use `useInfiniteScroll` from `@/hooks/use-infinite-scroll`; keep the sentinel mounted within the scrollable content and preserve existing rows during append requests. Dashboard tables retain their pagination controls.

Search and filter changes restart at page 1; server-backed text search is debounced by 300 ms. Invalidate obsolete requests when query context changes or the component unmounts. Suppress observer loading after a failed request and provide an explicit retry of the failed operation. Stop at the server total and deduplicate records by identity.

Document processing refreshes the loaded window, rather than dropping appended pages. Notification mutations refresh the loaded window to avoid skipping shifted unread records. The applications all-tab merges independently paginated Agent and Workflow sources: sorting covers the loaded union, not a globally ordered cross-resource cursor.

## Hydration

Use a mounted-state guard for UI that depends on `localStorage` or browser-only state.

## Cursor styles

All interactive elements should include the right cursor class:
- clickable: `cursor-pointer`
- draggable: `cursor-grab` / `cursor-grabbing`
- disabled: `cursor-not-allowed`
- text input: `cursor-text`

## Date formatting

Use the shared utilities from `@/lib/utils`:

```typescript
import { formatDateTime, formatDate } from '@/lib/utils'
```

Target formats:
- `formatDateTime(dateString)` → `2026/02/03 16:10`
- `formatDate(dateString)` → `2026/02/03`

Do not use `toLocaleDateString()` or `toLocaleString()` directly for app dates.

## Dashboard vs platform isolation

The frontend has separate route groups and layout assumptions.

### Dashboard

- Location: `frontend/app/(dashboard)/`
- Audience: administrators
- Layout: sidebar-based
- Uses `frontend/lib/api/admin/`

### Platform

- Location: `frontend/app/(platform)/`
- Audience: regular users
- Layout: header-based
- Uses `frontend/lib/api/`

### Rules

- Do not cross-import page-specific components between dashboard and platform routes.
- Keep route-specific components inside each route's `_components/` directory.
- Shared APIs and shared types can still live in common modules.

## Route component structure

- Use `_components/` for route-local components.
- Keep file names in kebab-case.
- Export component symbols in PascalCase.
- Add an `index.ts` barrel in each `_components/` directory when that route uses multiple files.

## Layout-specific gotchas

- Dashboard pages inherit different height and rounded-corner behavior from `SidebarInset`.
- Platform pages often need explicit `calc(100vh - 64px)` height handling.
- If sticky positioning fails, check parent overflow and height constraints.

## Related docs

- `../analysis/frontend/00-overview.md`
- `../api/BACKEND_API.md`
