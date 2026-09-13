# Skills & Capabilities User Guide

Skills allow users to extend Agent problem-solving capabilities with custom tool packages, Python code snippets, and reusable workflow abilities.

---

## 1. Overview

In Clouisle, Capabilities include:
- **Built-in Tools**: Web search, calculation, file parsers, and system utilities.
- **Custom Skills**: Custom-written Python scripts and package bundles that can be invoked dynamically by agents.
- **MCP Servers**: Live Model Context Protocol connections exposing dynamic external tool catalogues.
- **Database Tools**: Read-only structured querying tools for PostgreSQL, MySQL, and SQLite.

---

## 2. Managing Skills

Navigate to **Capabilities > Skills** from the workspace navigation:

1. **Create or Import Skill**:
   - **Manual Creation**: Write skill code directly in the code editor with parameter schemas.
   - **Import from ZIP**: Upload a structured skill ZIP bundle containing `manifest.json`, `index.py`, and dependencies.
   - **Import from Git**: Provide a public or authenticated Git repository URL containing standard Clouisle skill packages.
2. **Test and Verify**:
   - Use the **Test Skill** interactive runner to test execution within an isolated runtime sandbox before attaching to production agents.
3. **Attach to Agent**:
   - Open your target Agent editor under **Apps > Agents > Edit**.
   - Enable the skill in the **Tools & Skills** selector.

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
