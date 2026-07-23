import { afterEach, expect, mock, test } from "bun:test";
import React from "react";
import { act, create, type ReactTestRenderer } from "react-test-renderer";

const push = mock(() => {});
const router = { push };
const workflow = { id: "workflow-1", name: "Incident triage", icon: "🔀" };
const stats = {
  total_runs: 10,
  success_count: 7,
  failed_count: 2,
  timeout_count: 1,
  avg_duration_ms: 1500,
  last_run_at: null,
};
const getWorkflow = mock(() => Promise.resolve(workflow));
const getWorkflowStats = mock(() => Promise.resolve(stats));
const getWorkflowTrends = mock(() => Promise.resolve({ data: [{ date: "Jul 20", runs: 10, success: 7, failed: 2 }] }));
const getWorkflowRuns = mock(() => Promise.resolve({
  items: [{ id: "run-1", status: "success", created_at: "2026-07-20T10:00:00Z", total_duration_ms: 1500 }],
}));

mock.module("next/navigation", () => ({
  useParams: () => ({ id: "workflow-1" }),
  useRouter: () => router,
}));
mock.module("next-intl", () => ({
  useTranslations: (namespace: string) => (key: string) => `${namespace}:${key}`,
}));
mock.module("next/image", () => ({
  default: (props: React.ComponentProps<"img">) => <img {...props} alt={props.alt ?? ""} />,
}));
mock.module("@/lib/api/workflows", () => ({
  workflowsApi: { getWorkflow, getWorkflowStats, getWorkflowTrends, getWorkflowRuns },
}));
mock.module("@/components/ui/card", () => ({
  Card: ({ children, ...props }: React.ComponentProps<"section">) => <section {...props}>{children}</section>,
  CardContent: ({ children, ...props }: React.ComponentProps<"div">) => <div {...props}>{children}</div>,
  CardDescription: ({ children, ...props }: React.ComponentProps<"p">) => <p {...props}>{children}</p>,
  CardHeader: ({ children, ...props }: React.ComponentProps<"header">) => <header {...props}>{children}</header>,
  CardTitle: ({ children, ...props }: React.ComponentProps<"h2">) => <h2 {...props}>{children}</h2>,
}));
mock.module("@/components/ui/button", () => ({
  Button: ({ children, ...props }: React.ComponentProps<"button">) => <button {...props}>{children}</button>,
}));
mock.module("@/components/ui/badge", () => ({
  Badge: ({ children, ...props }: React.ComponentProps<"span">) => <span {...props}>{children}</span>,
}));
mock.module("@/components/ui/select", () => ({
  Select: ({ children, value, onValueChange }: { children: React.ReactNode; value: string; onValueChange: (value: string) => void }) => (
    <div data-select={value} onChange={onValueChange}>{children}</div>
  ),
  SelectContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectItem: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectValue: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));
mock.module("@/components/ui/dropdown-menu", () => ({
  DropdownMenu: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuItem: ({ children, ...props }: React.ComponentProps<"button">) => <button {...props}>{children}</button>,
  DropdownMenuTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));
const Chart = ({ children, ...props }: React.ComponentProps<"div">) => <div {...props}>{children}</div>;
mock.module("recharts", () => ({
  AreaChart: Chart,
  Area: Chart,
  BarChart: Chart,
  Bar: Chart,
  LineChart: Chart,
  Line: Chart,
  XAxis: Chart,
  YAxis: Chart,
  CartesianGrid: Chart,
  Tooltip: Chart,
  ResponsiveContainer: Chart,
  Legend: Chart,
}));

const { default: WorkflowMonitorPage } = await import("./page");

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
let renderer: ReactTestRenderer | undefined;

function resetApiMocks() {
  getWorkflow.mockReset();
  getWorkflow.mockImplementation(() => Promise.resolve(workflow));
  getWorkflowStats.mockReset();
  getWorkflowStats.mockImplementation(() => Promise.resolve(stats));
  getWorkflowTrends.mockReset();
  getWorkflowTrends.mockImplementation(() => Promise.resolve({ data: [{ date: "Jul 20", runs: 10, success: 7, failed: 2 }] }));
  getWorkflowRuns.mockReset();
  getWorkflowRuns.mockImplementation(() => Promise.resolve({
    items: [{ id: "run-1", status: "success", created_at: "2026-07-20T10:00:00Z", total_duration_ms: 1500 }],
  }));
}

afterEach(() => {
  if (renderer) act(() => renderer!.unmount());
  renderer = undefined;
  push.mockClear();
  resetApiMocks();
});

async function render() {
  await act(async () => {
    renderer = create(<WorkflowMonitorPage />);
    await Promise.resolve();
  });
  return renderer!;
}

function renderedText(view: ReactTestRenderer) {
  return view.root.findAll(() => true).flatMap((node) => node.children).filter((child) => typeof child === "string").join(" ");
}

test("loads workflow metrics, trends, and recent activity", async () => {
  const view = await render();
  const output = renderedText(view);

  expect(getWorkflow).toHaveBeenCalledWith("workflow-1");
  expect(getWorkflowStats).toHaveBeenCalledWith("workflow-1");
  expect(getWorkflowTrends).toHaveBeenCalledWith("workflow-1", "7d");
  expect(getWorkflowRuns).toHaveBeenCalledWith("workflow-1", { page: 1, pageSize: 5 });
  expect(output).toContain("Incident triage");
  expect(output).toContain("70.0%");
  expect(output).toContain("1.5s");
  expect(output).toContain("workflow.monitor_page:stats.success");
});

test("reloads the selected period and exposes workflow navigation", async () => {
  const view = await render();

  await act(async () => {
    view.root.findByProps({ "data-select": "7d" }).props.onChange("30d");
    await Promise.resolve();
  });

  expect(getWorkflowTrends).toHaveBeenLastCalledWith("workflow-1", "30d");

  act(() => view.root.findAllByType("button")[0]!.props.onClick());
  expect(push).toHaveBeenCalledWith("/app/apps");
});

test("keeps the loading recovery state when monitor data fails", async () => {
  getWorkflowStats.mockImplementation(() => Promise.reject(new Error("unavailable")));
  const consoleError = mock(() => {});
  const originalConsoleError = console.error;
  console.error = consoleError;

  try {
    const view = await render();

    expect(consoleError).toHaveBeenCalled();
    expect(renderedText(view)).not.toContain("Incident triage");
  } finally {
    console.error = originalConsoleError;
  }
});
