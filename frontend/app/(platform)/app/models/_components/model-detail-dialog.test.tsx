import { expect, mock, test } from "bun:test";
import React from "react";
import { act, create } from "react-test-renderer";

mock.module("next-intl", () => ({
  useTranslations: () => {
    const translate = (
      key: string,
      values?: Record<string, string | number>,
    ) => (values?.percent === undefined ? key : `${key}:${values.percent}`);
    translate.has = () => false;
    return translate;
  },
}));
mock.module("lucide-react", () => ({
  MessageSquare: () => null,
  Layers: () => null,
  ArrowUpDown: () => null,
  Volume2: () => null,
  Mic: () => null,
  Image: () => null,
  Video: () => null,
  Infinity: () => <span>∞</span>,
  TrendingUp: () => null,
  Calendar: () => null,
  CalendarDays: () => null,
  Hash: () => null,
  Zap: () => null,
}));
const element = ({
  children,
  ...props
}: React.PropsWithChildren<Record<string, unknown>>) => (
  <div {...props}>{children}</div>
);
mock.module("@/components/ui/dialog", () => ({
  Dialog: element,
  DialogContent: element,
  DialogHeader: element,
  DialogTitle: element,
}));
mock.module("@/components/ui/badge", () => ({ Badge: element }));
mock.module("@/components/ui/separator", () => ({ Separator: () => <hr /> }));
mock.module("@/components/ui/progress", () => ({
  Progress: ({ value, ...props }: { value: number }) => (
    <div {...props} data-value={value} />
  ),
}));
mock.module("@/lib/utils", () => ({
  cn: (...values: Array<string | false | null | undefined>) =>
    values.filter(Boolean).join(" "),
}));

const { ModelDetailDialog } = await import("./model-detail-dialog");

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const teamModel = {
  is_enabled: false,
  priority: 3,
  daily_tokens_used: 950,
  daily_token_limit: 1_000,
  monthly_tokens_used: 1_500,
  monthly_token_limit: 2_000,
  daily_requests_used: 25,
  daily_request_limit: 0,
  monthly_requests_used: 3,
  monthly_request_limit: null,
  model: {
    name: "Assistant",
    model_id: "assistant-1",
    provider: "unknown-provider",
    model_type: "unknown-type",
  },
} as never;

test("shows model quotas with capped progress and unlimited fallback", () => {
  let renderer: ReturnType<typeof create>;
  act(() => {
    renderer = create(
      <ModelDetailDialog open onOpenChange={mock()} teamModel={teamModel} />,
    );
  });

  const text = renderer!.root
    .findAllByType("span")
    .map((node) => node.children.join(""))
    .join(" ");
  expect(text).toContain("Assistant");
  expect(text).toContain("950 / 1.00K");
  expect(text).toContain("∞");
  expect(renderer!.root.findAllByProps({ "data-value": 95 })).toHaveLength(1);
  expect(renderer!.root.findAllByProps({ "data-value": 75 })).toHaveLength(1);
  expect(renderer!.root.findAllByProps({ "data-value": 5 })).toHaveLength(2);
  act(() => renderer!.unmount());
});

test("does not render without a selected team model", () => {
  let renderer: ReturnType<typeof create>;
  act(() => {
    renderer = create(
      <ModelDetailDialog open onOpenChange={mock()} teamModel={null} />,
    );
  });

  expect(renderer!.toJSON()).toBeNull();
  act(() => renderer!.unmount());
});
