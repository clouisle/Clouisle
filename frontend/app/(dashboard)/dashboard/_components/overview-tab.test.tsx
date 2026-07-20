import { expect, mock, test } from "bun:test";
import React from "react";
import { act, create, type ReactTestRenderer } from "react-test-renderer";

const element =
  (name: string) =>
  ({
    children,
    ...props
  }: React.PropsWithChildren<Record<string, unknown>>) => (
    <div data-chart={name}>{children}</div>
  );

Object.assign(globalThis, {
  window: { matchMedia: () => ({ matches: true }) },
});

mock.module("next-intl", () => ({
  useTranslations: () => (key: string) => key,
}));
mock.module("lucide-react", () => ({
  Users: () => null,
  Building2: () => null,
  Bot: () => null,
  Workflow: () => null,
  Database: () => null,
  MessageSquare: () => null,
  Activity: () => null,
  Coins: () => null,
  UserPlus: () => null,
  ShieldAlert: () => null,
  ShieldCheck: () => null,
}));
mock.module("@/components/ui/card", () => ({
  Card: element("card"),
  CardContent: element("content"),
  CardDescription: element("description"),
  CardHeader: element("header"),
  CardTitle: element("title"),
}));
mock.module("recharts", () => ({
  AreaChart: element("area-chart"),
  Area: element("area"),
  XAxis: element("x-axis"),
  YAxis: element("y-axis"),
  CartesianGrid: element("grid"),
  Tooltip: element("tooltip"),
  ResponsiveContainer: element("container"),
  Legend: element("legend"),
}));

const { OverviewTab } = await import("./overview-tab");

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const render = (totpStats: unknown, passwordExpiration: unknown = null) => {
  let renderer: ReactTestRenderer;
  act(() => {
    renderer = create(
      <OverviewTab
        stats={
          {
            overview: {
              total_users: 1500,
              total_conversations: 4,
              total_tokens: 3000000,
              total_teams: 2,
              total_agents: 3,
              total_workflows: 4,
              total_knowledge_bases: 5,
            },
            active_users: { dau: 20, wau: 30, mau: 40 },
            password_expiration: passwordExpiration,
          } as never
        }
        trendsData={[
          {
            date: "2026-01-01",
            new_users: 1,
            active_users: 2,
            new_conversations: 3,
            messages: 4,
            tokens: 5,
          },
        ]}
        isLoading={false}
        totpStats={totpStats as never}
      />,
    );
  });
  return renderer!;
};

test("renders dashboard trends and two-factor adoption when the statistics are available", () => {
  const renderer = render({
    totp_enabled: 5,
    total_users: 10,
    adoption_rate: 50,
  });

  expect(
    renderer.root.findAllByProps({ "data-chart": "area-chart" }),
  ).toHaveLength(2);
  expect(
    renderer.root.findAllByType("p").map((node) => node.children.join("")),
  ).toContain("1.5K");
  expect(
    renderer.root.findAllByType("p").map((node) => node.children.join("")),
  ).toContain("50.0% stats.adoptionRate");
  act(() => renderer.unmount());
});

test("omits optional security summaries when their data is unavailable", () => {
  const renderer = render(null);

  expect(
    renderer.root.findAllByType("p").map((node) => node.children.join("")),
  ).not.toContain("stats.twoFactorAuth");
  expect(
    renderer.root.findAllByType("p").map((node) => node.children.join("")),
  ).not.toContain("passwordExpiration.title");
  act(() => renderer.unmount());
});
