# Global Watermark Design Document

## Background & Goals

Screenshots of signed-in pages cannot be traced back to the account that produced them. Administrators need a global, per-user watermark that is configured in the UI and takes effect without a redeploy.

Goals:

- A new Site Settings subpage `/site-settings/watermark` (default **off**) persisted through the existing `site_settings` key/value store and delivered through the existing public site-settings endpoint.
- Content is a template rendered per user: `{username}`, `{email}`, `{site_name}`, `{date}`, `{time}`; default `{username} {date} {time}`.
- Style configuration: opacity, font size, rotation, tile gap, text color (empty = theme foreground).
- Coverage limited to authenticated route groups `(dashboard)`, `(platform)`, `(chat)` — never `(auth)` or `(embed)`.
- Reuse `admin:settings:read` / `admin:settings:update`; no new permission.

## High-Level Design

```
admin UI (/site-settings/watermark)
  → PUT /api/v1/admin/site-settings   (bulk, category=watermark)
    → Watermark rows in site_settings (public=True)
      → GET /api/v1/site-settings/public   (normalized bounds/template/color)
        → SiteSettingsProvider (client) → GlobalWatermark in each authenticated layout
          → WatermarkOverlay (SVG pattern, per-user text)
```

Defaults, bounds and the maximum template length live once in `backend/app/models/site_setting.py` (`WATERMARK_DEFAULT_CONTENT`, `WATERMARK_CONTENT_MAX_LENGTH`, `WATERMARK_INTEGER_BOUNDS`, `WATERMARK_SETTING_DEFAULTS`) and once in `frontend/lib/watermark.ts` (`DEFAULT_WATERMARK_CONTENT`, `WATERMARK_DEFAULTS`, `WATERMARK_LIMITS`). No database migration is needed: `init_default_settings()` seeds absent keys on startup.

Invalid persisted values cannot break the browser: the public endpoint clamps integers into bounds, replaces blank/oversized templates with the default, and normalizes the color to `""` when it is not a hex value. The admin endpoint rejects such values up front.

The overlay is a `pointer-events-none select-none` fixed layer (`z-[9999]`) containing one `<svg>` whose `<pattern>` paints the text (`fill="currentColor"`, so the theme foreground works without JS theme reads). The pattern id comes from `React.useId()` with non-alphanumerics stripped because `:` would break `url(#...)`.

## Implementation Plan

### Stage 1: Backend settings definition, public contract, validation

- **Files**: `backend/app/models/site_setting.py`, `backend/app/schemas/site_setting.py`, `backend/app/api/v1/endpoints/site_settings.py`, `backend/app/api/v1/admin/endpoints/site_settings.py`
- **Logic**: constants + seven `category: "watermark"` / `public: True` defaults; `WATERMARK_SETTING_DEFAULTS` derived from `DEFAULT_SETTINGS`; seven fields on `PublicSiteSettingsResponse`; `_normalize_bounded_int` / `_normalize_watermark_content` applied in `get_public_settings`; `_validate_setting_value` accepts booleans, non-blank ≤200-character templates, in-bounds integers, and `""`/hex colors.
- **Validation**: unit tests over every accept/reject case plus clamping; `ruff check`.

### Stage 2: Frontend contract and rendering primitives

- **Files**: `frontend/lib/watermark.ts`, `frontend/lib/api/site-settings.ts`, `frontend/lib/api/admin/site-settings.ts`, `frontend/contexts/site-settings-context.tsx`, `frontend/components/watermark/watermark-overlay.tsx`, `frontend/components/watermark/global-watermark.tsx`, the three authenticated layouts
- **Logic**: `renderWatermarkText` (local `YYYY-MM-DD`/`HH:mm`, unknown placeholders literal, whitespace collapsed, site-name/`Clouisle` fallback); `getWatermark` clamps numbers and falls back to defaults; `GlobalWatermark` renders only when the public settings are loaded, the watermark is enabled, `localStorage.access_token` exists, and the current user has resolved.
- **Validation**: render the overlay and inspect the emitted SVG; tests for placeholder rendering and each gate.

### Stage 3: Watermark settings subpage

- **Files**: `frontend/lib/route-permissions.ts`, `frontend/app/(dashboard)/site-settings/watermark/page.tsx`, `frontend/i18n/{en,zh}/siteSettings.json`
- **Logic**: permission entry + nav item; switch, template input, four `NumberInput`s, color picker with "auto" reset, live preview, per-field validation (required, ≤200, range, hex), save through `updateWatermark` then `refreshSiteSettings()`.
- **Validation**: page tests for loaded values, full save payload, and blocked saves; `i18n:gen-types`, `i18n:lint`, `i18n:check`.

### Stage 4: Documentation and verification

- **Files**: `CHANGELOG.md`, `docs/guide/admin-guide/settings/system-settings.md`, `docs/guide/api-reference/endpoints/settings.md`
- **Validation**: backend settings tests, frontend affected tests, `tsc --noEmit`, `eslint`, `ruff`, i18n checks.

## Testing Strategy

- Backend (`backend/tests/api/test_site_settings_watermark.py`): `_validate_setting_value` accept/reject matrix; `get_public_settings` clamping (`opacity 999 → 50`, `rotation -120 → -90`, `gap 12 → 60`), default-template fallback for blank/oversized content, and invalid color → `""`.
- Frontend: `lib/watermark.test.ts` (placeholders, literal unknown placeholder, whitespace, fallbacks), `components/watermark/global-watermark.test.tsx` (enabled + token + identity, disabled, no token, load failure), `app/(dashboard)/site-settings/watermark/page.test.tsx` (loaded values, save payload, blocked saves), `lib/api/admin/site-settings.test.ts` (client-side clamping), plus the three layout tests asserting the mount point.
- Regression scope: existing site-settings normalization/theme tests, settings page test, site-settings context test, route-permission tests.

## Ant Design Reference

Tiling follows Ant Design's `Watermark` (`components/watermark/useClips.ts`):

- **"Fill alternate" tile** — each pattern cell holds three marks: one cell plus the neighbouring column twice, shifted up and down by half a row, so columns interleave instead of forming a grid. Pitch is `rotatedWidth + gap` and `rotatedHeight + gap`, exactly antd's `cutWidth + gapX` / `cutHeight + gapY`. The rotated bounding box is derived from `|cos|`/`|sin|` of the text box (antd rotates the four corners).
- **Text width is measured, not estimated** — a hidden `<text>` is read through `getComputedTextLength()` and re-measured once `document.fonts.ready` settles; a `0.6 × fontSize` per-character estimate is used before measurement and whenever the API is unavailable (SSR, test renderer). antd uses `ctx.measureText` for the same purpose.
- **Rotation is applied per `<text>`** (`transform="rotate(...)"`) rather than via `patternTransform`, because rotating the tile grid clips each string at the tile edge.
- **Defaults follow antd's feel**: `rotate -22°`, `gap 120` (antd: `-22°`, `[100, 100]`), opacity 10% instead of antd's `rgba(0,0,0,.15)` ink so the overlay follows the theme and is admin-tunable.
- **The mark is scaled to fit the viewport** — a 200-character template at the largest font size is wider than a phone, so the rendered font size (and the tile with it) is reduced until one complete mark fits `window.innerWidth - gap`.
- **Identity, token and clock lifecycle** — the overlay renders only for a resolved identity, so a failed lookup never leaves a bare timestamp; a `storage` event for `access_token` re-resolves the identity for multi-tab sign-in/out; `{date}`/`{time}` tick about once a minute and on `visibilitychange`.
- **The settings page never saves values it did not load** — a failed `getWatermark()` shows the load error with retry and keeps the form unsavable, so defaults cannot overwrite stored settings. The color control expands `#rgb`/`#rgba` to `#rrggbb` for the native picker and shows an explicit auto (theme foreground) state instead of a black swatch when no color is set.

Not adopted: `image` watermarks, multi-line `content`, `offset`, `inherit` (Modal/Drawer propagation), and the `MutationObserver` anti-tamper restore. The last one is a deliberate omission: React owns our overlay node, so re-appending it imperatively would fight the reconciler for a marginal gain over `pointer-events-none` + a high `z-index`.

## Risks & Mitigation

- **Leaking a secret through public configuration** — `watermark_content` is public; documented as such in the admin guide.
- **Invalid persisted rows rendering `NaN` SVG attributes or blank overlays** — the public endpoint normalizes every field; the client normalizes again.
- **Hydration mismatch from dates** — the overlay renders nothing until a client-side identity check finishes, so no date is rendered during SSR.
- **Rollback** — disable the switch (or reset the `watermark` category); the seven `site_settings` rows are inert when `watermark_enabled` is false.
