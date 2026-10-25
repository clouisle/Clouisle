# Model Provider Icons & Provider Labels Design Document

Status: Implemented (2026-10-25). Verification: full frontend suite passes; coverage 95.88% functions / 98.00% lines; ESLint 0 errors; `tsc --noEmit` clean.

Update after visual check: custom gateways showed the neutral gateway mark for every model, so a per-model manual icon selector was evaluated and rejected because it requires a new `models.provider_icon` column and API payload changes. Instead, `custom` providers now infer a model-family icon from `model_id` (for example `gpt-5.6-terra → openai`, `gemini-3.8-flash → google`, `LongCat-2.0 → longcat`, `BAAI/bge-m3 → baai`). Built-in providers keep their canonical mark; unrecognized custom model ids keep the gateway mark. No database or backend change is required.

## Background & Goals

### Problem

Provider identity is missing or inconsistent wherever a model is displayed.

- The backend already declares an icon slug per provider (`PROVIDER_DEFAULTS[*]["icon"]`, `backend/app/models/model.py:70`) and exposes it as `ProviderInfo.icon` (`backend/app/schemas/model.py:134`, `GET /models/providers`), but the frontend never reads it. There are no brand assets under `frontend/public` except the Clouisle logo and `integrations/feishu.*`.
- Provider labels already exist in i18n (`models.providers.*` in `frontend/i18n/en/models.json:210` and `frontend/i18n/zh/models.json:199`), and `provider_display_name` is available on `Model` and `ModelBrief`.
- Surfaces that render only a type icon make every provider look identical:
  - `frontend/app/(platform)/app/models/_components/model-card.tsx` uses a lucide model-type icon inside a provider-colored tile.
  - `frontend/app/(platform)/app/models/_components/model-detail-dialog.tsx` uses the same type icon in the dialog header.
  - `frontend/app/(platform)/app/apps/[id]/_components/agent-settings-drawer.tsx:273` hard-codes a green `MessageSquare` tile for every model.
- Surfaces that show only `model.name` hide the provider entirely:
  - KB embedding/rerank selects (`frontend/app/(platform)/app/kb/_components/kb-dialog.tsx:330-382`).
  - Agent model selects (`agent-config-form.tsx:286-292`, `agent-settings-drawer.tsx`).
  - Workflow node pickers (`llm-node-config.tsx`, `question-classifier-node-config.tsx`, `parameter-extractor-node-config.tsx`, `decision-node-config.tsx`, `media-generation-node-config.tsx`).
  - Admin team model authorization (`frontend/app/(dashboard)/teams/_components/team-models-tab.tsx`).
- Some surfaces print the raw provider code instead of the localized label, bypassing existing i18n:
  - `frontend/app/(dashboard)/teams/_components/team-models-tab.tsx:405-407,347-350` (`provider_display_name || provider`).
  - `frontend/app/(platform)/app/kb/[id]/page.tsx:327,339`.

### Goals

1. Every model display/selection surface shows a provider icon and a provider label from one shared primitive.
2. `provider_display_name` (custom gateway name) takes precedence over the provider catalog name.
3. Unknown or newly added providers degrade to a deterministic monogram tile instead of rendering nothing.
4. No runtime network requests, no new runtime dependency, correct in light and dark themes.

### Non-Goals

- No backend, database, or API changes. `ProviderInfo.icon` remains the catalog hint; provider code is the frontend key.
- No sub-brand / model-family logos (GPT, Claude, Qwen variants); provider level only.
- No restyling of the workflow canvas node bodies, admin observability tables, or dashboard charts.
- No change to which models are available or how they are authorized.

## High-Level Design

### New shared units

| Unit | Path | Responsibility |
|---|---|---|
| Icon assets | `frontend/components/model-provider/icons/*.tsx` | Vendored monochrome brand marks, `currentColor`, one file per slug |
| ProviderIcon | `frontend/components/model-provider/provider-icon.tsx` | Resolve slug, render mark or monogram fallback, size/aria |
| ProviderLabel | `frontend/components/model-provider/provider-label.tsx` | Icon + resolved label, optional icon suppression |
| useProviderLabel | `frontend/hooks/use-provider-label.ts` | `models.providers.*` lookup with `provider_display_name` precedence |
| Pure helpers | `frontend/lib/model-provider.ts` | Slug map, tint map, `resolveProviderLabel`, fallback initial |

The directory is named `model-provider` on purpose: `frontend/components/providers/` is the React context provider barrel (`frontend/components/providers/index.tsx`).

### Icon source decision

Vendor the monochrome SVG path data from `lobehub/lobe-icons` (MIT) at a pinned release, converting each brand's `Mono` component into a local TSX component. Rationale, with evidence:

- Adding `@lobehub/icons` at runtime requires peer `@lobehub/ui ^6` (verified from the published `package.json`); its brand barrels import `features/IconAvatar` and `features/IconCombine`, which import `Center`, `useThemeMode`, and `Flexbox` from `@lobehub/ui`. That pulls a CSS-in-JS UI library in for ~20 logos. Rejected.
- `simple-icons` (16 MB unpacked) has coverage gaps. Verified via `cdn.simpleicons.org` on 2026-10-25: `zhipuai`, `baichuan`, `xai`, `microsoftazure`, `stabilityai`, `runway`, `luma`, `klingai`, `midjourney`, `volcengine`, `siliconcloud` all return 404; `anthropic`, `googlegemini`, `deepseek`, `qwen`, `moonshotai`, `minimax`, `ollama` resolve. Using it as the sole source still leaves half the providers on fallbacks. Rejected.
- Hand-drawn approximations are inaccurate and look unprofessional.
- Vendored MIT path data is offline, tree-shakeable, theme-adaptive, and reviewable.

License facts (verified 2026-10-25):

- npm metadata for `@lobehub/icons@6.9.1`: `"license": "MIT"`; repository `github.com/lobehub/lobe-icons`.
- Repo `LICENSE`: MIT License, Copyright (c) 2023 LobeHub.
- `license-policy.yml` lists MIT in `allowed_licenses`, so vendoring is policy-compliant. The vendored files are not a package dependency, so `license:check` will not see them; compliance is manual.

MIT requires the copyright and permission notice to accompany copies or substantial portions. Add `frontend/components/model-provider/icons/LICENSE` containing the upstream MIT text plus the pinned source tag/commit, and keep a short header comment (`Vendored from lobehub/lobe-icons @ <tag>, MIT`) in the registry file.

Trademarks are excluded from the MIT grant: the marks remain the property of each provider, so the practical answer is "yes, with usage limits", not "free to use anywhere".

Allowed, low-risk usage (the intended scope):

- Inside authenticated product UI, next to the provider's own name, solely to identify that provider in a model row, picker, or detail view.
- Text label always present, so the mark is not the sole identifier.
- No alteration of the mark's geometry, no combining with the Clouisle logo, no implied partnership or endorsement.
- A visible notice such as "All product names, logos, and brands are property of their respective owners" in the legal/third-party notices page.

Disallowed usage:

- Product logo, app icon, favicon, OG image, email header, or any place that reads as Clouisle's own brand.
- Marketing pages, ads, comparison tables, case studies, or customer-facing decks implying endorsement or partnership.
- Removing, stretching, re-coloring in a way that breaches a provider's brand guidelines, or using a mark for a provider the product does not actually support.

Monochrome caveat: `currentColor` rendering is technically a re-color. It is the common pattern in developer tools, but some brand guidelines require official colors. If strict compliance is required, switch those marks to official color variants (which also removes the dark-mode contrast problem) and keep the tint tile only for the monogram fallback.

Operational guardrails:

- Central registry only; no ad-hoc logo imports elsewhere, so a mark can be removed or replaced in one commit.
- Monogram fallback already covers removal: dropping a slug degrades to a letter tile, no layout change.
- Keep the vendored license/notice file and record the source tag with each asset update.
- This is engineering guidance, not legal advice; obtain counsel review if the product is sold into a jurisdiction or contract that requires trademark clearance.

Estimated addition: 23 marks, roughly 10–15 KB gzip, loaded only through `ProviderIcon`.

### Provider → slug map

Mirrors `PROVIDER_DEFAULTS` in the backend:

```
openai → openai
openai_responses → openai
anthropic → anthropic
google → google
xai → xai
azure_openai → azure
deepseek → deepseek
moonshot → moonshot
zhipu → zhipu
qwen → qwen
baichuan → baichuan
minimax → minimax
volcengine → volcengine
siliconflow → siliconcloud
ollama → ollama
runway → runway
pika → pika
luma → luma
kling → kling
stability → stability
midjourney → midjourney
typesafe → typesafe
custom → gateway (neutral gateway mark)
```

Unknown code → monogram fallback.

### Visual contract

- Monochrome mark using `currentColor`, inside an optional tinted rounded tile. The tint map is the existing `providerColors` from `model-card.tsx` moved to `frontend/lib/model-provider.ts` and extended with every provider code (light and dark variants).
- Sizes: 14 px in dense select items and pills, 16 px in table/list rows, 20 px in card headers, 24 px in detail/dialog headers.
- Dense option row: icon + model name (primary) + `provider label · model_id` (secondary, muted, truncated).
- Trigger: icon + model name; append the provider label in muted text where the trigger has room (`Provider · Model`), never rely on the trigger alone to convey the provider.
- Monogram fallback: rounded tinted tile with the first grapheme of the display label, deterministic tint from the provider code hash.
- Accessibility: icon is `aria-hidden` when adjacent text exists; otherwise `role="img"` with the provider label.

### Surfaces

| Surface | File | Change |
|---|---|---|
| Admin models table | `frontend/app/(dashboard)/models/_components/models-client.tsx:494` | Provider cell renders icon + localized label |
| Admin model dialog | `frontend/app/(dashboard)/models/_components/model-dialog.tsx:1128-1240` | Icon in the provider trigger and each provider grid button |
| Admin team models tab | `frontend/app/(dashboard)/teams/_components/team-models-tab.tsx:347-407` | Icon + localized label in authorized rows and add-model rows |
| Platform model catalog cards | `frontend/app/(platform)/app/models/_components/model-card.tsx:108-130` | Provider icon replaces the type icon; provider badge keeps the type badge |
| Model detail dialog | `frontend/app/(platform)/app/models/_components/model-detail-dialog.tsx:120-144` | Provider icon in the header tile |
| Platform team page cards | `frontend/app/(platform)/app/team/page.tsx:526-537` | Icon tile beside the model name; localized provider line |
| KB create/edit dialog | `frontend/app/(platform)/app/kb/_components/kb-dialog.tsx:330-382` | Icon + provider label in embedding/rerank options and triggers |
| KB detail page | `frontend/app/(platform)/app/kb/[id]/page.tsx:327,339` | Localized provider label instead of raw code |
| Agent config form | `frontend/app/(platform)/app/apps/[id]/_components/agent-config-form.tsx:286-292` | Icon + provider label in options and trigger |
| Agent settings drawer | `frontend/app/(platform)/app/apps/[id]/_components/agent-settings-drawer.tsx:270-274` | Replace the green `MessageSquare` tile with `ProviderIcon`; add provider label |
| Agent toolbar chip | `frontend/app/(platform)/app/apps/[id]/_components/agent-toolbar.tsx:91-96` | `ProviderIcon` + model name; provider label in the tooltip |
| Agent orchestration media selects | `frontend/app/(platform)/app/apps/[id]/_components/agent-orchestration-form.tsx:830-840,971-981` | Icon + provider label in options |
| Workflow LLM node | `.../node-config/configs/llm-node-config.tsx:234-292` | Icon per row; provider group header keeps the label; trigger adds the provider label |
| Workflow decision node | `.../decision-node-config.tsx:126-136` | Icon per row |
| Workflow question classifier | `.../question-classifier-node-config.tsx:277` | Icon + provider label in options; trigger suffix |
| Workflow parameter extractor | `.../parameter-extractor-node-config.tsx:346` | Icon + provider label in options; trigger suffix |
| Workflow media generation | `.../media-generation-node-config.tsx:202-212` | Icon + provider label in options; trigger suffix |

## Implementation Plan

### Stage 1: Shared primitives and assets

- **Files added**
  - `frontend/components/model-provider/icons/<slug>.tsx` (23 files) + `icons/index.tsx` registry.
  - `frontend/components/model-provider/provider-icon.tsx`, `provider-label.tsx`, `index.ts`.
  - `frontend/hooks/use-provider-label.ts`.
  - `frontend/lib/model-provider.ts`.
- **Specific logic**
  - `resolveProviderIcon(provider)` trims input, applies the alias map, returns the registry entry or `undefined`.
  - `ProviderIcon` renders `<svg>` for known slugs; otherwise a `span` monogram tile. Props: `provider`, `label?`, `size = 16`, `className`, `decorative` (default true).
  - `resolveProviderLabel(t, provider, displayName)` returns trimmed `displayName`, else `t('providers.<code>')` when `t.has` is true, else the code.
  - `useProviderLabel()` binds `useTranslations('models')` once.
  - Tint map covers all 23 provider codes plus a default.
- **Validation**
  - Render each registry entry and confirm exactly one `<svg>` with a non-empty `viewBox`.
  - Unknown provider (`"acme"`) renders exactly one monogram character and no SVG.
  - Whitespace-only `provider_display_name` falls back to i18n in both locales.
  - `openai_responses` renders the same mark as `openai`.

### Stage 2: Admin surfaces

- **Files modified**
  - `frontend/app/(dashboard)/models/_components/models-client.tsx`
  - `frontend/app/(dashboard)/models/_components/model-dialog.tsx`
  - `frontend/app/(dashboard)/teams/_components/team-models-tab.tsx`
- **Specific logic**
  - Provider cell and provider grid buttons use `ProviderLabel size={14|16}`.
  - Team models tab replaces `provider_display_name || provider` with the localized resolver; icons appear in both lists.
  - Preserve existing `data-testid` attributes and DOM text for tooltips.
- **Validation**
  - Admin table row for a `deepseek` model shows the DeepSeek mark and localized label.
  - A model with `provider_display_name: "Acme Gateway"` shows "Acme Gateway", not "DeepSeek".
  - Provider grid keeps the selected check indicator and 3-column layout without clipping.

### Stage 3: Platform catalog, team, and knowledge base

- **Files modified**
  - `model-card.tsx`, `model-detail-dialog.tsx`, `team/page.tsx`, `kb/_components/kb-dialog.tsx`, `kb/[id]/page.tsx`.
- **Specific logic**
  - Card header tile renders the provider mark; the model-type badge stays in the metadata row.
  - KB selects and detail page use the shared label resolver.
- **Validation**
  - Cards for OpenAI, Anthropic, and DeepSeek are visually distinguishable with no type-icon regression.
  - KB detail shows localized provider names in both locales.

### Stage 4: Agent and workflow pickers

- **Files modified**
  - `agent-config-form.tsx`, `agent-settings-drawer.tsx`, `agent-toolbar.tsx`, `agent-orchestration-form.tsx`.
  - Workflow `llm-node-config.tsx`, `decision-node-config.tsx`, `question-classifier-node-config.tsx`, `parameter-extractor-node-config.tsx`, `media-generation-node-config.tsx`.
- **Specific logic**
  - Options: icon + model name + secondary `provider label · model_id`.
  - Trigger: icon + model name, muted provider suffix where the trigger is wide enough.
  - Searches keep matching `provider_display_name` (already the case in LLM/media/decision configs).
- **Validation**
  - Every picker shows the provider for the selected and each listed model.
  - Existing search/grouping behavior and selected-state highlighting remain unchanged.

### Stage 5: Verification and cleanup

- Remove any local `getProviderName` copies in files touched where the shared hook fully replaces them; leave unrelated modules untouched.
- Confirm no dead exports or unused imports remain.
- Run the full frontend test and coverage gates.
- Final manual visual pass requires explicit user permission to start the dev server; otherwise report the limitation.

## Testing Strategy

- New unit tests
  - `frontend/components/model-provider/provider-icon.test.tsx`: every slug renders one SVG; alias resolution; custom-gateway family inference; unknown provider monogram; size/class/aria behavior; deterministic fallback initial.
  - `frontend/lib/model-provider.test.ts`: label precedence, trimming, unknown code fallback, slug map parity with the provider list used by i18n, and family inference precedence (canonical provider wins; inference only for `custom`).
- Updated tests (mock `ProviderIcon` or assert rendered text/icons)
  - `model-card.test.tsx`, `model-detail-dialog.test.tsx`, `models-client*.test.tsx`, `model-dialog*.test.tsx`, `team-models-tab.test.tsx`.
  - `kb-dialog.test.tsx`, `agent-config-form-issue255.test.tsx`, `agent-settings-drawer.test.tsx`, `agent-config-components.test.tsx`.
  - `decision-node-config.test.tsx`, `media-generation-node-config.test.tsx`, `question-classifier-node-config.test.tsx`, `parameter-extractor-node-config.test.tsx`, `workflow-node-config-lcov.test.tsx`.
- Gates
  - `bun test --isolate` for affected files during development, then `bun run test:coverage` (95% lines/functions, `scripts/run-coverage.ts`).
  - `bun run coverage:check` so every new eligible source appears in LCOV.
  - `bun run lint`; `bunx tsc --noEmit`.
  - `bun run i18n:check` (no new keys expected, but the hook adds a lookup path).
- Negative paths
  - Unknown provider, whitespace-only display name, long custom gateway name truncation, dark theme legibility.

## Risks & Mitigation

- **Trademark/copyright**: brand marks belong to their owners; path data is MIT-licensed from `lobe-icons`. Keep attribution/license beside the assets and use marks only to identify the provider. Replace assets if the user supplies official files.
- **Provider drift**: the backend enum and the vendored map can diverge. A parity test locks the known provider codes; the monogram fallback keeps new providers usable until an asset is added.
- **Test-mock churn**: many component tests mock `lucide-react`; new imports must mock `@/components/model-provider` consistently, or tests will attempt real rendering. Update affected mocks in the same change.
- **Density regressions**: the provider grid is 3 columns and select triggers are narrow. Use 14 px icons, `shrink-0`, and truncation; verify the longest labels (`OpenAI Responses`, `Stability AI`) at both locales.
- **Bundle size**: vendored marks are one client module; do not import the registry from server components or unrelated routes.

## Rollback

The change is additive frontend UI plus label resolution. Revert the surface edits to restore prior rendering; assets and shared primitives can remain without affecting behavior. No database or API rollback is required.
