import { afterEach, expect, mock, test } from "bun:test";
import React from "react";
import { act, create, type ReactTestRenderer } from "react-test-renderer";

const search = new Map<string, string>();
const getWorkflowInfo = mock(() => Promise.resolve({
  id: "workflow-1",
  name: "Triage",
  icon: "🔀",
  description: "Describe the incident",
  variables: [{ name: "query", type: "text" }, { name: "region", type: "text" }],
  embed_config: { bubble: { greeting: "Welcome" } },
}));
const runWorkflow = mock(() => Promise.resolve({ run_id: "run-1" }));
const closeStream = mock(() => {});
let streamHandlers: Record<string, (...args: unknown[]) => void> | undefined;
const streamWorkflowRun = mock((_id: string, _key: string, handlers: typeof streamHandlers) => {
  streamHandlers = handlers;
  return closeStream;
});
const postMessage = mock(() => {});
const resetVariables = mock(() => {});

Object.assign(globalThis, {
  window: {
    parent: { postMessage },
    addEventListener: () => {},
    removeEventListener: () => {},
  },
});

mock.module("next/navigation", () => ({
  useParams: () => ({ id: "workflow-1" }),
  useSearchParams: () => ({ get: (key: string) => search.get(key) ?? null }),
}));
const translate = (key: string) => key;
mock.module("next-intl", () => ({ useTranslations: () => translate }));
mock.module("next/image", () => ({
  default: (props: React.ComponentProps<"img">) => <img {...props} />,
}));
mock.module("@/lib/api/embed", () => ({
  embedApi: { getWorkflowInfo, runWorkflow, streamWorkflowRun },
  resolveEmbedMessage: (message: unknown, fallback: string) => typeof message === "string" ? message : fallback,
}));
mock.module("@/components/chat", () => ({
  ChatContainer: ({ emptyState, ...props }: { emptyState?: React.ReactNode } & Record<string, unknown>) => <div data-chat-container="true" {...props}>{emptyState}</div>,
  ChatInput: (props: Record<string, unknown>) => <div data-chat-input="true" {...props} />,
  VariableForm: (props: Record<string, unknown>) => <div data-variable-form="true" {...props} />,
  useVariableForm: () => ({
    values: { region: "EU" },
    needsInput: false,
    isValid: true,
    fieldErrors: {},
    validate: () => true,
    reset: resetVariables,
    setValues: mock(() => {}),
  }),
}));
mock.module("@/components/ui/button", () => ({
  Button: ({ children, ...props }: React.ComponentProps<"button">) => <button {...props}>{children}</button>,
}));
mock.module("@/components/ui/collapsible", () => ({
  Collapsible: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  CollapsibleContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  CollapsibleTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

const { default: EmbedWorkflowPage } = await import("./page");

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
let renderer: ReactTestRenderer | undefined;

afterEach(() => {
  if (renderer) act(() => renderer!.unmount());
  renderer = undefined;
  search.clear();
  getWorkflowInfo.mockClear();
  runWorkflow.mockClear();
  streamWorkflowRun.mockClear();
  closeStream.mockClear();
  postMessage.mockClear();
  resetVariables.mockClear();
  streamHandlers = undefined;
});

async function render() {
  await act(async () => {
    renderer = create(<EmbedWorkflowPage />);
    await Promise.resolve();
    await Promise.resolve();
  });
  return renderer!;
}

function renderedText(view: ReactTestRenderer) {
  return view.root.findAll(() => true).flatMap((node) => node.children).filter((child) => typeof child === "string").join(" ");
}

test("rejects a missing token and notifies the parent", async () => {
  const view = await render();

  expect(renderedText(view)).toContain("invalidToken");
  expect(getWorkflowInfo).not.toHaveBeenCalled();
  expect(postMessage).toHaveBeenCalledWith({ type: "clouisle:ready" }, "*");
});

test("runs the workflow and routes answer tokens into chat", async () => {
  search.set("token", "embed-token");
  const view = await render();
  const input = view.root.findByProps({ "data-chat-input": "true" });

  await act(async () => {
    await input.props.onSubmit("  diagnose  ");
  });
  expect(runWorkflow).toHaveBeenCalledWith("workflow-1", { query: "diagnose", region: "EU" }, "embed-token");
  expect(streamWorkflowRun).toHaveBeenCalledWith("run-1", "embed-token", expect.any(Object));

  act(() => {
    streamHandlers!.onEvent({ type: "node_start", data: { node_id: "answer-1", node_type: "answer" } });
    streamHandlers!.onEvent({ type: "token", data: { node_id: "answer-1", token: "Resolved" } });
    streamHandlers!.onEvent({ type: "workflow_complete", data: {} });
  });
  expect(view.root.findByProps({ "data-chat-container": "true" }).props.messages).toHaveLength(3);
});

test("stops, resets, and closes bubble workflows", async () => {
  search.set("token", "embed-token");
  search.set("mode", "bubble");
  const view = await render();
  const input = view.root.findByProps({ "data-chat-input": "true" });

  await act(async () => { await input.props.onSubmit("run"); });
  act(() => input.props.onStop());
  act(() => view.root.findByProps({ title: "newChat" }).props.onClick());
  act(() => view.root.findByProps({ title: "close" }).props.onClick());

  expect(closeStream).toHaveBeenCalledTimes(1);
  expect(resetVariables).toHaveBeenCalledTimes(1);
  expect(postMessage).toHaveBeenCalledWith({ type: "clouisle:close" }, "*");
});
