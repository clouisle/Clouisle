import { afterEach, expect, mock, test } from "bun:test";
import React from "react";
import { act, create, type ReactTestRenderer } from "react-test-renderer";

const search = new Map<string, string>();
const getAgentInfo = mock(() => Promise.resolve({
  id: "agent-1",
  name: "Support",
  icon: "🤖",
  description: "Ask a question",
  opening_message: "Welcome",
  suggested_questions: ["How do I start?"],
  variables: [],
  enable_vision: false,
  enable_file_upload: false,
  embed_config: {},
}));
const sendMessage = mock(() => Promise.resolve());
const reset = mock(() => {});
const stop = mock(() => {});
const postMessage = mock(() => {});
Object.assign(globalThis, {
  window: {
    parent: { postMessage },
    addEventListener: () => {},
    removeEventListener: () => {},
  },
});

mock.module("next/navigation", () => ({
  useParams: () => ({ id: "agent-1" }),
  useSearchParams: () => ({ get: (key: string) => search.get(key) ?? null }),
}));
const translate = (key: string) => key;
mock.module("next-intl", () => ({
  useTranslations: () => translate,
}));
mock.module("next/image", () => ({
  default: (props: React.ComponentProps<"img">) => <img {...props} alt={props.alt ?? ""} />,
}));
mock.module("@/lib/api/embed", () => ({
  embedApi: { getAgentInfo, uploadFile: mock(() => Promise.resolve({ url: "file-url" })) },
  resolveEmbedMessage: (message: string) => message,
}));
mock.module("@/hooks/use-embed-chat", () => ({
  useEmbedChat: () => ({
    messages: [{ id: "message-1", role: "assistant", parts: [] }],
    isStreaming: false,
    isLoading: false,
    sendMessage,
    reset,
    stop,
  }),
}));
mock.module("@/components/chat", () => ({
  ChatContainer: ({ emptyState, ...props }: { emptyState?: React.ReactNode } & Record<string, unknown>) => <div data-chat-container="true" {...props}>{emptyState}</div>,
  ChatInput: (props: Record<string, unknown>) => <div data-chat-input="true" {...props} />,
  VariableForm: () => <div />,
  useVariableForm: () => ({
    values: {},
    needsInput: false,
    isValid: true,
    fieldErrors: {},
    validate: () => true,
    reset: mock(() => {}),
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

const { default: EmbedAgentPage } = await import("./page");

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
let renderer: ReactTestRenderer | undefined;

afterEach(() => {
  if (renderer) act(() => renderer!.unmount());
  renderer = undefined;
  search.clear();
  getAgentInfo.mockClear();
  sendMessage.mockClear();
  reset.mockClear();
  postMessage.mockClear();
});

async function render() {
  await act(async () => {
    renderer = create(<EmbedAgentPage />);
    await Promise.resolve();
    await Promise.resolve();
  });
  return renderer!;
}

function renderedText(view: ReactTestRenderer) {
  return view.root.findAll(() => true).flatMap((node) => node.children).filter((child) => typeof child === "string").join(" ");
}

test("rejects a missing token and notifies the parent that it is ready", async () => {
  const view = await render();

  expect(renderedText(view)).toContain("invalidToken");
  expect(getAgentInfo).not.toHaveBeenCalled();
  expect(postMessage).toHaveBeenCalledWith({ type: "clouisle:ready" }, "*");
});

test("loads the embedded agent and sends suggested questions", async () => {
  search.set("token", "embed-token");
  const view = await render();

  expect(getAgentInfo).toHaveBeenCalledWith("agent-1", "embed-token");
  expect(renderedText(view)).toContain("Support");
  await act(async () => {
    view.root.findByProps({ children: "How do I start?" }).props.onClick();
    await Promise.resolve();
  });
  expect(sendMessage).toHaveBeenCalledWith("How do I start?", undefined, undefined);
});

test("resets conversations and closes bubble embeds", async () => {
  search.set("token", "embed-token");
  search.set("mode", "bubble");
  const view = await render();

  act(() => view.root.findByProps({ title: "newChat" }).props.onClick());
  act(() => view.root.findByProps({ title: "close" }).props.onClick());

  expect(reset).toHaveBeenCalledTimes(1);
  expect(postMessage).toHaveBeenCalledWith({ type: "clouisle:close" }, "*");
});
