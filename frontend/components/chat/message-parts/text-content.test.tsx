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
  Children: {
    toArray: (children: ReactNode) =>
      Array.isArray(children) ? children : [children],
  },
  isValidElement: (element: unknown) =>
    Boolean(element && typeof element === "object" && "type" in element),
  memo: <T,>(component: T) => component,
  useCallback: <T,>(callback: T) => callback,
  useMemo: <T,>(factory: () => T) => factory(),
}));
mock.module("next-intl", () => ({
  useTranslations: () => (key: string) => key,
}));
mock.module("streamdown", () => ({ Streamdown: () => null }));

const { TextContent } = await import("./text-content");

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

function streamdownProps(
  part: React.ComponentProps<typeof TextContent>["part"],
) {
  const tree = TextContent({ part }) as Tree;
  return (tree.props.children as Tree[])[0].props;
}

describe("TextContent", () => {
  test("normalizes citation formats before sending markdown to Streamdown", () => {
    const props = streamdownProps({
      type: "text",
      text: "One [[ref:1]], [ref:2], (ref:3), and [[cite:4]].",
    });

    expect(props.children).toBe(
      "One <cite-1>, <cite-2>, <cite-3>, and <cite-4>.",
    );
  });

  test("renders citation badges with source metadata and forwards clicks", () => {
    const clicked: number[] = [];
    const tree = TextContent({
      part: { type: "text", text: "Answer [[cite:1]]" },
      sources: [
        { type: "source-document", documentName: "Guide", content: "Source" },
      ],
      onCitationClick: (index) => clicked.push(index),
    }) as Tree;
    const streamdown = (tree.props.children as Tree[])[0];
    const paragraph = streamdown.props.components.p as (
      props: Record<string, unknown>,
    ) => ReactNode;
    const rendered = paragraph({
      children: "Answer <cite-1>",
      node: { children: [] },
    }) as Tree;
    const fragment = resolve(rendered.props.children) as Tree;
    const badge = resolve((fragment.props.children as ReactNode[])[1]) as Tree;

    expect(badge).toMatchObject({
      type: "button",
      props: { title: "Guide", children: 1 },
    });
    badge.props.onClick();
    expect(clicked).toEqual([1]);
  });

  test("uses block paragraphs for image nodes and shows the streaming cursor", () => {
    const tree = TextContent({
      part: { type: "text", text: "![image](url)", state: "streaming" },
    }) as Tree;
    const children = tree.props.children as Tree[];
    const components = children[0].props.components as Record<
      string,
      (props: Record<string, unknown>) => ReactNode
    >;
    const rendered = components.p({
      children: "image",
      node: { children: [{ type: "element", tagName: "img" }] },
    }) as Tree;
    const listItem = components.li({ children: "plain text" }) as Tree;

    expect(rendered.type).toBe("div");
    expect(listItem.type).toBe("li");
    expect(children[1].props.className).toContain("animate-blink");
  });
});
