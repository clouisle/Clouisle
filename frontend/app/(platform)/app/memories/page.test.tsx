import { expect, mock, test } from "bun:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

mock.module("./_components/memory-graph-canvas", () => ({
  MemoryGraphCanvas: () => <div data-testid="memory-graph" />,
}));

const { default: MemoriesPage } = await import("./page");

test("provides the full-height memory graph container", () => {
  const html = renderToStaticMarkup(<MemoriesPage />);

  expect(html).toContain('class="flex h-full flex-col"');
  expect(html).toContain('data-testid="memory-graph"');
});
