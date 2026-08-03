import { beforeEach, describe, expect, mock, test } from "bun:test";
import type { ReactNode } from "react";

let state: unknown[] = [];
let stateIndex = 0;

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
  memo: <T,>(component: T) => component,
  useCallback: <T,>(callback: T) => callback,
  useEffect: (effect: () => void | (() => void)) => effect(),
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

Object.assign(globalThis, {
  window: {
    clearTimeout: () => undefined,
    setTimeout: (callback: () => void) => {
      callback();
      return 0;
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
        (tree.type as (props: Record<string, unknown>) => ReactNode)(
          tree.props,
        ),
      )
    : tree;
}

function find(node: ReactNode, predicate: (tree: Tree) => boolean): Tree {
  for (const child of Array.isArray(node) ? node : [node]) {
    if (Array.isArray(child)) {
      try {
        return find(child, predicate);
      } catch {
        // Continue searching sibling elements.
      }
      continue;
    }
    const tree = resolve(child);
    if (!tree || typeof tree !== "object" || !("type" in tree)) continue;
    if (predicate(tree as Tree)) return tree as Tree;
    try {
      return find((tree as Tree).props.children as ReactNode, predicate);
    } catch {
      // Continue searching sibling elements.
    }
  }
  throw new Error("Element not found");
}

function render(
  sources: React.ComponentProps<typeof SourceContent>["sources"],
  onOpenCodePreview?: React.ComponentProps<typeof SourceContent>["onOpenCodePreview"],
) {
  stateIndex = 0;
  return SourceContent({ sources, onOpenCodePreview });
}

beforeEach(() => {
  state = [];
});

describe("SourceContent", () => {
  test("renders nothing when source data is unavailable", () => {
    expect(render([])).toBeNull();
  });

  test("falls back to a malformed URL when rendering source data", () => {
    const tree = render([{ type: "source-url", url: "not a valid URL" }]);
    const toggle = find(tree, (node) => node.props["aria-expanded"] === false);
    toggle.props.onClick();
    const expanded = render([{ type: "source-url", url: "not a valid URL" }]);

    expect(find(expanded, (node) => node.type === "a").props.href).toBe(
      "not a valid URL",
    );
    expect(
      find(
        expanded,
        (node) =>
          node.type === "span" && node.props.children === "not a valid URL",
      ),
    ).toBeDefined();
  });

  test("opens preview with document segments when a document is selected", () => {
    const onOpenCodePreview = mock(() => {});
    const sources = Array.from({ length: 6 }, (_, index) => ({
      type: "source-document" as const,
      documentId: "doc-1",
      documentName: "Guide",
      content: index === 0 ? "A".repeat(4001) : `Source segment ${index + 1}`,
      metadata: { score: 0.9, page: index + 1 },
    }));
    const tree = render(sources, onOpenCodePreview);
    find(tree, (node) => node.props["aria-expanded"] === false).props.onClick();
    const expanded = render(sources, onOpenCodePreview);
    find(
      expanded,
      (node) =>
        node.type === "button" &&
        JSON.stringify(node.props.children).includes("Guide"),
    ).props.onClick();

    expect(onOpenCodePreview).toHaveBeenCalledTimes(1);
    const payload = onOpenCodePreview.mock.calls[0][0] as {
      segments: { content: string }[];
    };
    expect(payload).toMatchObject({
      id: "source-document:doc-1",
      kind: "source-document",
      documentId: "doc-1",
      documentName: "Guide",
    });
    expect(payload.segments).toHaveLength(6);
    expect(payload.segments[0].content).toBe("A".repeat(4001));
  });

  test("shows more than the initial source batch", () => {
    const sources = Array.from({ length: 21 }, (_, index) => ({
      type: "source-url" as const,
      url: `https://example.com/${index}`,
    }));
    const tree = render(sources);
    find(tree, (node) => node.props["aria-expanded"] === false).props.onClick();
    const expanded = render(sources);

    find(
      expanded,
      (node) =>
        node.type === "button" && node.props.children === "showMoreSources:1",
    ).props.onClick();
    const allSources = render(sources);

    expect(JSON.stringify(allSources)).toContain("https://example.com/20");
  });

  test("uses source titles and default document names", () => {
    const sources = [
      {
        type: "source-url" as const,
        url: "https://example.com",
        title: "Example",
      },
      { type: "source-document" as const, content: "Segment" },
    ];
    const tree = render(sources);
    find(tree, (node) => node.props["aria-expanded"] === false).props.onClick();
    const expanded = render(sources);

    expect(JSON.stringify(expanded)).toContain("Example");
    expect(JSON.stringify(expanded)).toContain("document");
  });
});
