import { expect, mock, test } from "bun:test";
import React from "react";
import { act, create, type ReactTestRenderer } from "@/test-utils/rtl-renderer";

let theme = "auto";

mock.module("next/navigation", () => ({
  useSearchParams: () => ({ get: () => theme }),
}));
mock.module("next-themes", () => ({
  ThemeProvider: ({
    children,
    ...props
  }: React.PropsWithChildren<Record<string, unknown>>) => (
    <div data-theme={JSON.stringify(props)}>{children}</div>
  ),
}));

const { default: EmbedLayout } = await import("./layout");

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const render = () => {
  let renderer: ReactTestRenderer;
  act(() => {
    renderer = create(<EmbedLayout>content</EmbedLayout>);
  });
  return renderer!;
};

const themeProps = (renderer: ReactTestRenderer) =>
  JSON.parse(
    renderer.root
      .findAllByType("div")
      .find((node) => typeof node.props["data-theme"] === "string")!.props[
      "data-theme"
    ],
  );

test("forces a supported embed theme from the URL", () => {
  theme = "dark";
  const renderer = render();

  expect(themeProps(renderer)).toMatchObject({
    defaultTheme: "dark",
    forcedTheme: "dark",
    enableSystem: false,
  });
  act(() => renderer.unmount());
});

test("uses the system theme for unsupported URL values", () => {
  theme = "sepia";
  const renderer = render();

  expect(themeProps(renderer)).toMatchObject({
    defaultTheme: "system",
    enableSystem: true,
  });
  act(() => renderer.unmount());
});
