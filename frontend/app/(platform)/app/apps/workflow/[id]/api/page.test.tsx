import { afterEach, expect, mock, test } from "bun:test";
import React from "react";
import { act, create, type ReactTestRenderer } from "react-test-renderer";

const push = mock(() => {});
const router = { push };
const getWorkflow = mock(() => Promise.resolve({
  id: "workflow-1",
  name: "Incident triage",
  icon: "🔀",
}));

mock.module("next/navigation", () => ({
  useParams: () => ({ id: "workflow-1" }),
  useRouter: () => router,
}));
mock.module("next-intl", () => ({
  useTranslations: () => (key: string) => key,
}));
mock.module("next/image", () => ({
  default: (props: React.ComponentProps<"img">) => <img {...props} />,
}));
mock.module("@/lib/api/workflows", () => ({ workflowsApi: { getWorkflow } }));
mock.module("@/components/ui/button", () => ({
  Button: ({ children, ...props }: React.ComponentProps<"button">) => <button {...props}>{children}</button>,
}));
mock.module("@/components/ui/dropdown-menu", () => ({
  DropdownMenu: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuItem: ({ children, ...props }: React.ComponentProps<"button">) => <button {...props}>{children}</button>,
  DropdownMenuTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));
mock.module("./_components/workflow-api-content", () => ({
  WorkflowApiContent: ({ workflow }: { workflow: { id: string } }) => <div data-workflow={workflow.id} />,
}));

const { default: WorkflowApiPage } = await import("./page");

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
let renderer: ReactTestRenderer | undefined;

afterEach(() => {
  if (renderer) act(() => renderer!.unmount());
  renderer = undefined;
  push.mockClear();
  getWorkflow.mockReset();
  getWorkflow.mockImplementation(() => Promise.resolve({ id: "workflow-1", name: "Incident triage", icon: "🔀" }));
});

async function render() {
  await act(async () => {
    renderer = create(<WorkflowApiPage />);
    await Promise.resolve();
  });
  return renderer!;
}

test("loads the routed workflow and exposes API navigation", async () => {
  const view = await render();

  expect(getWorkflow).toHaveBeenCalledWith("workflow-1");
  expect(view.root.findByProps({ "data-workflow": "workflow-1" })).toBeTruthy();
  expect(JSON.stringify(view.toJSON())).toContain("Incident triage");

  act(() => view.root.findAllByType("button")[0]!.props.onClick());
  expect(push).toHaveBeenCalledWith("/app/apps");
});

test("shows the recovery route when the workflow cannot load", async () => {
  getWorkflow.mockImplementation(() => Promise.reject(new Error("missing")));

  const view = await render();
  const back = view.root.findByType("button");

  expect(JSON.stringify(view.toJSON())).toContain("workflowNotFound");
  act(() => back.props.onClick());
  expect(push).toHaveBeenCalledWith("/app/apps/workflow");
});
