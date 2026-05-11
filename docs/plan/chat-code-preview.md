# Chat Code Preview Design Document

## Background & Goals

- Chat responses often include HTML, SVG, CSS, JavaScript, or Markdown code blocks that are easier to understand when rendered visually.
- Preview should not interrupt the conversation with a modal; it should open as a resizable right-side canvas so the user can keep reading the chat.
- Success criteria:
  - Supported code blocks expose a preview action after a complete non-streaming fence is available.
  - Previewable HTML/JavaScript executes only inside a sandboxed iframe.
  - Unsupported languages keep the existing source-only Streamdown rendering.
  - Mermaid rendering and streaming scroll behavior do not regress.

## High-Level Design

- `frontend/components/chat/message.tsx` remains the Streamdown block routing point.
- `frontend/components/chat/chat-container.tsx` passes an optional code-preview callback into messages.
- `frontend/app/(chat)/chat/[id]/page.tsx` owns selected preview state and lays out chat plus the right canvas.
- `frontend/components/chat/code-preview-canvas.tsx` renders preview/source tabs and builds sandboxed iframe documents for browser-previewable code.
- Preview iframe uses `sandbox="allow-scripts"` without `allow-same-origin` so scripts can run without access to the parent origin.

## Implementation Plan

### Stage 1: Preview data flow and code fence detection

- **Files modified**: `frontend/components/chat/types.ts`, `frontend/components/chat/chat-container.tsx`, `frontend/components/chat/message.tsx`
- **Specific logic**:
  - Add `CodePreviewKind` and `CodePreviewPayload` types.
  - Add optional `onOpenCodePreview` props from `ChatContainer` to `Message` and text markdown blocks.
  - Detect complete fenced code blocks in `message.tsx` after Mermaid handling.
  - Support `html`, `htm`, `xhtml`, `svg`, `xml` containing SVG, `css`, `js`, `javascript`, `mjs`, `md`, and `markdown`.
  - Do not show preview controls during streaming or for incomplete fences.
- **Validation**:
  - Preview callback is optional and existing callers without it keep current rendering.
  - Mermaid blocks still route to `MermaidBlock`.
  - Unsupported languages such as Python, JSON, TSX, and SQL show no preview action.

### Stage 2: Sandboxed preview canvas and chat page layout

- **Files modified**: `frontend/app/(chat)/chat/[id]/page.tsx`, `frontend/components/chat/code-preview-canvas.tsx`
- **Specific logic**:
  - Add selected preview state to the main chat page.
  - When a preview is active, wrap the chat area and canvas with `ResizablePanelGroup direction="horizontal"`.
  - Use `ResizablePanel` and `ResizableHandle` for a draggable right-side canvas.
  - Render `Preview` and `Source` tabs in `CodePreviewCanvas`.
  - Use iframe `srcDoc` for HTML, SVG, CSS, and JavaScript previews.
  - Render Markdown preview with `Streamdown` inside the canvas.
  - Escape `</script>` in JavaScript before placing it inside wrapper script tags.
- **Validation**:
  - HTML inline scripts run inside the iframe and do not affect the parent page.
  - Canvas can be resized and closed.
  - Closing the canvas restores the original single-column chat layout.

### Stage 3: i18n and end-to-end validation

- **Files modified**: `frontend/i18n/en/chat.json`, `frontend/i18n/zh/chat.json`, generated `frontend/i18n/types/chat.ts`, `docs/IMPLEMENTATION_PLAN.md`
- **Specific logic**:
  - Add synchronized English and Chinese keys for preview/source labels, open/close actions, title, and sandbox notice.
  - Regenerate i18n types.
  - Mark this plan entry complete after validation.
- **Validation**:
  - Run `bun run --cwd frontend i18n:gen-types`.
  - Run `bun run --cwd frontend i18n:lint --strict`.
  - Run `bun run --cwd frontend lint`.
  - Run `bun run --cwd frontend build`.
  - Manually verify HTML, CSS, JS, SVG, Markdown, unsupported language, and streaming long-code cases in the browser.

## Testing Strategy

- Happy path tests:
  - HTML block opens the right canvas and executes a button click script inside iframe.
  - CSS block styles the generated sample page.
  - JavaScript block appends DOM content and writes console output in iframe.
  - SVG block renders centered in iframe.
  - Markdown block renders formatted preview in the canvas.
- Negative tests:
  - Python, JSON, SQL, TSX, and incomplete streaming fences do not show preview buttons.
  - iframe script cannot access `window.parent.document` because same-origin is not granted.
- Regression scope:
  - Mermaid diagram/code/fullscreen behavior.
  - Chat auto-scroll while streaming long code blocks.
  - Existing agent preview/chat containers where no preview callback is passed.

## Risks & Mitigation

- User code execution risk: restrict execution to iframe with `sandbox="allow-scripts"` and no same-origin privileges.
- Over-broad preview support risk: first version only supports browser-native preview wrappers and leaves compile/runtime languages source-only.
- Layout regression risk: keep preview state local to the main chat page and keep existing single-column layout when no preview is selected.
- Scroll regression risk: do not mount preview iframes during streaming; only show preview after a complete fence is available.
- Rollback plan: remove the `onOpenCodePreview` callback wiring and right canvas integration; Streamdown default code rendering remains intact.
