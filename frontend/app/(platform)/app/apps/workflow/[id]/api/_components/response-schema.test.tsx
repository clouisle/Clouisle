import { afterEach, expect, mock, test } from "bun:test";
import React from "react";
import { act, create, type ReactTestRenderer } from "react-test-renderer";

mock.module("next-intl", () => ({ useTranslations: () => (key: string) => key }));
mock.module("@/components/ui/badge", () => ({ Badge: ({ children, ...props }: React.ComponentProps<"span">) => <span {...props}>{children}</span> }));
mock.module("@/components/ui/card", () => ({
  Card: ({ children }: { children: React.ReactNode }) => <section>{children}</section>,
  CardContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  CardDescription: ({ children }: { children: React.ReactNode }) => <p>{children}</p>,
  CardHeader: ({ children }: { children: React.ReactNode }) => <header>{children}</header>,
  CardTitle: ({ children }: { children: React.ReactNode }) => <h2>{children}</h2>,
}));
mock.module("@/components/ui/table", () => Object.fromEntries(
  ["Table", "TableBody", "TableCell", "TableHead", "TableHeader", "TableRow"].map((name) => [name, ({ children }: { children: React.ReactNode }) => <div data-table={name}>{children}</div>]),
));

const { ResponseSchema } = await import("./response-schema");
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
let renderer: ReactTestRenderer | undefined;
afterEach(() => {
  if (renderer) act(() => renderer!.unmount());
  renderer = undefined;
});

function text(view: ReactTestRenderer) {
  return view.root.findAll(() => true).flatMap((node) => node.children).filter((child) => typeof child === "string").join(" ");
}

test("documents successful and failed workflow API responses", () => {
  act(() => { renderer = create(<ResponseSchema />); });
  const output = text(renderer!);

  expect(output).toContain("workflow_triggered");
  expect(output).toContain("invalid_webhook_token");
  expect(output).toContain("workflow_not_published");
  expect(output).toContain("webhook_trigger_disabled");
  expect(output).toContain("workflow_execution_error");
  expect(output).toContain("data.stream_url");
  expect(output).toContain("200");
  expect(output).toContain("403");
  expect(output).toContain("500");
});
