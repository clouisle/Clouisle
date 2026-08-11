import { expect, mock, test } from "bun:test";
import React from "react";
import { act, create } from "react-test-renderer";

mock.module("next-intl", () => ({
  useTranslations: () => {
    const translate = (key: string) => key;
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
}));
const element = ({
  children,
  ...props
}: React.PropsWithChildren<Record<string, unknown>>) => (
  <div {...props}>{children}</div>
);
mock.module("@/components/ui/card", () => ({
  Card: element,
  CardContent: element,
}));
mock.module("@/components/ui/badge", () => ({ Badge: element }));
mock.module("@/components/ui/skeleton", () => ({ Skeleton: element }));
mock.module("@/components/ui/progress", () => ({
  Progress: ({ value, ...props }: { value: number }) => (
    <div {...props} data-value={value} />
  ),
}));
mock.module("@/components/ui/tooltip", () => ({
  Tooltip: element,
  TooltipContent: element,
  TooltipTrigger: element,
}));
mock.module("@/lib/utils", () => ({
  cn: (...values: Array<string | false | null | undefined>) =>
    values.filter(Boolean).join(" "),
}));

const { ModelCard, ModelCardSkeleton } = await import("./model-card");

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const teamModel = {
  is_enabled: false,
  priority: 2,
  daily_tokens_used: 1_500,
  daily_token_limit: 2_000,
  monthly_tokens_used: 0,
  monthly_token_limit: null,
  model: {
    name: "Assistant",
    model_id: "assistant-1",
    provider: "unknown-provider",
    provider_display_name: "Acme Gateway",
    model_type: "unknown-type",
  },
} as never;

test("renders disabled model quota state and opens its details", () => {
  const onClick = mock();
  let renderer: ReturnType<typeof create>;
  act(() => {
    renderer = create(<ModelCard teamModel={teamModel} onClick={onClick} />);
  });

  const text = renderer!.root
    .findAllByType("span")
    .map((node) => node.children.join(""))
    .join(" ");
  expect(text).toContain("Assistant");
  expect(renderer!.root.findAllByType("div").some((node) => node.children.includes("Acme Gateway"))).toBe(true);
  expect(
    renderer!.root.findAllByType("div").map((node) => node.children.join("")),
  ).toContain("disabled");
  expect(text).toContain("1.5K/2.0K");
  expect(text).toContain("∞");
  expect(renderer!.root.findAllByProps({ "data-value": 75 })).toHaveLength(1);
  act(() => {
    renderer!.root
      .findAllByType("div")
      .find((node) => node.props.onClick)
      ?.props.onClick();
  });
  expect(onClick).toHaveBeenCalledTimes(1);
  act(() => renderer!.unmount());
});

test("renders the model-card loading skeleton", () => {
  let renderer: ReturnType<typeof create>;
  act(() => {
    renderer = create(<ModelCardSkeleton />);
  });

  expect(renderer!.root.findAllByType("div")).not.toHaveLength(0);
  act(() => renderer!.unmount());
});
