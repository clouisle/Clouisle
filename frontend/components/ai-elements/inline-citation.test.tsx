import { expect, mock, test } from "bun:test";

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props });
const Button = () => null;

mock.module("react/jsx-runtime", () => ({
  jsx,
  jsxs: jsx,
  Fragment: Symbol.for("react.fragment"),
}));
mock.module("react/jsx-dev-runtime", () => ({
  jsxDEV: jsx,
  Fragment: Symbol.for("react.fragment"),
}));
mock.module("lucide-react", () => ({ ChevronLeft: "left", ChevronRight: "right" }));
mock.module("@/components/ui/badge", () => ({ Badge: () => null }));
mock.module("@/components/ui/button", () => ({ Button }));
mock.module("@/components/ui/carousel", () => ({
  Carousel: () => null,
  CarouselContent: () => null,
  CarouselItem: () => null,
}));
mock.module("@/components/ui/hover-card", () => ({
  HoverCard: () => null,
  HoverCardContent: () => null,
  HoverCardTrigger: () => null,
}));

const { InlineCitationCardTrigger, InlineCitationSource } = await import(
  "./inline-citation"
);

type ElementNode = { type: unknown; props: Record<string, unknown> };

function findElement(
  node: unknown,
  predicate: (element: ElementNode) => boolean,
): ElementNode | undefined {
  if (!node || typeof node !== "object") return undefined;
  const element = node as ElementNode;
  if (predicate(element)) return element;

  const children = element.props?.children;
  if (Array.isArray(children)) {
    for (const child of children) {
      const match = findElement(child, predicate);
      if (match) return match;
    }
  } else {
    return findElement(children, predicate);
  }
}

test("citation trigger remains a delayed, keyboard-focusable button", () => {
  const trigger = InlineCitationCardTrigger({
    sources: ["https://docs.example.org/page"],
    label: "[1]",
    className: "citation-custom",
    "aria-label": "Documentation",
  }) as ElementNode;
  const button = trigger.props.render as ElementNode;

  expect(trigger.props.delay).toBe(10);
  expect(trigger.props.closeDelay).toBe(100);
  expect(trigger.props.children).toBe("[1]");
  expect(button.type).toBe(Button);
  expect(button.props.variant).toBe("secondary");
  expect(button.props.size).toBe("xs");
  expect(button.props.className).toBe("ml-1 rounded-full citation-custom");
  expect(button.props["aria-label"]).toBe("Documentation");
});

test("citation trigger keeps hostname labels and source counts", () => {
  const single = InlineCitationCardTrigger({
    sources: ["https://docs.example.org/page"],
  }) as ElementNode;
  const multiple = InlineCitationCardTrigger({
    sources: ["https://docs.example.org/page", "https://other.example.org"],
  }) as ElementNode;
  const unavailable = InlineCitationCardTrigger({ sources: [] }) as ElementNode;

  expect(single.props.children).toBe("docs.example.org");
  expect(multiple.props.children).toBe("docs.example.org +1");
  expect(unavailable.props.children).toBe("unknown");
});

test("citation source links open externally and retain accessible context", () => {
  const source = InlineCitationSource({
    title: "Documentation",
    url: "https://docs.example.org/page",
    description: "A short source summary.",
  }) as ElementNode;
  const link = findElement(source, (element) => element.type === "a");
  const newTabHint = findElement(
    source,
    (element) => element.type === "span" && element.props.className === "sr-only",
  );

  expect(link?.props.href).toBe("https://docs.example.org/page");
  expect(link?.props.target).toBe("_blank");
  expect(link?.props.rel).toBe("noreferrer");
  expect(newTabHint?.props.children).toBe(" (opens in a new tab)");
});
