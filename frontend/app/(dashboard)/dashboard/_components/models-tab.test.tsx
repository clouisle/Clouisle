import { afterEach, expect, mock, test } from "bun:test";
import React from "react";
import { act, create, type ReactTestRenderer } from "@/test-utils/rtl-renderer";

const chart = (name: string) => {
  const Component = (props: Record<string, unknown>) => (
    <div data-chart={name} data-props={JSON.stringify(props)} />
  );
  Component.displayName = name;
  return Component;
};

Object.assign(globalThis, {
  window: { matchMedia: () => ({ matches: true }) },
});

mock.module("next-intl", () => ({
  useTranslations: () => (key: string) => key,
}));
mock.module("lucide-react", () => ({
  Coins: () => null,
  MessageSquare: () => null,
}));
mock.module("@/components/ui/card", () => ({
  Card: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  CardContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
}));
mock.module("@/components/dashboard/model-distribution-chart", () => ({
  ModelDistributionChart: chart("models"),
}));
mock.module("@/components/dashboard/model-details-card", () => ({
  ModelDetailsCard: chart("details"),
}));
mock.module("@/components/dashboard/team-token-usage-chart", () => ({
  TeamTokenUsageChart: chart("teams"),
}));
mock.module("@/components/dashboard/token-trend-chart", () => ({
  TokenTrendChart: chart("trends"),
}));
mock.module("@/components/dashboard/top-agents-chart", () => ({
  TopAgentsChart: chart("agents"),
}));

const { ModelsTab } = await import("./models-tab");

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const props = {
  stats: { overview: { total_tokens: 2500, total_messages: 2 } },
  modelData: [],
  teamTokenData: [],
  topAgentsData: [],
  trendsData: [],
  isLoading: false,
} as never;

const render = (overrides = {}) => {
  let renderer: ReactTestRenderer;
  act(() => {
    renderer = create(<ModelsTab {...props} {...overrides} />);
  });
  return renderer!;
};

afterEach(() => mock.clearAllMocks());

test("passes dashboard model data and the calculated token average to its charts", () => {
  const renderer = render();

  expect(renderer.root.findByProps({ "data-chart": "models" })).toBeDefined();
  expect(renderer.root.findByProps({ "data-chart": "teams" })).toBeDefined();
  expect(
    renderer.root.findAllByType("p").map((node) => node.children.join("")),
  ).toContain("1.3K");
  expect(renderer.root.findAllByProps({ "data-chart": "agents" })).toHaveLength(
    0,
  );
  act(() => renderer.unmount());
});

test("shows top agents while loading even when their data is empty", () => {
  const renderer = render({ isLoading: true });

  expect(
    renderer.root.findByProps({ "data-chart": "agents" }).props["data-props"],
  ).toContain("total_tokens");
  act(() => renderer.unmount());
});
