---
on:
  issues:
    types: [opened, edited, reopened]
permissions:
  contents: read
  issues: read
  pull-requests: read
engine:
  id: codex
  model: deepseek-v4-pro
  env:
    OPENAI_BASE_URL: https://api.deepseek.com
    OPENAI_API_KEY: ${{ secrets.DEEPSEEK_API_KEY }}
network:
  allowed:
    - defaults
    - api.deepseek.com
tools:
  github:
    toolsets: [default]
safe-outputs:
  add-labels:
    allowed:
      - bug
      - documentation
      - duplicate
      - enhancement
      - help wanted
      - invalid
      - question
      - priority:high
      - priority:medium
      - priority:low
    max: 4
    target: triggering
  add-comment:
    max: 1
    target: triggering
  assign-to-user:
    allowed: [yunhai-dev]
    max: 1
    target: triggering
---
# Issue Triage

Triage the triggering issue in `${{ github.repository }}`.

Use GitHub tools to inspect the issue body, labels, comments, and recent related issues. Do not mutate GitHub directly. Apply all changes through safe-output tools only.

## Goals

1. Label the issue by type.
2. Label the issue by priority.
3. Identify likely duplicates.
4. Ask clarifying questions when the issue is unclear or missing key details.
5. Assign the issue to the right team member when there is enough signal.

## Type labels

Choose at most one primary type label unless the issue clearly needs more:

- `bug`: broken behavior, regression, error, crash, failed workflow, incorrect result.
- `enhancement`: new feature request or meaningful improvement to existing behavior.
- `documentation`: docs, README, examples, deployment instructions, or copy-only improvements.
- `question`: support request, usage question, unclear intent, or missing requirements.
- `invalid`: not actionable for this repository, spam, or clearly outside project scope.
- `duplicate`: substantially the same as an existing open or closed issue.
- `help wanted`: issue is actionable but needs maintainer attention or community help.

## Priority labels

Choose exactly one priority label when possible:

- `priority:high`: blocks release/deployment, causes data loss, breaks core user flows, security-sensitive, or affects many users.
- `priority:medium`: important bug or feature with clear impact but not blocking critical paths.
- `priority:low`: minor polish, small docs improvement, exploratory request, or low-impact enhancement.

If priority is impossible to infer, do not guess; ask a clarifying question instead.

## Duplicate detection

Search existing issues for matching error messages, feature names, affected components, and user intent.

When you find a likely duplicate:

- Add the `duplicate` label.
- Add a short comment linking the most likely duplicate issue number.
- Do not close the issue.

## Clarifying questions

If the issue lacks enough detail to act, add the `question` label and ask one concise comment with the missing information. Prefer concrete questions, for example:

- Steps to reproduce.
- Expected vs actual behavior.
- Screenshots, logs, or error messages.
- Environment details.
- Which route, API, workflow, or deployment mode is affected.

## Assignment

Assign only when the owner is obvious from repository context or issue content. The current allowed assignee is:

- `yunhai-dev`: default maintainer for this repository.

If the right owner is unclear, do not assign.

## Safe-output requirements

- Use `add_labels` to apply labels.
- Use `add_comment` to ask clarifying questions or note likely duplicates.
- Use `assign_to_user` to assign the issue when appropriate.
- If no GitHub action is needed, call `noop` with a short explanation.
- Never use direct GitHub mutation APIs or `gh issue edit`.
