import { expect, mock, test } from "bun:test";
import React from "react";
import { act, create, type ReactTestRenderer } from "@/test-utils/rtl-renderer";

const chart = (name: string) => {
  const Component = (props: Record<string, unknown>) => (
    <div data-chart={name} data-props={JSON.stringify(props)} />
  );
  Component.displayName = name;
  return Component;
};
const onMetricChange = mock(() => {});

Object.assign(globalThis, {
  window: { matchMedia: () => ({ matches: true }) },
});

mock.module("next-intl", () => ({
  useTranslations: () => (key: string) => key,
}));
mock.module("lucide-react", () => ({
  Workflow: () => null,
  TrendingUp: () => null,
  Clock: () => null,
  Bot: () => null,
}));
mock.module("@/components/ui/card", () => ({
  Card: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  CardContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
}));
mock.module("@/components/dashboard/agent-performance-chart", () => ({
  AgentPerformanceChart: chart("agents"),
}));
mock.module("@/components/dashboard/workflow-status-chart", () => ({
  WorkflowStatusChart: chart("status"),
}));
mock.module("@/components/dashboard/workflow-trigger-chart", () => ({
  WorkflowTriggerChart: chart("triggers"),
}));
mock.module("@/components/dashboard/top-workflows-card", () => ({
  TopWorkflowsCard: chart("workflows"),
}));

const { AnalyticsTab } = await import("./analytics-tab");

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const render = (workflowData: unknown, topAgentsData: unknown[] = []) => {
  let renderer: ReactTestRenderer;
  act(() => {
    renderer = create(
      <AnalyticsTab
        stats={
          {
            overview: {
              total_messages: 2000,
              total_conversations: 4,
              total_tokens: 3000000,
            },
          } as never
        }
        workflowData={workflowData as never}
        topAgentsData={topAgentsData as never}
        isLoading={false}
        isLoadingAgents={false}
        onMetricChange={onMetricChange}
        currentMetric="message_count"
      />,
    );
  });
  return renderer!;
};

test("passes workflow data and the selected metric to analytics charts", () => {
  const renderer = render(
    {
      total_runs: 7,
      success_rate: 99.5,
      avg_duration_ms: 1200,
      status_distribution: [{ name: "success" }],
      trigger_type_distribution: [{ name: "manual" }],
      top_workflows: [],
    },
    [{ name: "Agent One", value: 1 }],
  );

  expect(
    renderer.root.findByProps({ "data-chart": "agents" }).props["data-props"],
  ).toContain("message_count");
  expect(
    renderer.root.findByProps({ "data-chart": "status" }).props["data-props"],
  ).toContain("success");
  expect(
    renderer.root.findAllByType("span").map((node) => node.children.join("")),
  ).toContain("1.5K");
  act(() => renderer.unmount());
});

test("renders safe empty workflow and top-agent defaults", () => {
  const renderer = render(null);

  expect(
    renderer.root.findByProps({ "data-chart": "workflows" }).props[
      "data-props"
    ],
  ).toContain("[]");
  expect(
    renderer.root.findAllByType("p").map((node) => node.children.join("")),
  ).toContain("N/A");
  act(() => renderer.unmount());
});
