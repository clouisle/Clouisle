# Skills & Capabilities User Guide

Skills follow the open [Agent Skills specification](https://agentskills.io/specification): a Skill is a directory holding a `SKILL.md` plus optional `scripts/`, `references/`, and `assets/` files. Clouisle imports Skill packages and lets Agents read, run, and adapt those files inside the sandbox.

---

## 1. Overview

In Clouisle, Capabilities include:
- **Built-in Tools**: Web search, calculation, file parsers, and system utilities.
- **Skills**: Imported `SKILL.md` packages whose instructions and bundled files the Agent uses on demand.
- **MCP Servers**: Live Model Context Protocol connections exposing dynamic external tool catalogues.
- **Database Tools**: Read-only structured querying tools for PostgreSQL, MySQL, and SQLite.

---

## 2. Writing a Skill

`SKILL.md` carries YAML frontmatter plus Markdown instructions:

```markdown
---
name: pdf-tools
description: Extract text and tables from PDF files. Use when the user mentions PDFs, forms, or document extraction.
license: Apache-2.0
compatibility: Requires Python 3.11
allowed-tools: Bash Read
---

Run `scripts/extract.py <file>` and summarise the result.
```

- `name` and `description` are required. `name` uses lowercase letters, digits, and single hyphens, is at most 64 characters, and should match the package directory name; `description` is at most 1024 characters.
- `license`, `compatibility`, `metadata`, and `allowed-tools` are optional. `allowed-tools` is a space-separated list of the tools the Skill expects to use; Clouisle passes it to the model as guidance.
- There is no execution declaration. Scripts are run by the Agent with its sandbox tools (`bash`, `read`, `write`, `artifact`), exactly as the specification intends.
- Older packages may still carry an `x-clouisle.execution` block. It is ignored and reported as an import warning.

---

## 3. Managing Skills

Navigate to **Capabilities > Skills** from the workspace navigation:

1. **Import Skill** — Skills are created only by importing a package; there is no manual editor:
   - **Import from ZIP**: upload a `.zip` bundle; every directory containing `SKILL.md` is previewed separately.
   - **Import from Git**: point at a public HTTPS repository and branch, tag, or commit; the whole checkout is scanned for `SKILL.md`.
2. **Select and install**: pick the scanned Skills, resolve conflicts with update/skip, then install.
3. **Attach to Agent**: open the Agent editor under **Apps > Agents > Edit** and enable the Skill in the **Tools & Skills** selector. Enable at least the `bash` tool (plus `read`/`write`/`artifact`) so the Agent can run and produce files.

---

## 4. How Skills reach the sandbox

When a chat or Agent run starts, Clouisle creates a sandbox session and pushes each enabled Skill package into that session's workspace through the sandbox job API. The worker node receives the package bytes in the job payload; it never reads shared or distributed storage. Files land under `/workspace/skills/<name>/`:

- The first Skill call returns the `SKILL.md` body, the file inventory, and the Skill root path.
- The Agent then reads `references/`, runs `scripts/`, and writes results to `/workspace/output`, where the `artifact` tool generates download links.
- A workspace reset invalidates the copy, and the next Skill call pushes the package again.

---

# Memory System User Guide

Clouisle features a long-term episodic and semantic memory system that extracts, stores, and connects key facts across conversations.

---

## 1. How Memory Works

When Memory is enabled for an Agent:
1. **Automatic Extraction**: At conversation turn boundaries, the system extracts notable user preferences, facts, and relationships.
2. **Entity & Relation Graph**: Facts are structured as entities (e.g. `User Preference`, `Project`, `Contact`) connected by directional relations.
3. **Context Injection**: Relevant entity nodes and connected graph context are automatically retrieved and appended to the agent's prompt during subsequent conversations.

---

## 2. Managing Memories

Navigate to **Memories** from the navigation bar:
- **Entity Browser**: Search and inspect extracted knowledge entities and their creation timestamps.
- **Graph View**: Visually inspect connections and relations between concepts.
- **Edit & Delete**: Correct inaccurate facts or permanently delete sensitive memory records.
