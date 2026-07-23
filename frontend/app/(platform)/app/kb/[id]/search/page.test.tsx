import { expect, mock, test } from "bun:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

mock.module("./_components/search-test-client", () => ({
  SearchTestClient: ({ knowledgeBaseId }: { knowledgeBaseId: string }) => <div data-kb={knowledgeBaseId} />,
}));

const { default: SearchTestPage } = await import("./page");

test("passes the route knowledge-base ID to search", async () => {
  const page = await SearchTestPage({ params: Promise.resolve({ id: "kb-1" }) });

  expect(renderToStaticMarkup(page)).toContain('data-kb="kb-1"');
});
