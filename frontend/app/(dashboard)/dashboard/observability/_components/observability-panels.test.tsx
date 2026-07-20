import { expect, mock, test } from "bun:test";
import React from "react";
import { act, create, type ReactTestRenderer } from "react-test-renderer";

const element = ({
  children,
  ...props
}: React.PropsWithChildren<Record<string, unknown>>) => (
  <div {...props}>{children}</div>
);
const icon = () => null;

mock.module("next-intl", () => ({
  useTranslations: () => (key: string) => key,
}));
mock.module("lucide-react", () => ({
  AlertTriangle: icon,
  ChevronRight: icon,
  Cpu: icon,
  Database: icon,
  HardDrive: icon,
  Info: icon,
  Server: icon,
  Workflow: icon,
}));
mock.module("recharts", () => ({
  Area: element,
  AreaChart: element,
  Bar: element,
  BarChart: element,
  CartesianGrid: element,
  Legend: element,
  Line: element,
  LineChart: element,
  ResponsiveContainer: element,
  Tooltip: element,
  XAxis: element,
  YAxis: element,
}));
mock.module("@/components/ui/alert", () => ({
  Alert: element,
  AlertDescription: element,
  AlertTitle: element,
}));
mock.module("@/components/ui/badge", () => ({ Badge: element }));
mock.module("@/components/ui/button", () => ({
  Button: ({
    children,
    ...props
  }: React.ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button {...props}>{children}</button>
  ),
}));
mock.module("@/components/ui/card", () => ({
  Card: element,
  CardContent: element,
  CardDescription: element,
  CardHeader: element,
  CardTitle: element,
}));
mock.module("@/components/ui/sheet", () => ({
  Sheet: element,
  SheetContent: element,
  SheetDescription: element,
  SheetHeader: element,
  SheetTitle: element,
}));
mock.module("@/components/ui/skeleton", () => ({ Skeleton: element }));
mock.module("@/components/ui/table", () => ({
  Table: element,
  TableBody: element,
  TableCell: element,
  TableHead: element,
  TableHeader: element,
  TableRow: element,
}));
mock.module("@/lib/api/admin/observability", () => ({
  observabilityApi: { getAgentDetail: mock(), getWorkflowDetail: mock() },
}));
mock.module("./observability-helpers", () => ({
  TONE_STYLES: {},
  abnormalReason: () => "",
  formatBucket: () => "",
  formatCompactNumber: () => "",
  formatDuration: () => "",
  formatNumber: (value: number) => String(value),
  formatPercent: () => "",
  getRiskLevel: () => ({ tone: "success", key: "low", summaryKey: "healthy" }),
  percentOf: () => 0,
  readNumber: () => 0,
  readString: () => "",
  sourceLabel: () => "",
  statusLabel: () => "",
  timeoutTypeLabel: () => "",
  toneBarClass: () => "",
  toneDotClass: () => "",
  toneForStatus: () => "neutral",
  toneTextClass: () => "",
}));

const { ErrorState, ObservabilitySkeleton } =
  await import("./observability-panels");

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const render = (node: React.ReactElement) => {
  let renderer: ReactTestRenderer;
  act(() => {
    renderer = create(node);
  });
  return renderer!;
};

test("retries an observability request from its error state", () => {
  const retry = mock();
  const renderer = render(<ErrorState onRetry={retry} />);

  act(() => renderer.root.findByType("button").props.onClick());

  expect(retry).toHaveBeenCalledTimes(1);
  expect(renderer.root.findByType("button").children).toEqual([
    "actions.retry",
  ]);
  act(() => renderer.unmount());
});

test("adds a table placeholder for observability table tabs", () => {
  const overview = render(<ObservabilitySkeleton tab="overview" />);
  const agents = render(<ObservabilitySkeleton tab="agents" />);

  expect(
    overview.root.findAllByProps({ className: "h-[420px] rounded-xl" }),
  ).toHaveLength(0);
  expect(
    agents.root.findAllByProps({ className: "h-[420px] rounded-xl" }),
  ).toHaveLength(2);
  act(() => {
    overview.unmount();
    agents.unmount();
  });
});
