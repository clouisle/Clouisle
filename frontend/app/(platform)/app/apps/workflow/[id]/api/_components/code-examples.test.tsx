import { afterEach, expect, mock, test } from "bun:test";
import React from "react";
import { act, create, type ReactTestRenderer } from "@/test-utils/rtl-renderer";

const writeText = mock(() => Promise.resolve());
Object.assign(globalThis, { navigator: { clipboard: { writeText } } });

mock.module("next-intl", () => ({
  useTranslations: () => (key: string) => key,
}));
mock.module("@/components/ui/card", () => ({
  Card: ({ children, ...props }: React.ComponentProps<"section">) => <section {...props}>{children}</section>,
  CardContent: ({ children, ...props }: React.ComponentProps<"div">) => <div {...props}>{children}</div>,
  CardHeader: ({ children, ...props }: React.ComponentProps<"header">) => <header {...props}>{children}</header>,
  CardTitle: ({ children, ...props }: React.ComponentProps<"h2">) => <h2 {...props}>{children}</h2>,
}));
mock.module("@/components/ui/button", () => ({
  Button: ({ children, ...props }: React.ComponentProps<"button">) => <button {...props}>{children}</button>,
}));

const { CodeExamples } = await import("./code-examples");

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
let renderer: ReactTestRenderer | undefined;

afterEach(() => {
  if (renderer) act(() => renderer!.unmount());
  renderer = undefined;
  writeText.mockClear();
});

function renderedText(view: ReactTestRenderer) {
  return view.root.findAll(() => true).flatMap((node) => node.children).filter((child) => typeof child === "string").join(" ");
}

test("builds request examples for workflow variable types", () => {
  act(() => {
    renderer = create(<CodeExamples webhookUrl="https://example.test/run" variables={[
      { name: "text", type: "text" },
      { name: "count", type: "number" },
      { name: "enabled", type: "boolean" },
      { name: "items", type: "array" },
      { name: "metadata", type: "object" },
      { name: "other", type: "select" },
    ] as never} />);
  });

  const output = renderedText(renderer!);
  expect(output).toContain("https://example.test/run");
  expect(output).toContain('"count": 42');
  expect(output).toContain('"enabled": true');
  expect(output).toContain('"item1"');
  expect(output).toContain('"key": "value"');
  expect(output).toContain('"other": "value"');
});

test("expands examples and copies their generated code", async () => {
  const originalSetTimeout = globalThis.setTimeout
  let timeoutCallback: (() => void) | undefined
  globalThis.setTimeout = ((callback: () => void) => { timeoutCallback = callback; return 1 }) as unknown as typeof globalThis.setTimeout
  try {
    act(() => {
      renderer = create(<CodeExamples webhookUrl="https://example.test/run" variables={[]} />);
    })
    const headers = renderer!.root.findAllByType("header")

    act(() => headers[1].props.onClick())
    expect(renderedText(renderer!)).toContain("import requests")

    const copyButton = headers[1].findByType("button")
    await act(async () => copyButton.props.onClick({ stopPropagation: mock(() => {}) }))

    expect(writeText).toHaveBeenCalledWith(expect.stringContaining("import requests"))
    expect(renderedText(renderer!)).toContain("copied")
    act(() => timeoutCallback!())
  } finally {
    globalThis.setTimeout = originalSetTimeout
  }
})
