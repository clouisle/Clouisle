import { describe, expect, mock, test } from "bun:test";
import type { ReactNode } from "react";

const jsx = (type: unknown, props: Record<string, unknown>) => ({
  type,
  props,
});

// What the component asked the dictionary for, so a test can assert a number
// that only ever reaches the user through an ICU argument.
const translationCalls: Array<{
  key: string;
  values?: Record<string, unknown>;
}> = [];

function progressPercents(): Array<unknown> {
  return translationCalls
    .filter((call) => call.key === "progressPercent")
    .map((call) => call.values?.percent);
}

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
  useTranslations: () => (key: string, values?: Record<string, unknown>) => {
    translationCalls.push({ key, values });
    return key;
  },
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

  test("shows a running call's completion percentage and server message", () => {
    translationCalls.length = 0
    const tree = render({
      type: "tool-call",
      toolCallId: "call-4",
      toolName: "mcp_docs_index",
      input: {},
      state: "running",
      progress: { progress: 2, total: 8, message: "indexing" },
    });

    expect(progressPercents()).toEqual([25, 25]);
    expect(JSON.stringify(tree.props.children)).toContain("indexing");
  });

  test("clamps a reported percentage into the visible range", () => {
    translationCalls.length = 0
    render({
      type: "tool-call",
      toolCallId: "call-5",
      toolName: "mcp_docs_index",
      input: {},
      state: "running",
      progress: { progress: 12, total: 8 },
    });

    expect(progressPercents()).toEqual([100, 100]);
  });

  test("falls back to the raw step count when the server reports no total", () => {
    translationCalls.length = 0
    const tree = render({
      type: "tool-call",
      toolCallId: "call-6",
      toolName: "mcp_docs_index",
      input: {},
      state: "running",
      progress: { progress: 3 },
    });

    expect(progressPercents()).toEqual([]);
    expect(JSON.stringify(tree.props.children)).toContain('"3"');
  });

  test("treats a zero total as indeterminate instead of dividing by zero", () => {
    translationCalls.length = 0
    const tree = render({
      type: "tool-call",
      toolCallId: "call-8",
      toolName: "mcp_docs_index",
      input: {},
      state: "running",
      progress: { progress: 4, total: 0 },
    });

    expect(progressPercents()).toEqual([]);
    expect(JSON.stringify(tree.props.children)).toContain('"4"');
  });

  test("shows progress on a running MCP call too", () => {
    translationCalls.length = 0
    const tree = render(
      {
        type: "mcp-tool-call",
        toolCallId: "call-9",
        serverName: "docs",
        toolName: "index",
        input: {},
        state: "running",
        progress: { progress: 1, total: 4 },
      },
      { isMcp: true },
    );

    expect(progressPercents()).toEqual([25, 25]);
    expect(JSON.stringify(tree.props.children)).toContain("@ ");
  });

  test("hides a finished call's last progress tick", () => {
    translationCalls.length = 0
    const tree = render({
      type: "tool-call",
      toolCallId: "call-7",
      toolName: "mcp_docs_index",
      input: {},
      state: "done",
      progress: { progress: 8, total: 8, message: "indexed" },
    });

    const json = JSON.stringify(tree.props.children);
    expect(progressPercents()).toEqual([]);
    expect(json).not.toContain("indexed");
  });
});
