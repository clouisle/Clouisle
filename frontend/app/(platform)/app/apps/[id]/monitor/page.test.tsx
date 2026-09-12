import { afterEach, expect, mock, test } from "bun:test";
import React from "react";
import { act, create, type ReactTestRenderer } from "@/test-utils/rtl-renderer";

const push = mock(() => {});
const router = { push };
const getAgent = mock(() => Promise.resolve({ id: "agent-1", name: "Support" }));
const statsFixture = () => ({
  overview: { total_conversations: 1200, total_messages: 25, active_users: 4 },
  tokens: { total_tokens: 2000000, prompt_tokens: 1500, completion_tokens: 500 },
  performance: {
    avg_response_time_ms: 1500,
    first_token_ms: { p50: 4649, p95: 30431.6, avg: 8583.58, samples: 67 },
  },
  tools: { tool_call_count: 3 },
  health: {
    completed: 67,
    failed: 2,
    stopped: 7,
    in_flight: 2,
    total: 76,
    success_rate: 67 / 76,
  },
  interventions: { steer: 10, stop: 7, follow_up: 0, total: 17 },
});
const getStats = mock(() => Promise.resolve(statsFixture()));
const trendsFixture = () => ({
  data: [
    {
      timestamp: "2026-09-08T00:00:00+08:00",
      label: "09/08",
      conversations: 3,
      messages: 36,
      tokens: 100,
      avg_response_time_ms: 30000,
      first_token_p50_ms: 6423,
      first_token_p95_ms: 45002,
    },
    {
      timestamp: "2026-09-09T00:00:00+08:00",
      label: "09/09",
      conversations: 5,
      messages: 42,
      tokens: 200,
      avg_response_time_ms: 25000,
      first_token_p50_ms: 4414,
      first_token_p95_ms: 7527,
    },
  ],
});
const getTrends = mock(() => Promise.resolve(trendsFixture()));
const getToolUsage = mock(() => Promise.resolve({ tools: [] }));

mock.module("next/navigation", () => ({ useRouter: () => router }));
mock.module("next-intl", () => ({
  useTranslations: () => (key: string, values?: Record<string, unknown>) =>
    values ? `${key}(${JSON.stringify(values)})` : key,
}));
mock.module("@/lib/api", () => ({
  agentsApi: { getAgent },
  agentStatsApi: { getStats, getTrends, getToolUsage },
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
let tooltip: { active: boolean; payload: Array<{ payload: unknown }> } = { active: false, payload: [] };
mock.module("@/components/ui/chart", () => ({
  ChartContainer: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  ChartTooltip: ({ content }: { content?: React.ReactNode | ((props: typeof tooltip) => React.ReactNode) }) => (
    <div data-tooltip={typeof content === "function" ? "custom" : "default"}>
      {typeof content === "function" ? content(tooltip) : content}
    </div>
  ),
  ChartTooltipContent: ({ formatter }: { formatter?: (value: unknown) => React.ReactNode }) => (
    <div data-tooltip-content>{formatter ? formatter(1500) : null}</div>
  ),
}));
const Chart = ({ children, ...props }: React.ComponentProps<"div">) => <div {...props}>{children}</div>;
mock.module("recharts", () => ({ Area: Chart, AreaChart: Chart, Bar: Chart, BarChart: Chart, Cell: Chart, Line: Chart, LineChart: Chart, Pie: Chart, PieChart: Chart, XAxis: Chart, YAxis: Chart, CartesianGrid: Chart }));

const { default: MonitorPage } = await import("./page");

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
let renderer: ReactTestRenderer | undefined;

afterEach(() => {
  if (renderer) act(() => renderer!.unmount());
  renderer = undefined;
  push.mockClear();
  getAgent.mockReset();
  getAgent.mockImplementation(() => Promise.resolve({ id: "agent-1", name: "Support" }));
  getStats.mockReset();
  getStats.mockImplementation(() => Promise.resolve(statsFixture()));
  getTrends.mockReset();
  getTrends.mockImplementation(() => Promise.resolve(trendsFixture()));
  getToolUsage.mockImplementation(() => Promise.resolve({ tools: [] }));
});

async function render() {
  await act(async () => {
    renderer = create(<MonitorPage params={Promise.resolve({ id: "agent-1" })} />);
    await Promise.resolve();
    await Promise.resolve();
  });
  return renderer!;
}

function textOf(node: ReactTestRenderer["root"]) {
  return node.findAll(() => true).flatMap((child) => child.children).filter((value): value is string => typeof value === "string").join(" ");
}

test("loads agent metrics without requesting the redundant conversation list", async () => {
  const view = await render();
  const output = textOf(view.root);

  expect(getAgent).toHaveBeenCalledWith("agent-1");
  expect(getStats).toHaveBeenCalledWith("agent-1", "7d");
  expect(getTrends).toHaveBeenCalledWith("agent-1", "7d");
  expect(getToolUsage).toHaveBeenCalledWith("agent-1", "7d");
  expect(view.root.findByProps({ "data-sidebar": "agent-1" })).toBeTruthy();
  expect(output).toContain("1.2K");
  expect(output).toContain("2.0M");
  expect(output).toContain("1.50s");
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

test("labels the tool usage distribution with display names", async () => {
  getToolUsage.mockImplementation(() => Promise.resolve({
    tools: [
      { name: "web_search", display_name: "Web Search", count: 36 },
      { name: "knowledge_search", display_name: "Knowledge Search", count: 2 },
    ],
  }));

  const view = await render();
  const output = textOf(view.root);

  // Raw identifiers are internal; the chart must show readable labels.
  expect(output).toContain("Web Search");
  expect(output).toContain("Knowledge Search");
  expect(output).not.toContain("web_search");
  expect(output).not.toContain("knowledge_search");
  // Each legend row carries its call count.
  expect(output).toContain("36");
  expect(output).toContain("2");
});

test("reports execution health with a success rate over terminal runs", async () => {
  const view = await render();
  const output = textOf(view.root);

  // 67 completed of 76 terminal runs; the 2 in-flight runs are excluded.
  expect(output).toContain("health.completed");
  expect(output).toContain("health.failed");
  expect(output).toContain("health.stopped");
  expect(output).toContain("health.successRate");
  expect(output).toContain("88.2%");
  expect(output).toContain('health.inFlight({"count":2})');
});

test("shows all three terminal health counts even when one is zero", async () => {
  getStats.mockImplementation(() => Promise.resolve({
    ...statsFixture(),
    health: {
      completed: 5,
      failed: 0,
      stopped: 2,
      in_flight: 0,
      total: 7,
      success_rate: 5 / 7,
    },
  }));

  const view = await render();
  const output = textOf(view.root);

  expect(output).toContain("71.4%");
  // A zero-value slice drops out of the donut but stays in the legend totals.
  expect(output).toContain("health.stopped");
});

test("shows first-token percentiles plus the series behind them", async () => {
  const view = await render();
  const output = textOf(view.root);

  // Summary tiles: the snapshot values.
  expect(output).toContain("firstToken.p50");
  expect(output).toContain("firstToken.p95");
  expect(output).toContain("4.65s");
  expect(output).toContain("30.43s");
  expect(output).toContain('firstToken.sampleCount({"count":"67"})');

  // Per-bucket series: the chart must plot the median and the tail, because
  // the tail can spike while the median holds (09/08 here).
  const series = view.root
    .findAllByProps({ dataKey: "first_token_p95_ms" })
    .concat(view.root.findAllByProps({ dataKey: "first_token_p50_ms" }));
  expect(series.length).toBeGreaterThanOrEqual(2);
});

test("plots null latency buckets as gaps rather than zeros", async () => {
  getTrends.mockImplementation(() => Promise.resolve({
    data: [
      { ...trendsFixture().data[0], first_token_p50_ms: null, first_token_p95_ms: null },
      trendsFixture().data[1],
    ],
  }));

  const view = await render();
  // A null bucket must not be coerced to 0, which would draw a fake drop.
  for (const key of ["first_token_p50_ms", "first_token_p95_ms"]) {
    const lines = view.root.findAllByProps({ dataKey: key });
    expect(lines[0].props.connectNulls).toBe(false);
  }
});

test("shows user interventions as ranked bars plus a per-run rate", async () => {
  const view = await render();
  const output = textOf(view.root);

  // Category labels live in the chart data (recharts renders the axis), so
  // assert on what the chart was handed rather than on rendered text.
  // follow_up is 0 and therefore filtered out of the chart.
  const rows = view.root.findByProps({ layout: "vertical" }).props.data as Array<{
    label: string;
    value: number;
  }>;
  expect(rows.map((r) => r.label)).toEqual([
    "interventions.steer",
    "interventions.stop",
  ]);
  expect(rows.map((r) => r.value)).toEqual([10, 7]);

  // 17 interventions over 76 terminal runs.
  expect(output).toContain("interventions.rate");
  expect(output).toContain("0.22");
  expect(output).toContain('interventions.rateHint({"runs":"76"})');
});

test("omits zero-count intervention bars", async () => {
  getStats.mockImplementation(() => Promise.resolve({
    ...statsFixture(),
    interventions: { steer: 4, stop: 0, follow_up: 0, total: 4 },
  }));

  const view = await render();
  const rows = view.root.findByProps({ layout: "vertical" }).props.data as Array<{
    key: string;
  }>;

  // Only categories with a count get a bar; the rate still reflects the total.
  expect(rows.map((r) => r.key)).toEqual(["steer"]);
  expect(textOf(view.root)).toContain("0.05");
});

test("falls back to empty states when a new agent has no runs or samples", async () => {
  getStats.mockImplementation(() => Promise.resolve({
    ...statsFixture(),
    performance: {
      avg_response_time_ms: 0,
      first_token_ms: { p50: 0, p95: 0, avg: 0, samples: 0 },
    },
    health: {
      completed: 0,
      failed: 0,
      stopped: 0,
      in_flight: 0,
      total: 0,
      success_rate: 0,
    },
    interventions: { steer: 0, stop: 0, follow_up: 0, total: 0 },
  }));

  const view = await render();
  const output = textOf(view.root);

  expect(output).toContain("health.empty");
  expect(output).toContain("firstToken.empty");
  expect(output).toContain("interventions.empty");
  // No success rate is claimed when there is nothing to divide by.
  expect(output).not.toContain("health.successRate");
});

test("falls back to the raw tool name when no display name is provided", async () => {
  getToolUsage.mockImplementation(() => Promise.resolve({
    tools: [{ name: "mcp_github_create_issue", display_name: "", count: 4 }],
  }));

  const view = await render();

  expect(textOf(view.root)).toContain("mcp_github_create_issue");
});

test("health tooltip reports each outcome's share of terminal runs", async () => {
  getTrends.mockImplementation(() => Promise.resolve({ data: [] }));
  getToolUsage.mockImplementation(() => Promise.resolve({ tools: [] }));
  getStats.mockImplementation(() => Promise.resolve({
    ...statsFixture(),
    health: {
      completed: 67,
      failed: 2,
      stopped: 7,
      in_flight: 2,
      total: 76,
      success_rate: 67 / 76,
    },
  }));
  tooltip = {
    active: true,
    payload: [{ payload: { key: "failed", label: "health.failed", value: 2 } }],
  };

  const view = await render();
  const rendered = view.root
    .findAllByProps({ "data-tooltip": "custom" })
    .map((node) => textOf(node))
    .find((text) => text.includes("health.failed"));

  expect(rendered).toBeDefined();
  expect(rendered).toContain("2");
  // 2 of 76 terminal runs.
  expect(rendered).toContain("2.6%");
});

test("intervention tooltip reports the category and its count", async () => {
  getTrends.mockImplementation(() => Promise.resolve({ data: [] }));
  getToolUsage.mockImplementation(() => Promise.resolve({ tools: [] }));
  tooltip = {
    active: true,
    payload: [{ payload: { key: "steer", label: "interventions.steer", value: 10 } }],
  };

  const view = await render();
  const rendered = view.root
    .findAllByProps({ "data-tooltip": "custom" })
    .map((node) => textOf(node))
    .find((text) => text.includes("interventions.steer"));

  expect(rendered).toBeDefined();
  expect(rendered).toContain("10");
});

test("tooltip shows the display name and call count for a hovered slice", async () => {
  // Empty health and interventions keep the tool-usage tooltip unambiguous.
  getStats.mockImplementation(() => Promise.resolve({
    ...statsFixture(),
    health: {
      completed: 0,
      failed: 0,
      stopped: 0,
      in_flight: 0,
      total: 0,
      success_rate: 0,
    },
    interventions: { steer: 0, stop: 0, follow_up: 0, total: 0 },
  }));
  getToolUsage.mockImplementation(() => Promise.resolve({
    tools: [{ name: "web_search", display_name: "Web Search", count: 36 }],
  }));
  tooltip = {
    active: true,
    payload: [{ payload: { name: "web_search", display_name: "Web Search", count: 36 } }],
  };

  const view = await render();
  const nodes = view.root.findAllByProps({ "data-tooltip": "custom" });

  expect(nodes).toHaveLength(1);
  const rendered = textOf(nodes[0]);
  expect(rendered).toContain("Web Search");
  expect(rendered).toContain("36");
  expect(rendered).not.toContain("web_search");
});

test("tooltip renders nothing when inactive", async () => {
  getStats.mockImplementation(() => Promise.resolve({
    ...statsFixture(),
    health: {
      completed: 0,
      failed: 0,
      stopped: 0,
      in_flight: 0,
      total: 0,
      success_rate: 0,
    },
    interventions: { steer: 0, stop: 0, follow_up: 0, total: 0 },
  }));
  getToolUsage.mockImplementation(() => Promise.resolve({
    tools: [{ name: "web_search", display_name: "Web Search", count: 36 }],
  }));
  tooltip = { active: false, payload: [] };

  const view = await render();

  for (const node of view.root.findAllByProps({ "data-tooltip": "custom" })) {
    expect(node.children).toHaveLength(0);
  }
});

test("response time tooltip labels the series through i18n", async () => {
  const view = await render();
  // Two charts format their values (response time and first-token latency), so
  // select by content: the response-time tooltip is the one carrying its label.
  const rendered = view.root
    .findAllByProps({ "data-tooltip-content": true })
    .map((node) => textOf(node))
    .filter((text) => text.length > 0);

  const responseTime = rendered.find((text) => text.includes("charts.avgResponseTime"));
  expect(responseTime).toBeDefined();
  // The test `t` returns the key, so this proves the label came from the
  // translation lookup rather than a hardcoded English string.
  expect(responseTime).not.toContain("Response Time");
  // Value stays in seconds while the axis keeps milliseconds.
  expect(responseTime).toContain("1.50s");
});

test("first-token tooltip formats its value through the shared formatter", async () => {
  const view = await render();
  const rendered = view.root
    .findAllByProps({ "data-tooltip-content": true })
    .map((node) => textOf(node))
    .filter((text) => text.length > 0);

  // formatDuration(1500) renders as seconds, not raw milliseconds.
  expect(rendered.some((text) => text.includes("1.50s"))).toBe(true);
  expect(rendered.every((text) => !text.includes("1500"))).toBe(true);
});
