import { expect, mock, test } from "bun:test";
import React from "react";
import { act, create, type ReactTestRenderer } from "@/test-utils/rtl-renderer";

let pathname = "/missing";
const back = mock();

mock.module("next/navigation", () => ({ usePathname: () => pathname }));
mock.module("next-intl", () => ({ useTranslations: () => (key: string) => key }));
mock.module("next/link", () => ({
  default: ({ children, href }: React.PropsWithChildren<{ href: string }>) => <a href={href}>{children}</a>,
}));
mock.module("@/components/ui/button", () => ({
  Button: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button {...props}>{children}</button>
  ),
}));
mock.module("lucide-react", () => ({ Home: () => null, ArrowLeft: () => null }));

Object.assign(globalThis, {
  document: { referrer: "" },
  window: { history: { back }, location: { host: "clouisle.test" } },
});

const { default: NotFound } = await import("./not-found");

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

async function renderPage() {
  let renderer: ReactTestRenderer;
  await act(async () => {
    renderer = create(<NotFound />);
  });
  return renderer!;
}

test("returns dashboard users to the dashboard", async () => {
  pathname = "/dashboard/missing";
  const renderer = await renderPage();

  expect(renderer.root.findByType("a").props.href).toBe("/dashboard");
  expect(renderer.root.findAllByType("p").map((node) => node.children.join(""))).toContain("backToDashboard");
  act(() => renderer.unmount());
});

test("offers workspace fallback and browser back navigation", async () => {
  pathname = "/missing";
  const renderer = await renderPage();

  expect(renderer.root.findByType("a").props.href).toBe("/app");
  act(() => renderer.root.findAllByType("button")[0]!.props.onClick());
  expect(back).toHaveBeenCalledTimes(1);
  act(() => renderer.unmount());
});
