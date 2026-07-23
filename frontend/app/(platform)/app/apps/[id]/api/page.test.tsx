import { afterEach, expect, mock, test } from "bun:test";
import React from "react";
import { act, create, type ReactTestRenderer } from "react-test-renderer";

const push = mock(() => {});
const router = { push };
const getAgent = mock(() => Promise.resolve({ id: "agent-1", name: "Support" }));

mock.module("next/navigation", () => ({ useRouter: () => router }));
mock.module("@/lib/api", () => ({ agentsApi: { getAgent } }));
mock.module("@/components/ui/skeleton", () => ({
  Skeleton: (props: React.ComponentProps<"div">) => <div {...props} />,
}));
mock.module("../_components/agent-sidebar", () => ({
  AgentSidebar: ({ agent }: { agent: { id: string } }) => <div data-sidebar={agent.id} />,
}));
mock.module("./_components/api-access-content", () => ({
  ApiAccessContent: ({ agent }: { agent: { id: string } }) => <div data-api={agent.id} />,
}));

const { default: ApiAccessPage } = await import("./page");

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
let renderer: ReactTestRenderer | undefined;

afterEach(() => {
  if (renderer) act(() => renderer!.unmount());
  renderer = undefined;
  getAgent.mockReset();
  getAgent.mockImplementation(() => Promise.resolve({ id: "agent-1", name: "Support" }));
  push.mockClear();
});

async function render() {
  await act(async () => {
    renderer = create(<ApiAccessPage params={Promise.resolve({ id: "agent-1" })} />);
    await Promise.resolve();
    await Promise.resolve();
  });
  return renderer!;
}

test("loads the routed agent for its sidebar and API access content", async () => {
  const view = await render();

  expect(getAgent).toHaveBeenCalledWith("agent-1");
  expect(view.root.findByProps({ "data-sidebar": "agent-1" })).toBeTruthy();
  expect(view.root.findByProps({ "data-api": "agent-1" })).toBeTruthy();
  expect(push).not.toHaveBeenCalled();
});

test("returns to the app list when the routed agent cannot load", async () => {
  getAgent.mockImplementation(() => Promise.reject(new Error("missing")));

  const view = await render();

  expect(push).toHaveBeenCalledWith("/app/apps");
  expect(view.root.findAllByProps({ "data-api": "agent-1" })).toHaveLength(0);
});
