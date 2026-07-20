import { afterEach, expect, mock, test } from "bun:test";
import React from "react";
import { act, create, type ReactTestRenderer } from "react-test-renderer";

const writeText = mock(() => Promise.resolve());
Object.assign(globalThis, { navigator: { clipboard: { writeText } } });

mock.module("next-intl", () => ({ useTranslations: () => (key: string) => key }));
mock.module("next/link", () => ({ default: ({ children, ...props }: React.ComponentProps<"a">) => <a {...props}>{children}</a> }));
mock.module("@/components/ui/button", () => ({ Button: ({ children, ...props }: React.ComponentProps<"button">) => <button {...props}>{children}</button> }));
mock.module("@/components/ui/badge", () => ({ Badge: ({ children, ...props }: React.ComponentProps<"span">) => <span {...props}>{children}</span> }));
mock.module("@/components/ui/card", () => ({
  Card: ({ children }: { children: React.ReactNode }) => <section>{children}</section>,
  CardContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  CardDescription: ({ children }: { children: React.ReactNode }) => <p>{children}</p>,
  CardHeader: ({ children }: { children: React.ReactNode }) => <header>{children}</header>,
  CardTitle: ({ children }: { children: React.ReactNode }) => <h2>{children}</h2>,
}));
mock.module("@/components/ui/alert", () => ({
  Alert: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDescription: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));
mock.module("@/components/ui/table", () => Object.fromEntries(
  ["Table", "TableBody", "TableCell", "TableHead", "TableHeader", "TableRow"].map((name) => [name, ({ children }: { children: React.ReactNode }) => <div data-table={name}>{children}</div>]),
));

const { ApiOverview } = await import("./api-overview");

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
let renderer: ReactTestRenderer | undefined;
afterEach(() => {
  if (renderer) act(() => renderer!.unmount());
  renderer = undefined;
  writeText.mockClear();
});

function text(view: ReactTestRenderer) {
  return view.root.findAll(() => true).flatMap((node) => node.children).filter((child) => typeof child === "string").join(" ");
}

const workflow = {
  webhook_token: "token",
  variables: [
    { name: "query", type: "text", required: true, description: "Question" },
    { name: "limit", type: "number", required: false },
  ],
};

test("shows the unconfigured state without a webhook token", () => {
  act(() => { renderer = create(<ApiOverview workflow={{ ...workflow, webhook_token: null } as never} webhookUrl="" />); });
  expect(text(renderer!)).toContain("webhookNotConfigured");
  expect(writeText).not.toHaveBeenCalled();
});

test("renders webhook documentation and copies the URL", async () => {
  act(() => { renderer = create(<ApiOverview workflow={workflow as never} webhookUrl="https://example.test/hook" />); });
  const output = text(renderer!);

  expect(output).toContain("https://example.test/hook");
  expect(output).toContain("query");
  expect(output).toContain("required");
  expect(output).toContain("optional");
  expect(output).toContain("workflow_error");

  await act(async () => renderer!.root.findAllByType("button")[0].props.onClick());
  expect(writeText).toHaveBeenCalledWith("https://example.test/hook");
});
