import { describe, expect, mock, test } from "bun:test";
import type { ReactNode } from "react";

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
  useState: <T,>(initial: T) => [initial, () => undefined] as const,
}));
mock.module("next-intl", () => ({
  useTranslations: () => (key: string) => key,
}));
mock.module("@/lib/utils", () => ({
  cn: (...values: unknown[]) => values.filter(Boolean).join(" "),
}));
mock.module("lucide-react", () => ({
  CheckCircle2: () => null,
  ChevronDown: () => null,
  Circle: () => null,
  Loader2: () => null,
  SkipForward: () => null,
  XCircle: () => null,
}));
mock.module("@/components/ui/collapsible", () => ({
  Collapsible: ({ children }: { children: ReactNode }) => children,
  CollapsibleContent: ({ children }: { children: ReactNode }) => children,
  CollapsibleTrigger: ({ children }: { children: ReactNode }) => children,
}));

const { NodeCard } = await import("./node-card");

type Tree = { type: unknown; props: Record<string, unknown> };

function render(
  node: React.ComponentProps<typeof NodeCard>["node"],
  compact = false,
) {
  return NodeCard({ node, compact }) as Tree;
}

describe("NodeCard", () => {
  test("renders a completed node with duration and structured input/output details", () => {
    const tree = render({
      id: "node-1",
      type: "tool",
      label: "Search",
      status: "completed",
      duration: 120,
      input: { query: "coverage" },
      output: { count: 2 },
    });

    const content = JSON.stringify(tree.props.children);
    expect(tree.props.className).toContain("bg-green-50");
    expect(content).toContain("Search");
    expect(content).toContain('"children":[120,"ms"]');
    expect(content).toContain("showDetails");
    expect(content).toContain('\\"query\\": \\"coverage\\"');
    expect(content).toContain('\\"count\\": 2');
  });

  test("renders running and error states while hiding error outputs", () => {
    const tree = render({
      id: "node-2",
      type: "tool",
      label: "Call API",
      status: "error",
      error: "Timed out",
      output: "private response",
    });

    expect(tree.props.className).toContain("bg-red-50");
    expect(JSON.stringify(tree.props.children)).toContain("Timed out");
    expect(JSON.stringify(tree.props.children)).not.toContain(
      "private response",
    );
  });

  test("omits details for compact pending nodes", () => {
    const tree = render(
      {
        id: "node-3",
        type: "tool",
        label: "Queued",
        status: "pending",
        input: { queued: true },
      },
      true,
    );

    expect(tree.props.className).toContain("bg-muted");
    expect(JSON.stringify(tree.props.children)).toContain("Queued");
    expect(JSON.stringify(tree.props.children)).not.toContain("showDetails");
  });
});
