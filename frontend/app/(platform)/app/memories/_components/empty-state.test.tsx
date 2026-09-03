import { expect, mock, test } from "bun:test";
import React from "react";
import { act, create } from "@/test-utils/rtl-renderer";

const push = mock();

mock.module("next/navigation", () => ({ useRouter: () => ({ push }) }));
mock.module("next-intl", () => ({
  useTranslations: () => (key: string) => key,
}));
mock.module("lucide-react", () => ({ Brain: () => null }));
mock.module("@/components/ui/button", () => ({
  Button: ({
    children,
    ...props
  }: React.ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button {...props}>{children}</button>
  ),
}));

const { EmptyState } = await import("./empty-state");

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

test("routes a memory user to start a conversation", () => {
  let renderer: ReturnType<typeof create>;
  act(() => {
    renderer = create(<EmptyState />);
  });

  expect(renderer!.root.findByType("h3").children.join("")).toBe("noMemories");
  act(() => {
    renderer!.root.findByType("button").props.onClick();
  });
  expect(push).toHaveBeenCalledWith("/app");
  act(() => renderer!.unmount());
});
