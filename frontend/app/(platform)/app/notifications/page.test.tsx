import { expect, mock, test } from "bun:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

mock.module("./_components/notifications-client", () => ({
  NotificationsClient: () => <div data-testid="notifications-client" />,
}));

const { default: NotificationsPage } = await import("./page");

test("provides the scrollable inbox container", () => {
  const html = renderToStaticMarkup(<NotificationsPage />);

  expect(html).toContain("height:calc(100vh - 64px)");
  expect(html).toContain('data-testid="notifications-client"');
});
