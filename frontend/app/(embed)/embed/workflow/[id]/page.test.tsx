import { afterEach, expect, mock, test } from "bun:test";
import React from "react";
import { act, create, type ReactTestRenderer } from "react-test-renderer";

const search = new Map<string, string>();
const postMessage = mock(() => {});
Object.assign(globalThis, {
  window: { parent: { postMessage }, addEventListener: () => {}, removeEventListener: () => {} },
});

mock.module("next/navigation", () => ({
  useParams: () => ({ id: "workflow-1" }),
  useSearchParams: () => ({ get: (key: string) => search.get(key) ?? null }),
}));
mock.module("next-intl", () => ({ useTranslations: () => (key: string) => key }));
mock.module("@/lib/api/embed", () => ({
  embedApi: {
    getWorkflowInfo: mock(() =>
      Promise.resolve({ id: "workflow-1", name: "Wf", description: null, icon: null, variables: [], embed_config: {} }),
    ),
  },
}));

let lastProps: Record<string, unknown> | undefined;
mock.module("@/app/(chat)/run/[id]/_components/workflow-run-page", () => ({
  WorkflowRunPage: (props: Record<string, unknown>) => {
    lastProps = props;
    return React.createElement("div", { "data-workflow-run-page": "true" });
  },
}));

const { default: EmbedWorkflowPage } = await import("./page");

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
let renderer: ReactTestRenderer | undefined;

afterEach(() => {
  renderer?.unmount();
  renderer = undefined;
  search.clear();
  lastProps = undefined;
});

async function render() {
  await act(async () => {
    renderer = create(React.createElement(EmbedWorkflowPage));
  });
  return renderer!;
}

test("shows the invalid token state without a token", async () => {
  const view = await render();
  const paragraphs = view.root.findAllByType("p");
  expect(paragraphs.some((node) => node.children.includes("invalidToken"))).toBe(true);
});

test("renders the run page in embed mode with a token", async () => {
  search.set("token", "tok-1");
  const view = await render();
  expect(view.root.findByProps({ "data-workflow-run-page": "true" })).toBeDefined();
  expect(lastProps?.embedMode).toBe(true);
  expect(lastProps?.id).toBe("workflow-1");
  expect(lastProps?.adapter).toBeDefined();
});
