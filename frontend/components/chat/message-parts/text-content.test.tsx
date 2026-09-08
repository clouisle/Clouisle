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
mock.module("@/components/ui/tooltip", () => ({
  Tooltip: (props: Record<string, unknown>) => jsx("tooltip", props),
  TooltipTrigger: ({ render, children, ...props }: Record<string, unknown>) => {
    const element = render as { type?: unknown; props?: Record<string, unknown> } | undefined;
    return element
      ? { type: element.type, props: { ...element.props, ...props, ...(children !== undefined ? { children } : {}) } }
      : jsx("span", { ...props, children });
  },
  TooltipContent: (props: Record<string, unknown>) => jsx("tooltip-content", props),
}));

const { TextContent, TextContentComponent } = await import("./text-content");
const RenderTextContent = (TextContentComponent || (typeof TextContent === 'function' ? TextContent : (TextContent as unknown as { type: (props: unknown) => unknown }).type)) as unknown as typeof TextContent;


function streamdownProps(
  part: React.ComponentProps<typeof TextContent>["part"],
) {
  const tree = RenderTextContent({ part }) as Tree;
  return (tree.props.children as Tree[])[0].props;
}

describe("TextContent", () => {
  test("passes raw markdown directly to Streamdown without citation replacement", () => {
    const props = streamdownProps({
      type: "text",
      text: "One [[ref:1]], [ref:2], (ref:3), and [[cite:4]].",
    });

    expect(props.children).toBe(
      "One [[ref:1]], [ref:2], (ref:3), and [[cite:4]].",
    );
  });

  test("uses block paragraphs for image nodes and shows the streaming cursor", () => {
    const tree = RenderTextContent({
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
