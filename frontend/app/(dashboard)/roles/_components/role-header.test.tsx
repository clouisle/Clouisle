import { expect, mock, test } from "bun:test";
import React from "react";
import { act, create } from "react-test-renderer";

const onCreateClick = mock();

mock.module("next-intl", () => ({
  useTranslations: () => (key: string) => key,
}));
mock.module("lucide-react", () => ({ Plus: () => null }));
mock.module("@/components/ui/button", () => ({
  Button: ({
    children,
    ...props
  }: React.ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button {...props}>{children}</button>
  ),
}));

const { RoleHeader } = await import("./role-header");

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

test("starts role creation from the roles header action", () => {
  let renderer: ReturnType<typeof create>;
  act(() => {
    renderer = create(<RoleHeader onCreateClick={onCreateClick} />);
  });

  act(() => renderer!.root.findByType("button").props.onClick());

  expect(onCreateClick).toHaveBeenCalledTimes(1);
  expect(renderer!.root.findByType("h1").children).toEqual(["title"]);
  act(() => renderer!.unmount());
});
