import { afterEach, expect, mock, test } from "bun:test";
import React from "react";
import { act, create, type ReactTestRenderer } from "@/test-utils/rtl-renderer";

const search = new Map<string, string>();
const postMessage = mock(() => {});
const addEventListener = mock(() => {});
const removeEventListener = mock(() => {});

Object.assign(globalThis, {
  window: { parent: { postMessage }, addEventListener, removeEventListener },
});

mock.module("next/navigation", () => ({
  useParams: () => ({ id: "agent-1" }),
  useSearchParams: () => ({ get: (key: string) => search.get(key) ?? null }),
}));

let lastPageProps: Record<string, unknown> | undefined;
mock.module("@/app/(chat)/chat/[id]/page", () => ({
  default: (props: Record<string, unknown>) => {
    lastPageProps = props;
    return React.createElement("div", { "data-public-chat-page": "true" });
  },
}));

const stubAdapter = { _stub: true };
mock.module("@/lib/chat/embed-chat-adapter", () => ({
  createEmbedChatAdapter: mock(() => stubAdapter),
}));

const { default: EmbedAgentPage } = await import("./page");

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
let renderer: ReactTestRenderer | undefined;

afterEach(() => {
  if (renderer) {
    act(() => {
      renderer?.unmount();
    });
    renderer = undefined;
  }
  search.clear();
  postMessage.mockClear();
  addEventListener.mockClear();
  lastPageProps = undefined;
});

async function render() {
  await act(async () => {
    renderer = create(React.createElement(EmbedAgentPage));
  });
  return renderer!;
}

test("renders PublicChatPage in embed mode with a token", async () => {
  search.set("token", "tok-1");
  const view = await render();
  expect(view.root.findByProps({ "data-public-chat-page": "true" })).toBeDefined();
  expect(lastPageProps?.embedMode).toBe(true);
  expect(lastPageProps?.agentId).toBe("agent-1");
  expect(lastPageProps?.adapter).toBe(stubAdapter);
});

test("passes bubble mode through", async () => {
  search.set("token", "tok-1");
  search.set("mode", "bubble");
  await render();
  expect(lastPageProps?.mode).toBe("bubble");
});

test("notifies parent window on mount", async () => {
  search.set("token", "tok-1");
  await render();
  expect(postMessage).toHaveBeenCalledWith({ type: "clouisle:ready" }, "*");
});

test("shows spinner without a token", async () => {
  const view = await render();
  expect(lastPageProps).toBeUndefined();
  expect(view.root.findAllByType("div").length).toBeGreaterThan(0);
});

test("wires onConversationChange to parent postMessage", async () => {
  search.set("token", "tok-1");
  await render();
  (lastPageProps!.onConversationChange as (id: string) => void)("conv-42");
  expect(postMessage).toHaveBeenCalledWith({ type: "clouisle:conversation", conversationId: "conv-42" }, "*");
});

test("wires onClose to parent postMessage", async () => {
  search.set("token", "tok-1");
  await render();
  (lastPageProps!.onClose as () => void)();
  expect(postMessage).toHaveBeenCalledWith({ type: "clouisle:close" }, "*");
});
