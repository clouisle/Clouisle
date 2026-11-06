import { expect, mock, test } from "bun:test";
import * as React from "react";
import { act, create, type ReactTestRenderer } from "react-test-renderer";

const replace = mock(() => {});
mock.module("next/navigation", () => ({
  useRouter: () => ({ replace }),
}));

const { default: NotificationsPage } = await import("./page");

test("redirects legacy notifications route to /app", () => {
  let renderer!: ReactTestRenderer;
  act(() => {
    renderer = create(<NotificationsPage />);
  });
  expect(renderer.toJSON()).toBeNull();
  expect(replace).toHaveBeenCalledWith("/app");
});
