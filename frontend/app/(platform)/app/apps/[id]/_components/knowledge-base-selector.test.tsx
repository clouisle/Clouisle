import { beforeEach, describe, expect, mock, test } from "bun:test";
import type { ReactNode } from "react";
import type { AgentKnowledgeBaseConfig, KnowledgeBase } from "@/lib/api";

let state: unknown[] = [];
let stateIndex = 0;
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
  useEffect: (effect: () => void) => effect(),
  useMemo: <T,>(factory: () => T) => factory(),
  useState: <T,>(initial: T) => {
    const index = stateIndex++;
    state[index] ??= initial;
    return [
      state[index] as T,
      (value: T | ((current: T) => T)) => {
        state[index] =
          typeof value === "function"
            ? (value as (current: T) => T)(state[index] as T)
            : value;
      },
    ] as const;
  },
}));
mock.module("next-intl", () => ({
  useTranslations: () => (key: string) => key,
}));
mock.module("lucide-react", () => ({
  Database: () => null,
  Plus: () => null,
  Settings2: () => null,
  Trash2: () => null,
}));

for (const [module, names] of [
  ["@/components/ui/button", ["Button"]],
  ["@/components/ui/badge", ["Badge"]],
  ["@/components/ui/label", ["Label"]],
  ["@/components/ui/slider", ["Slider"]],
  [
    "@/components/ui/select",
    ["Select", "SelectContent", "SelectItem", "SelectTrigger", "SelectValue"],
  ],
  [
    "@/components/ui/dialog",
    ["Dialog", "DialogContent", "DialogHeader", "DialogTitle", "DialogFooter"],
  ],
  ["@/components/ui/popover", ["Popover", "PopoverContent", "PopoverTrigger"]],
] as const) {
  mock.module(module, () =>
    Object.fromEntries(
      names.map((name) => [
        name,
        (props: Record<string, unknown>) => jsx(name, props),
      ]),
    ),
  );
}

const { AddKnowledgeBaseButton, KnowledgeBaseSelector } = await import(
  "./knowledge-base-selector"
);

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

function findAll(node: ReactNode, predicate: (tree: Tree) => boolean): Tree[] {
  const matches: Tree[] = [];
  for (const child of Array.isArray(node) ? node : [node]) {
    const tree = resolve(child);
    if (Array.isArray(tree)) {
      matches.push(...findAll(tree, predicate));
      continue;
    }
    if (!tree || typeof tree !== "object" || !("type" in tree)) continue;
    if (predicate(tree as Tree)) matches.push(tree as Tree);
    matches.push(
      ...findAll((tree as Tree).props.children as ReactNode, predicate),
    );
  }
  return matches;
}

function render<T>(component: () => T) {
  stateIndex = 0;
  return component();
}

const knowledgeBases = [
  { id: "kb-1", name: "Selected", document_count: 2, total_chunks: 10 },
  { id: "kb-2", name: "Available", document_count: 3, total_chunks: 20 },
] as unknown as KnowledgeBase[];

const configs: AgentKnowledgeBaseConfig[] = [
  {
    knowledge_base_id: "kb-1",
    retrieval_top_k: 5,
    score_threshold: 0.3,
    search_mode: "hybrid",
  },
  {
    knowledge_base_id: "missing",
    retrieval_top_k: 4,
    score_threshold: 0.2,
    search_mode: "vector",
  },
];

beforeEach(() => {
  state = [];
  stateIndex = 0;
});

describe("knowledge base selector", () => {
  test("offers only unselected knowledge bases and closes after selection", () => {
    const added: KnowledgeBase[] = [];
    const component = () =>
      AddKnowledgeBaseButton({
        knowledgeBases,
        selectedIds: ["kb-1"],
        onAdd: (kb) => added.push(kb),
      });

    let tree = render(component);
    const popover = findAll(tree, (node) => node.type === "Popover")[0];
    popover.props.onOpenChange(true);
    tree = render(component);
    expect(findAll(tree, (node) => node.type === "Popover")[0].props.open).toBe(
      true,
    );
    expect(JSON.stringify(tree)).not.toContain("Selected");

    findAll(tree, (node) => node.type === "button")[0].props.onClick();
    tree = render(component);

    expect(added).toEqual([knowledgeBases[1]]);
    expect(findAll(tree, (node) => node.type === "Popover")[0].props.open).toBe(
      false,
    );
  });

  test("disables adding when every knowledge base is selected", () => {
    const tree = render(() =>
      AddKnowledgeBaseButton({
        knowledgeBases,
        selectedIds: ["kb-1", "kb-2"],
        onAdd: () => undefined,
      }),
    );

    expect(findAll(tree, (node) => node.type === "Button")[0].props.disabled).toBe(
      true,
    );
    expect(findAll(tree, (node) => node.type === "Popover")).toHaveLength(0);
  });

  test("ignores stale configs and forwards delete and configuration changes", () => {
    const changes: AgentKnowledgeBaseConfig[][] = [];
    const component = () =>
      KnowledgeBaseSelector({
        configs,
        availableKnowledgeBases: knowledgeBases,
        onChange: (next) => changes.push(next),
      });

    let tree = render(component);
    expect(JSON.stringify(tree)).toContain("Selected");
    expect(JSON.stringify(tree)).not.toContain("missing");

    const iconButtons = findAll(
      tree,
      (node) => node.type === "Button" && node.props.size === "icon",
    );
    iconButtons[1].props.onClick({ stopPropagation: () => undefined });
    expect(changes[0]).toEqual([configs[1]]);

    iconButtons[0].props.onClick({ stopPropagation: () => undefined });
    tree = render(component);
    const controls = findAll(
      tree,
      (node) => node.type === "Select" || node.type === "Slider",
    );
    controls[0].props.onValueChange("fulltext");
    controls[1].props.onValueChange([8]);
    controls[2].props.onValueChange(0.6);
    tree = render(component);
    const save = findAll(
      tree,
      (node) => node.type === "Button" && node.props.children === "dialog.save",
    )[0];
    save.props.onClick();

    expect(changes[1][0]).toEqual({
      ...configs[0],
      retrieval_top_k: 8,
      score_threshold: 0.6,
      search_mode: "fulltext",
    });
    expect(changes[1][1]).toEqual(configs[1]);
  });
});
