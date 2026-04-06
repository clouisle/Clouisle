# Dependency License Compliance

This repository enforces dependency license policy in CI for both backend and frontend dependencies.

## Scope

- Backend check: `backend/scripts/check_licenses.py`
- Frontend check: `frontend/scripts/check-licenses.mjs`
- Shared policy: `license-policy.yml`
- CI integration: `.github/workflows/ci.yml`

The current policy focuses on runtime dependencies.

## Local commands

### Backend

```bash
uv sync --project backend --all-extras --dev
uv run --project backend python scripts/check_licenses.py
```

### Frontend

```bash
bun install --cwd frontend
bun run --cwd frontend license:check
```

## Policy file

`license-policy.yml` defines:

- `allowed_licenses`
- `conditionally_allowed_licenses`
- `denied_licenses`
- `defaults.action_on_unknown`
- `defaults.include_dev_dependencies`
- `defaults.fail_on_missing_license`
- `exceptions`

## Exception rules

Each exception should be explicit and temporary. Include:

- `ecosystem`: `python` or `node`
- `package`
- `version` when the exception is version-specific
- `license` when the exception applies to a specific detected license
- `justification`
- `owner`
- `expires_on`

Example:

```yaml
exceptions:
  - ecosystem: python
    package: example-package
    version: "1.2.3"
    license: LGPL-3.0-only
    justification: approved-by-legal
    owner: engineering
    expires_on: 2026-12-31
```

Expired exceptions are ignored.

## Normalization behavior

The checkers normalize common license aliases before evaluating policy, including:

- `Apache 2.0` -> `Apache-2.0`
- `MIT License` -> `MIT`
- `BSD License` -> `BSD-3-Clause`
- `Python Software Foundation License` -> `PSF-2.0`

They also evaluate simple license expressions:

- `A OR B`: passes if any branch is allowed
- `A AND B`: passes only if all branches are allowed
- `UNKNOWN` or missing license: fails by default

## Frontend Next.js image optimization rule

The frontend checker contains one conditional runtime-path filter for Next.js image optimization packages.

- `frontend/next.config.ts` currently sets `images.unoptimized: true`
- When this flag is enabled, `frontend/scripts/check-licenses.mjs` ignores the optional `next -> sharp -> @img/sharp-libvips-*` chain
- This ignore rule exists because those packages correspond to the disabled built-in image optimization path and are not part of the active runtime behavior

If `images.unoptimized` is removed or changed back to `false`, the ignore rule no longer applies and the `sharp` / `libvips` chain will be checked normally.

## CI behavior

Both jobs in `.github/workflows/ci.yml` run license checks after dependency installation:

- backend: `uv run python scripts/check_licenses.py`
- frontend: `bun run license:check`

A violation fails the job and blocks the PR.
