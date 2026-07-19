import { describe, expect, mock, test } from "bun:test";
import type { ReactNode } from "react";

const setters: unknown[] = [];
const jsx = (type: unknown, props: Record<string, unknown>) => ({
  type,
  props,
});

mock.module("react/jsx-runtime", () => ({
  jsx,
  jsxs: jsx,
  Fragment: Symbol.for("react.fragment"),
}));
mock.module("react/jsx-dev-runtime", () => ({
  jsxDEV: jsx,
  Fragment: Symbol.for("react.fragment"),
}));
mock.module("react", () => ({
  useEffect: (effect: () => void | (() => void)) => effect(),
  useState: <T,>(initial: T) =>
    [initial, (value: T) => setters.push(value)] as const,
}));
mock.module("next-intl", () => ({
  useTranslations: () => (key: string, values?: Record<string, unknown>) =>
    values ? `${key}:${JSON.stringify(values)}` : key,
}));
mock.module("@/lib/utils", () => ({
  cn: (...values: unknown[]) => values.filter(Boolean).join(" "),
}));
mock.module("lucide-react", () => ({
  Brain: () => null,
  ChevronDown: () => null,
  Loader2: () => null,
}));
mock.module("@/components/ui/collapsible", () => ({
  Collapsible: ({ children }: { children: ReactNode }) => children,
  CollapsibleContent: ({ children }: { children: ReactNode }) => children,
  CollapsibleTrigger: ({ children }: { children: ReactNode }) => children,
}));

const { ReasoningContent } = await import("./reasoning-content");

type Tree = { type: unknown; props: Record<string, unknown> };

function content(part: React.ComponentProps<typeof ReasoningContent>["part"]) {
  setters.length = 0;
  return ReasoningContent({ part }) as Tree;
}

describe("ReasoningContent", () => {
  test("shows a streaming state, opens automatically, and renders the cursor", () => {
    const tree = content({
      type: "reasoning",
      text: "Analyzing",
      state: "streaming",
    });

    expect(tree.props.open).toBe(false);
    expect(setters).toEqual([true]);
    expect(JSON.stringify(tree.props.children)).toContain("thinking");
    expect(JSON.stringify(tree.props.children)).toContain("animate-blink");
  });

  test.each([
    [500, "500ms"],
    [2500, "2s"],
    [61000, "1m 1s"],
  ])("formats a %ims duration", (duration, label) => {
    const tree = content({ type: "reasoning", text: "Done", duration });

    const trigger = (tree.props.children as Tree[])[0];
    const status = (trigger.props.children as Tree[])[1];

    expect(status.props.children).toBe(
      `thoughtFor:${JSON.stringify({ seconds: label })}`,
    );
  });

  test("uses the processing fallback and respects the default open state", () => {
    const tree = ReasoningContent({
      part: { type: "reasoning", text: "" },
      defaultOpen: true,
      className: "custom",
    }) as Tree;

    expect(tree.props.open).toBe(true);
    expect(tree.props.className).toContain("custom");
    expect(JSON.stringify(tree.props.children)).toContain("processing");
  });
});
