import { beforeEach, describe, expect, mock, test } from "bun:test";
import type { ComponentProps, ReactNode } from "react";

let state: unknown[] = [];
let stateIndex = 0;
let effects: Array<{
  cleanup?: () => void;
  dependency?: unknown;
}> = [];
let effectIndex = 0;
let nextTimer = 1;
const timers = new Map<number, () => void>();
const clearedTimers: number[] = [];

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props });
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
  memo: <T,>(component: T) => component,
  useCallback: <T,>(callback: T) => callback,
  useEffect: (
    effect: () => void | (() => void),
    dependencies?: readonly unknown[],
  ) => {
    const index = effectIndex++;
    const dependency = dependencies?.[0];
    if (Object.is(effects[index]?.dependency, dependency)) return;
    effects[index]?.cleanup?.();
    const cleanup = effect();
    effects[index] = { cleanup: cleanup || undefined, dependency };
  },
  useMemo: <T,>(factory: () => T) => factory(),
  useState: <T,>(initial: T) => {
    const index = stateIndex++;
    state[index] ??= initial;
    return [
      state[index] as T,
      (value: T | ((previous: T) => T)) => {
        state[index] =
          typeof value === "function"
            ? (value as (previous: T) => T)(state[index] as T)
            : value;
      },
    ] as const;
  },
}));
mock.module("next-intl", () => ({
  useTranslations: () => (key: string, values?: Record<string, unknown>) =>
    values?.count === undefined ? key : `${key}:${values.count}`,
}));
mock.module("lucide-react", () => ({
  ChevronDown: () => null,
  ChevronRight: () => null,
  FileText: () => null,
  Link2: () => null,
  X: () => null,
}));
mock.module("@/lib/utils", () => ({
  cn: (...values: unknown[]) => values.filter(Boolean).join(" "),
}));

Object.assign(globalThis, {
  window: {
    clearTimeout: (handle: number) => {
      clearedTimers.push(handle);
      timers.delete(handle);
    },
    setTimeout: (callback: () => void) => {
      const handle = nextTimer++;
      timers.set(handle, callback);
      return handle;
    },
  },
});

const { SourceContent } = await import("./source-content");

type Tree = { type: unknown; props: Record<string, unknown> };

function resolve(node: ReactNode): Tree | ReactNode {
  if (!node || typeof node !== "object" || !("type" in node)) return node;
  const tree = node as Tree;
  return typeof tree.type === "function"
    ? resolve(
        (tree.type as (props: Record<string, unknown>) => ReactNode)(tree.props),
      )
    : tree;
}

function find(node: ReactNode, predicate: (tree: Tree) => boolean): Tree {
  for (const child of Array.isArray(node) ? node : [node]) {
    if (Array.isArray(child)) {
      try {
        return find(child, predicate);
      } catch {
        continue;
      }
    }
    const tree = resolve(child);
    if (!tree || typeof tree !== "object" || !("type" in tree)) continue;
    if (predicate(tree as Tree)) return tree as Tree;
    try {
      return find((tree as Tree).props.children as ReactNode, predicate);
    } catch {
      continue;
    }
  }
  throw new Error("Element not found");
}

function render(sources: ComponentProps<typeof SourceContent>["sources"]) {
  stateIndex = 0;
  effectIndex = 0;
  return SourceContent({ sources });
}

beforeEach(() => {
  effects.forEach((effect) => effect.cleanup?.());
  state = [];
  effects = [];
  stateIndex = 0;
  effectIndex = 0;
  nextTimer = 1;
  timers.clear();
  clearedTimers.length = 0;
});

describe("SourceContent issue #255 coverage", () => {
  test("falls back for malformed URLs and expands source batches", () => {
    const sources = [
      { type: "source-url" as const, url: "not a valid URL" },
      ...Array.from({ length: 20 }, (_, index) => ({
        type: "source-url" as const,
        url: `https://example.com/${index}`,
      })),
    ];

    find(render(sources), (node) => node.props["aria-expanded"] === false).props
      .onClick();
    const expanded = render(sources);

    expect(
      find(
        expanded,
        (node) =>
          node.type === "span" && node.props.children === "not a valid URL",
      ),
    ).toBeDefined();
    find(
      expanded,
      (node) => node.props.children === "showMoreSources:1",
    ).props.onClick();

    expect(JSON.stringify(render(sources))).toContain("https://example.com/19");
  });

  test("cancels deferred segment rendering when the document closes", () => {
    const sources = [
      {
        type: "source-document" as const,
        documentId: "doc-1",
        documentName: "Guide",
        content: "Deferred segment",
      },
    ];

    find(render(sources), (node) => node.props["aria-expanded"] === false).props
      .onClick();
    find(
      render(sources),
      (node) =>
        node.type === "button" &&
        JSON.stringify(node.props.children).includes("Guide"),
    ).props.onClick();
    const selected = render(sources);

    expect(timers.size).toBe(1);
    expect(JSON.stringify(selected)).toContain("loadingSources");
    find(selected, (node) => node.props["aria-label"] === "close").props.onClick();
    render(sources);

    expect(clearedTimers).toEqual([1]);
    expect(timers).toHaveLength(0);
  });

  test("renders, expands, and batches grouped document segments", () => {
    const sources = Array.from({ length: 6 }, (_, index) => ({
      type: "source-document" as const,
      documentId: "doc-1",
      documentName: "Guide",
      content: index === 0 ? "A".repeat(4001) : `Segment ${index + 1}`,
      metadata: { score: 0.9, page: index + 1 },
    }));

    find(render(sources), (node) => node.props["aria-expanded"] === false).props
      .onClick();
    find(
      render(sources),
      (node) =>
        node.type === "button" &&
        JSON.stringify(node.props.children).includes("Guide"),
    ).props.onClick();
    render(sources);
    timers.get(1)?.();
    const selected = render(sources);

    expect(JSON.stringify(selected)).toContain("showMoreSegments:1");
    find(selected, (node) => node.props["aria-expanded"] === false).props.onClick();
    const openSegment = render(sources);
    expect(
      find(openSegment, (node) => node.props.children === "contentTruncated"),
    ).toBeDefined();
    expect(
      find(openSegment, (node) => node.props.children === "relevance"),
    ).toBeDefined();

    find(
      openSegment,
      (node) => node.props.children === "showMoreSegments:1",
    ).props.onClick();
    expect(JSON.stringify(render(sources))).toContain("Segment 6");
  });
});
