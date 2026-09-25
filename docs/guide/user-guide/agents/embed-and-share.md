# Agent Embed & Independent Run View

This guide explains how to share published AI agents via the dedicated Run page and embed them into external websites as interactive chat widgets.

---

## Overview

Once an agent is configured and published, Clouisle provides three distinct delivery channels:

1. **Independent Run Page (`/run/{agent_id}`)**: A distraction-free, full-screen conversational interface for an agent, reached by direct URL.
2. **Embeddable Chat Widget (`/embed/agent/{agent_id}`)**: A browser page that renders an agent chat — or a workflow run at `/embed/workflow/{workflow_id}` — inside an external site. It is loaded with the `embed.js` SDK or a plain iframe and authenticates with your own API key (`clou_...`).
3. **Embed REST API (`/api/v1/embed/...`)**: The API-key-authenticated endpoints the widget calls under the hood (agent info/chat/runs/uploads and workflow info/run/stream). This is a different namespace from the browser embed pages above.

---

## 1. Independent Run Page (`/run/{agent_id}`)

The Run view provides a clean, standalone interface tailored for dedicated task execution without the clutter of the studio sidebar or settings drawers.

```
┌────────────────────────────────────────────────────────────────────────┐
│ 🤖 Financial Analyst Agent                           [Team: Finance]   │
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│  🤖 Financial Analyst                                                  │
│  Upload quarterly earnings reports or ask financial modeling questions │
│                                                                        │
│  [Analyze Q3 Revenue]  [Model Cashflow]  [Compare Competitors]         │
│                                                                        │
│  👤 User: Analyze the uploaded Q3 report.                              │
│                                                                        │
│  🤖 Financial Analyst:                                                 │
│  💭 Thought for 2.4s (Reading file: Q3_Financials.pdf)...              │
│  Here is the summary of Q3 financial performance...                    │
│                                                                        │
├────────────────────────────────────────────────────────────────────────┤
│  [📎] Ask a question or drop a spreadsheet...                   [Send] │
└────────────────────────────────────────────────────────────────────────┘
```

### Accessing the Run Page
- Navigate directly to `https://<your-clouisle-domain>/run/{agent_id}`.
- The **Apps** page (`/app/apps`) does not link agents here: an agent card's **⋯** menu opens **Chat** (`/chat/{agent_id}`). The **Run** menu item appears only on workflow cards, where it opens `/run/{workflow_id}?type=workflow`.

### Features
- **Distraction-free Canvas**: Optimized for deep interaction, document analysis, and iterative multi-turn conversations.
- **Dynamic Variable Prompting**: If the agent contains required variables (e.g., `client_id`, `locale`), the run page presents a clean input banner before starting.
- **Full Capabilities**: Complete support for attachments, image lightbox, document previews, `ask_user` interaction forms, and multi-version message branching.

---

## 2. Embeddable Chat Widget

Clouisle allows you to embed published agents or workflows into third-party web pages as a **Floating Chat Bubble**, a **Fullscreen iframe**, or a **Mobile iframe**. The browser page is served at `/embed/agent/{id}` or `/embed/workflow/{id}`; the REST API behind it lives under the separate `/api/v1/embed/...` namespace.

### Enabling Embedding

1. Open your agent in the **Agent Studio** (`/app/apps/{agent_id}`) — the same **Embed Settings** dialog is available for workflows in the workflow builder.
2. Ensure the agent/workflow is **Published**: for drafts the enable toggle and **Save** are disabled.
3. Click the **Embed** button on the top toolbar to open the **Embed Settings** dialog.
4. Toggle **Enable Embedding** on.
5. Paste one of your own API keys (`clou_...`) into the **API Key** field. It is only inserted into the generated snippet — it is never saved with the agent. Use **Manage API Keys** to create one.

### Configuration Options

| Option | Description | Example |
|---|---|---|
| **Enable Embedding** | Allow this agent/workflow to be loaded through the embed page | On / Off |
| **Allowed Domains** | Restrict widget loading to specific browser origins (checked against the request `Origin` / `Referer`). Leave empty to allow all domains; wildcard subdomains are supported | `https://example.com, *.example.com` |
| **Show Header** | Show the app icon and name at the top of the embed | On (default) |
| **Show History** | Show a history sidebar in the embed (stored in the browser) | On (default) |
| **Allow New** | Allow users to start a new chat/run | On (default) |
| **Theme** | Widget color scheme | `Auto` (default) / `Light` / `Dark` |
| **Primary Color** | Widget accent color (hex) | `#6366f1` |
| **Bubble Position** | Screen placement of the floating bubble | `Bottom Right` (default) / `Bottom Left` |
| **Greeting Message** | Message shown when the embed opens | `Hi! How can I help you?` |
| **Embed Mode** | Which snippet the dialog generates (the mode is not persisted) | `Bubble` / `Fullscreen` / `Mobile` |

---

## 3. Integration Code Examples

### Option A: JavaScript SDK (Floating Bubble)

Paste this snippet immediately before the closing `</body>` tag on your website:

```html
<script src="https://<your-clouisle-domain>/embed.js"></script>
<script>
  Clouisle.init({
    type: 'agent',                                  // 'agent' or 'workflow'
    id: '550e8400-e29b-41d4-a716-446655440000',
    token: 'clou_a1b2c3d4e5f6...',
    mode: 'bubble',                                 // 'bubble' | 'fullscreen' | 'mobile'
    theme: 'auto',                                  // 'auto' | 'light' | 'dark'
    primaryColor: '#6366f1',
    position: 'bottom-right',                       // 'bottom-right' | 'bottom-left'
    greeting: 'Hi! How can I help you?',
  });
</script>
```

`Clouisle.init()` requires `id` and `token`. For `mode: 'fullscreen'` or `mode: 'mobile'`, also pass `container` (a CSS selector for the element to mount into). The returned instance exposes `open()`, `close()`, and `destroy()`.

### Option B: Inline Iframe Embedding

To embed the agent conversation directly inside a container on your page:

```html
<iframe
  src="https://<your-clouisle-domain>/embed/agent/550e8400-e29b-41d4-a716-446655440000?token=clou_a1b2c3d4e5f6...&theme=light&mode=fullscreen"
  style="width: 100%; height: 100%; border: none;"
  allow="clipboard-write"
></iframe>
```

The embed page accepts `token` (required), `mode` (`fullscreen` by default, or `bubble` / `mobile`), and `theme` (`auto` by default, or `light` / `dark`). For a workflow, use `/embed/workflow/{workflow_id}`; for a mobile-style layout, use a fixed-position iframe exactly as the dialog's **Mobile** tab generates it.

---

## 4. Security & Access Control

- **API Key Authentication**: Embedded widgets authenticate with an API key (`clou_...`) passed in the `token` query parameter or an `Authorization: Bearer <key>` header. API keys belong to the user who created them — they are not team-scoped — and the embed acts as that user.
- **Key Restrictions**: The only per-key restriction is the optional binding to specific agents/workflows. A key bound to agents or workflows can only reach those; a key bound to none is allowed to reach all of them. The key's `scopes` list is stored but never enforced.
- **Domain Verification**: When **Allowed Domains** is configured, requests are rejected unless the `Origin` (or `Referer`) host matches an allowed entry; wildcard subdomains (`*.example.com`) are supported. Requests carrying no origin information are allowed.
- **Endpoint Surface**: Embedded clients are intended to call only the `/api/v1/embed/...` routes. Because the key authenticates as its owner, treat `clou_...` keys as owner credentials and restrict where they are published.
