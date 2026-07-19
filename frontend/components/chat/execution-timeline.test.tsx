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
mock.module("next-intl", () => ({
  useTranslations: () => (key: string) => key,
}));
mock.module("@/lib/utils", () => ({
  cn: (...values: unknown[]) => values.filter(Boolean).join(" "),
}));
mock.module("./node-card", () => ({
  NodeCard: ({
    node,
    compact,
  }: {
    node: { label: string };
    compact: boolean;
  }) => <div>{`${node.label}:${compact}`}</div>,
}));

const { ExecutionTimeline } = await import("./execution-timeline");

type Tree = { type: unknown; props: Record<string, unknown> };

function state(
  nodes: Array<{ id: string; label: string }>,
  current = 0,
  total = 0,
) {
  return {
    nodes: new Map(
      nodes.map((node) => [
        node.id,
        { ...node, type: "tool", status: "done" as const },
      ]),
    ),
    progress: { current, total },
  };
}

describe("ExecutionTimeline", () => {
  test("does not render an empty execution", () => {
    expect(ExecutionTimeline({ executionState: state([]) })).toBeNull();
  });

  test("shows progress and detailed vertical node cards", () => {
    const tree = ExecutionTimeline({
      executionState: state(
        [
          { id: "first", label: "Retrieve" },
          { id: "second", label: "Answer" },
        ],
        1,
        2,
      ),
    }) as Tree;

    const content = JSON.stringify(tree.props.children);
    expect(content).toContain("progress");
    expect(content).toContain("1");
    expect(content).toContain("50%");
    expect(content).toContain('"label":"Retrieve"');
    expect(content).toContain('"label":"Answer"');
    expect(content).toContain('"compact":false');
  });

  test("uses horizontal compact cards without progress when the total is zero", () => {
    const tree = ExecutionTimeline({
      executionState: state([{ id: "only", label: "Run" }]),
      layout: "horizontal",
      showDetails: false,
    }) as Tree;

    expect(JSON.stringify(tree.props.children)).toContain('"label":"Run"');
    expect(JSON.stringify(tree.props.children)).toContain('"compact":true');
    expect(JSON.stringify(tree.props.children)).toContain("overflow-x-auto");
    expect(JSON.stringify(tree.props.children)).not.toContain("progress");
  });
});
