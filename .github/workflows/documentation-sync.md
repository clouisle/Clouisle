---
on:
  schedule: daily on weekdays
permissions:
  contents: read
  issues: read
  pull-requests: read
engine:
  id: claude
  model: deepseek-v4-pro
  env:
    ANTHROPIC_BASE_URL: https://api.deepseek.com/anthropic
  api-target: api.deepseek.com
secrets:
  ANTHROPIC_API_KEY:
    value: ${{ secrets.DEEPSEEK_API_KEY }}
    description: DeepSeek API key for the Anthropic-compatible Claude engine endpoint
network:
  allowed:
    - defaults
    - api.deepseek.com
tools:
  github:
    toolsets: [default]
safe-outputs:
  create-pull-request:
    title-prefix: "[docs-sync] "
    labels: [documentation]
    assignees: [yunhai-dev]
    protected-files: fallback-to-issue
---
# Documentation Sync

Run a daily documentation freshness check for `${{ github.repository }}` and open a pull request when repository documentation is out of sync with recent code changes.

Use GitHub tools and the local repository checkout to compare recent code changes against documentation. Focus on changes since the previous documentation sync run or, if that cannot be determined, recent activity on the default branch.

## Documentation scope

Review documentation files that are likely to describe changed behavior, especially:

- `docs/**/*.md`
- `README.md`
- `frontend/README.md`
- `AGENT.md`
- `CHANGELOG.md`
- `deploy/README.md`
- `.github/*.md`

Do not update generated lock files or build artifacts.

## What to look for

Identify documentation that is stale because recent code changes changed:

- CLI commands, setup steps, environment variables, Docker or deployment behavior.
- API routes, request/response shapes, authentication, error handling, pagination, streaming, or webhooks.
- Frontend routes, user-visible workflows, configuration, or feature behavior.
- Workflow, agent, tool, notification, memory, RBAC, or access-control behavior.
- GitHub Actions, release flow, labels, issue workflow, or contribution process.

## Update rules

When docs are out of sync:

1. Make the smallest documentation edits needed to match the current code.
2. Keep existing document structure and style.
3. Update both English and Chinese versions when a paired `_zh-CN.md` file exists and the same content is affected.
4. Do not rewrite broad sections unless the code change requires it.
5. Do not invent undocumented behavior; verify against code or workflow files.

## Pull request requirements

If documentation updates are needed, request a pull request through the `create_pull_request` safe-output tool.

The PR should include:

- A concise title using the configured `[docs-sync] ` prefix.
- A body summarizing which recent code changes made the docs stale.
- A bullet list of documentation files changed.
- A short validation note explaining how the updates were checked.

If no documentation updates are needed, call `noop` with a short explanation.

## Safety rules

- Do not push directly to any branch.
- Do not use direct GitHub mutation APIs or `gh pr create`.
- Do not modify source code unless it is part of a documentation example that must match the current code.
- Prefer a small PR over broad documentation cleanup.
