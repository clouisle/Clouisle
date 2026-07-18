# Workflow Media Preview and URL Output Design Document

## Background & Goals

The workflow media-generation node currently exposes the complete media tool payload to downstream nodes and only previews generated media in execution details. The canvas node should show its running/result state, while downstream nodes should receive only durable media URLs.

Success criteria:

- image output is an ordered `string[]` of backend file URLs;
- video output is one backend file URL string;
- media appears inside the canvas node after the non-streaming `node_complete` event;
- execution traces remain ephemeral and are not saved into workflow definitions.

## High-Level Design

Reuse the shared media generation and asset-normalization pipeline. The workflow executor extracts normalized URLs and emits them once on completion. The editor projects its existing `nodeTraces` state into derived ReactFlow nodes, allowing `MediaGenerationNode` to render runtime state without altering persisted node configuration.

## Implementation Plan

### Stage 1: URL-only executor outputs

- **Files modified**: `backend/app/services/workflow/executors/media_generation.py`
- Return ordered URL arrays for image mode and a URL string for video mode.
- Mirror the same value to a configured output alias.
- Declare matching output types and fail when a successful generation has no normalized URL.
- **Validation**: executor and output-schema unit tests.

### Stage 2: Canvas trace projection

- **Files modified**: `frontend/app/(platform)/app/apps/workflow/[id]/page.tsx`
- Attach current execution traces only to nodes derived for ReactFlow rendering.
- Keep canonical workflow nodes unchanged for save/configuration behavior.
- **Validation**: save/reload after a run and confirm traces are not persisted.

### Stage 3: In-node media preview

- **Files modified**: media generation node and shared node-output renderer.
- Show running/failure state, bounded image thumbnails, and playable video.
- Keep legacy full media payload support in historical execution details.
- **Validation**: image, multi-image, video, failure, and no-trace states.

## Testing Strategy

- Happy path: ordered image URLs, video URL, output alias, canvas previews.
- Error path: provider failure and successful response without a normalized URL.
- Regression scope: historical run rendering, workflow saving, downstream variable typing, execution drawer.

## Risks & Mitigation

- URL contract breaks object consumers: update type declarations and tests atomically.
- Runtime data leaks into definitions: derive render nodes rather than mutating canonical nodes.
- Large canvas previews: use bounded aspect-ratio frames with `object-contain`, a stable preview width, and a compact multi-image grid.
- Detailed viewing: canvas thumbnails and execution-detail media open the shared fullscreen image/video viewers without persisting viewer state.
- Rollback: restore executor payload output and remove trace projection; no stored schema changes are required.
