import { afterEach, expect, mock, test } from "bun:test";
import React from "react";
import { act, create, type ReactTestRenderer } from "react-test-renderer";

const push = mock(() => {});
const router = { push };
const getAgent = mock(() => Promise.resolve({ id: "agent-1", name: "Support" }));
const getStats = mock(() => Promise.resolve({
  overview: { total_conversations: 1200, total_messages: 25, active_users: 4 },
  tokens: { total_tokens: 2000000, prompt_tokens: 1500, completion_tokens: 500 },
  performance: { avg_response_time_ms: 1500 },
  tools: { tool_call_count: 3 },
}));
const getTrends = mock(() => Promise.resolve({ data: [] }));
const getToolUsage = mock(() => Promise.resolve({ tools: [] }));
const getRecentConversations = mock(() => Promise.resolve([{
  id: "conversation-1",
  title: "Customer question",
  user: { username: "alex" },
  message_count: 3,
  updated_at: "2026-07-20T10:00:00Z",
}]));

mock.module("next/navigation", () => ({ useRouter: () => router }));
mock.module("next-intl", () => ({
  useTranslations: () => (key: string) => key,
  useLocale: () => "en",
}));
mock.module("@/lib/api", () => ({
  agentsApi: { getAgent },
  agentStatsApi: { getStats, getTrends, getToolUsage, getRecentConversations },
}));
mock.module("@/components/ui/skeleton", () => ({ Skeleton: (props: React.ComponentProps<"div">) => <div {...props} /> }));
mock.module("@/components/ui/card", () => ({
  Card: ({ children, ...props }: React.ComponentProps<"section">) => <section {...props}>{children}</section>,
  CardContent: ({ children, ...props }: React.ComponentProps<"div">) => <div {...props}>{children}</div>,
  CardDescription: ({ children, ...props }: React.ComponentProps<"p">) => <p {...props}>{children}</p>,
  CardHeader: ({ children, ...props }: React.ComponentProps<"header">) => <header {...props}>{children}</header>,
  CardTitle: ({ children, ...props }: React.ComponentProps<"h2">) => <h2 {...props}>{children}</h2>,
}));
mock.module("@/components/ui/select", () => ({
  Select: ({ children, value, onValueChange }: { children: React.ReactNode; value: string; onValueChange: (value: string) => void }) => <div data-select={value} onChange={onValueChange}>{children}</div>,
  SelectContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectItem: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectValue: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));
mock.module("../_components/agent-sidebar", () => ({ AgentSidebar: ({ agent }: { agent: { id: string } }) => <div data-sidebar={agent.id} /> }));
mock.module("@/components/ui/chart", () => ({
  ChartContainer: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  ChartTooltip: ({ children }: { children?: React.ReactNode }) => <div>{children}</div>,
  ChartTooltipContent: () => <div />,
}));
const Chart = ({ children, ...props }: React.ComponentProps<"div">) => <div {...props}>{children}</div>;
mock.module("recharts", () => ({ Area: Chart, AreaChart: Chart, Bar: Chart, BarChart: Chart, XAxis: Chart, YAxis: Chart, CartesianGrid: Chart, Cell: Chart }));

const { default: MonitorPage } = await import("./page");

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
let renderer: ReactTestRenderer | undefined;

afterEach(() => {
  if (renderer) act(() => renderer!.unmount());
  renderer = undefined;
  push.mockClear();
  getAgent.mockReset();
  getAgent.mockImplementation(() => Promise.resolve({ id: "agent-1", name: "Support" }));
});

async function render() {
  await act(async () => {
    renderer = create(<MonitorPage params={Promise.resolve({ id: "agent-1" })} />);
    await Promise.resolve();
    await Promise.resolve();
  });
  return renderer!;
}

function renderedText(view: ReactTestRenderer) {
  return view.root.findAll(() => true).flatMap((node) => node.children).filter((child) => typeof child === "string").join(" ");
}

test("loads agent metrics and recent conversations", async () => {
  const view = await render();
  const output = renderedText(view);

  expect(getAgent).toHaveBeenCalledWith("agent-1");
  expect(getStats).toHaveBeenCalledWith("agent-1", "7d");
  expect(getTrends).toHaveBeenCalledWith("agent-1", "7d");
  expect(getToolUsage).toHaveBeenCalledWith("agent-1", "7d");
  expect(getRecentConversations).toHaveBeenCalledWith("agent-1", 5);
  expect(view.root.findByProps({ "data-sidebar": "agent-1" })).toBeTruthy();
  expect(output).toContain("1.2K");
  expect(output).toContain("2.0M");
  expect(output).toContain("1.50s");
  expect(output).toContain("Customer question");
});

test("reloads metrics when the reporting period changes", async () => {
  const view = await render();

  await act(async () => {
    view.root.findByProps({ "data-select": "7d" }).props.onChange("30d");
    await Promise.resolve();
  });

  expect(getStats).toHaveBeenLastCalledWith("agent-1", "30d");
});

test("returns to apps when the agent cannot load", async () => {
  getAgent.mockImplementation(() => Promise.reject(new Error("missing")));
  const view = await render();

  expect(push).toHaveBeenCalledWith("/app/apps");
  expect(view.root.findAllByProps({ "data-sidebar": "agent-1" })).toHaveLength(0);
});
