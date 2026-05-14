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
5. Do not invent undocumented behavior; verify against current code, configuration, workflow files, or lightweight command checks.

## Verification requirements

For documentation changes involving runnable commands, do not rely on static inference. Verify the documented working directory and use the lightest safe check available, such as importing the target module, running a non-mutating `--help` command, checking that a referenced script exists, or reading the referenced configuration file. If a command starts long-running services, databases, Docker containers, or network-dependent processes, do not run the full command; instead verify its executable path, module import path, script name, and required working directory.

For configuration and environment documentation, verify names and defaults against the source configuration files, examples, deployment manifests, or workflow definitions. If related files disagree, treat the change as uncertain until the current project behavior is clear.

## Cross-document consistency

When changing setup, quick start, deployment, environment variable, or command documentation, search related docs for the same concept before opening a PR. At minimum check `README.md`, `docs/guide/README.md`, `docs/guide/README_zh-CN.md`, `docs/guide/getting-started/**/*.md`, and relevant deployment docs when the affected topic appears there. Update all affected copies, including paired Chinese docs, or explain why a related copy is intentionally unchanged.

## Confidence policy

Open a normal PR only when each changed fact is verified against current code, config, workflow files, or a lightweight command check. If the proposed change is inference-heavy, only partially verified, or depends on an unsafe long-running command, prefer reporting the evidence and uncertainty with `noop` instead of opening a normal PR.

## Pull request requirements

If documentation updates are needed and the confidence policy is satisfied, request a pull request through the `create_pull_request` safe-output tool.

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
