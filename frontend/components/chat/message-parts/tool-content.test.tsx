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
  Check: () => null,
  ChevronDown: () => null,
  Clock: () => null,
  Loader2: () => null,
  Server: () => null,
  Wrench: () => null,
  X: () => null,
}));
mock.module("@/components/ui/collapsible", () => ({
  Collapsible: ({ children }: { children: ReactNode }) => children,
  CollapsibleContent: ({ children }: { children: ReactNode }) => children,
  CollapsibleTrigger: ({ children }: { children: ReactNode }) => children,
}));

const { ToolContent } = await import("./tool-content");

type Tree = { type: unknown; props: Record<string, unknown> };

function render(
  part: React.ComponentProps<typeof ToolContent>["part"],
  props = {},
) {
  return ToolContent({ part, ...props }) as Tree;
}

describe("ToolContent", () => {
  test("shows a running call's display name and formatted input", () => {
    const tree = render({
      type: "tool-call",
      toolCallId: "call-1",
      toolName: "internal_search",
      toolDisplayName: "Search docs",
      input: { query: "coverage" },
      state: "running",
    });

    expect(JSON.stringify(tree.props.children)).toContain("Search docs");
    expect(JSON.stringify(tree.props.children)).toContain("running");
    expect(JSON.stringify(tree.props.children)).toContain(
      '\\"query\\": \\"coverage\\"',
    );
  });

  test("shows an MCP result's server, output, error state, and custom class", () => {
    const tree = render(
      {
        type: "mcp-tool-result",
        toolCallId: "call-2",
        serverName: "linear",
        toolName: "get_issue",
        output: { message: "not found" },
        isError: true,
      },
      { isMcp: true, defaultOpen: true, className: "custom" },
    );

    expect(tree.props.open).toBe(true);
    expect(tree.props.className).toContain("border-red-500/30");
    expect(tree.props.className).toContain("custom");
    expect(JSON.stringify(tree.props.children)).toContain('"@ ","linear"');
    expect(JSON.stringify(tree.props.children)).toContain("error");
    expect(JSON.stringify(tree.props.children)).toContain(
      '\\"message\\": \\"not found\\"',
    );
  });

  test("renders pending string results without an error style", () => {
    const tree = render({
      type: "tool-result",
      toolCallId: "call-3",
      toolName: "calculator",
      output: "42",
    });

    expect(JSON.stringify(tree.props.children)).toContain("completed");
    expect(JSON.stringify(tree.props.children)).toContain("42");
    expect(tree.props.className).not.toContain("border-red-500/30");
  });
});
