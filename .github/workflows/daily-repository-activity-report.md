---
on:
  schedule: daily on weekdays
permissions:
  contents: read
  issues: read
  pull-requests: read
  actions: read
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
  create-issue:
    title-prefix: "[daily-report] "
    max: 1
---
# Daily Repository Activity Report

Create a daily issue that summarizes recent activity in `${{ github.repository }}`.

Use GitHub tools to inspect repository activity since the previous daily report or, if that cannot be determined, the last 24 hours. The report should focus only on new issues, pull requests merged, and any open blockers.

Include these sections in the issue body:

## Summary
- 2-4 concise bullets covering the most important activity from the reporting window.

## New Issues
- Issues opened during the reporting window.
- Include issue number, title, author, labels, and the likely follow-up.
- If no new issues were opened, write `No new issues.`

## Pull Requests Merged
- Pull requests merged during the reporting window.
- Include PR number, title, author, merger if available, and a short impact summary.
- If no pull requests were merged, write `No pull requests merged.`

## Open Blockers
- Open issues or pull requests that appear blocked, urgent, stale-but-important, failing CI, release-blocking, security-sensitive, or waiting for maintainer action.
- Include issue or PR number, title, owner or assignee when available, and the reason it looks blocked.
- If no blockers are found, write `No open blockers identified.`

Reporting rules:

- Create exactly one issue by calling the `create_issue` safe-output tool with a clear title and markdown body.
- Do not use direct GitHub write APIs, `gh issue create`, or mutation tools.
- If there is genuinely no repository activity, still create a short daily report issue with the required sections.
- Attribute automation-assisted activity to the humans involved when possible, such as PR authors, reviewers, assignees, mergers, or workflow triggerers.
- Keep the report concise and factual. Avoid speculation.
