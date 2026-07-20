import { beforeEach, describe, expect, mock, test } from "bun:test";
import type { ReactNode } from "react";

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props });
const Button = ({ children }: { children: ReactNode }) => children;
const Loader2 = () => null;
const getDocumentChunks = mock(() => Promise.resolve({ items: [], total: 0 }));

let states: unknown[] = [];
let stateIndex = 0;
let callbacks: Array<{ deps: unknown[]; value: unknown }> = [];
let callbackIndex = 0;
let effects: unknown[][] = [];
let effectIndex = 0;

const changed = (previous: unknown[] | undefined, next: unknown[]) =>
  !previous || previous.some((value, index) => value !== next[index]);

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
  useState: <T,>(initial: T) => {
    const index = stateIndex++;
    states[index] ??= initial;
    return [
      states[index] as T,
      (value: T | ((previous: T) => T)) => {
        states[index] =
          typeof value === "function"
            ? (value as (previous: T) => T)(states[index] as T)
            : value;
      },
    ] as const;
  },
  useCallback: <T,>(value: T, deps: unknown[]) => {
    const index = callbackIndex++;
    if (!callbacks[index] || changed(callbacks[index].deps, deps)) {
      callbacks[index] = { deps, value };
    }
    return callbacks[index].value as T;
  },
  useEffect: (effect: () => void, deps: unknown[]) => {
    const index = effectIndex++;
    if (changed(effects[index], deps)) {
      effects[index] = deps;
      effect();
    }
  },
}));
mock.module("next-intl", () => ({
  useTranslations: () => (key: string, values?: Record<string, unknown>) =>
    values ? `${key}:${JSON.stringify(values)}` : key,
}));
mock.module("lucide-react", () => ({
  ChevronLeft: () => null,
  ChevronRight: () => null,
  Loader2,
}));
mock.module("@/lib/api", () => ({
  adminKnowledgeBasesApi: { getDocumentChunks },
}));
mock.module("@/components/ui/button", () => ({ Button }));
mock.module("@/components/ui/badge", () => ({
  Badge: ({ children }: { children: ReactNode }) => children,
}));
mock.module("@/components/ui/scroll-area", () => ({
  ScrollArea: ({ children }: { children: ReactNode }) => children,
}));
mock.module("@/components/ui/dialog", () => ({
  Dialog: ({ children }: { children: ReactNode }) => children,
  DialogContent: ({ children }: { children: ReactNode }) => children,
  DialogDescription: ({ children }: { children: ReactNode }) => children,
  DialogHeader: ({ children }: { children: ReactNode }) => children,
  DialogTitle: ({ children }: { children: ReactNode }) => children,
}));

const { DocumentChunksDialog } = await import("./document-chunks-dialog");

type Tree = { type: unknown; props: Record<string, unknown> };
const document = { id: "doc-1", name: "Guide", chunk_count: 21 } as never;
const baseProps = {
  open: true,
  onOpenChange: () => undefined,
  knowledgeBaseId: "kb-1",
  document,
};

function render(props = baseProps) {
  stateIndex = 0;
  callbackIndex = 0;
  effectIndex = 0;
  return DocumentChunksDialog(props) as Tree;
}

function findAll(node: ReactNode, predicate: (tree: Tree) => boolean): Tree[] {
  if (Array.isArray(node)) return node.flatMap((child) => findAll(child, predicate));
  if (!node || typeof node !== "object" || !("type" in node)) return [];
  const tree = node as Tree;
  return [
    ...(predicate(tree) ? [tree] : []),
    ...findAll(tree.props.children as ReactNode, predicate),
  ];
}

const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

beforeEach(() => {
  states = [];
  callbacks = [];
  effects = [];
  getDocumentChunks.mockReset();
  getDocumentChunks.mockResolvedValue({ items: [], total: 0 });
});

describe("DocumentChunksDialog", () => {
  test("loads only when open with a document and exposes the loading boundary", () => {
    let resolveRequest!: (value: { items: never[]; total: number }) => void;
    getDocumentChunks.mockImplementation(
      () => new Promise((resolve) => (resolveRequest = resolve)),
    );

    render({ ...baseProps, open: false });
    render({ ...baseProps, open: true, document: null });
    expect(getDocumentChunks).not.toHaveBeenCalled();

    render();
    const loading = render();

    expect(getDocumentChunks).toHaveBeenCalledWith("kb-1", "doc-1", {
      page: 1,
      pageSize: 10,
    });
    expect(findAll(loading, (node) => node.type === Loader2)).toHaveLength(1);
    resolveRequest({ items: [], total: 0 });
  });

  test("renders loaded chunk data and page metadata", async () => {
    getDocumentChunks.mockResolvedValue({
      items: [
        {
          id: "chunk-1",
          chunk_index: 2,
          token_count: 17,
          content: "Meaningful chunk content",
        },
      ],
      total: 21,
    });

    render();
    await flush();
    const tree = render();
    const content = JSON.stringify(tree);
    const buttons = findAll(tree, (node) => node.type === Button);

    expect(content).toContain("Guide");
    expect(content).toContain('"children":["#",3]');
    expect(content).toContain('"children":[17," tokens"]');
    expect(content).toContain("Meaningful chunk content");
    expect(content).toContain('pageInfo:{\\"page\\":1,\\"total\\":3}');
    expect(buttons.map((button) => button.props.disabled)).toEqual([true, false]);
  });

  test("loads the next page and keeps actions bounded", async () => {
    getDocumentChunks.mockResolvedValue({
      items: [{ id: "chunk-1", chunk_index: 0, token_count: 1, content: "x" }],
      total: 21,
    });
    render();
    await flush();
    let tree = render();
    let buttons = findAll(tree, (node) => node.type === Button);

    (buttons[1].props.onClick as () => void)();
    render();
    await flush();
    tree = render();
    buttons = findAll(tree, (node) => node.type === Button);

    expect(getDocumentChunks).toHaveBeenLastCalledWith("kb-1", "doc-1", {
      page: 2,
      pageSize: 10,
    });
    expect(buttons.map((button) => button.props.disabled)).toEqual([false, false]);
    (buttons[0].props.onClick as () => void)();
    expect(states[2]).toBe(1);
  });

  test("shows the empty state after an API error and resets data when closed", async () => {
    getDocumentChunks.mockRejectedValue(new Error("network"));
    render();
    await flush();
    expect(JSON.stringify(render())).toContain("noChunks");

    states[0] = [{ id: "stale", content: "stale" }];
    states[2] = 3;
    states[3] = { items: states[0], total: 21 };
    render({ ...baseProps, open: false });

    expect(states[0]).toEqual([]);
    expect(states[2]).toBe(1);
    expect(states[3]).toBeNull();
  });
});
