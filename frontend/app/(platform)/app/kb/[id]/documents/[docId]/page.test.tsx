import { expect, mock, test } from "bun:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

mock.module("./_components/document-detail-client", () => ({
  DocumentDetailClient: ({ knowledgeBaseId, documentId }: { knowledgeBaseId: string; documentId: string }) => (
    <div data-kb={knowledgeBaseId} data-document={documentId} />
  ),
}));

const { default: DocumentDetailPage } = await import("./page");

test("passes both route IDs to document details", async () => {
  const page = await DocumentDetailPage({
    params: Promise.resolve({ id: "kb-1", docId: "doc-1" }),
  });
  const html = renderToStaticMarkup(page);

  expect(html).toContain('data-kb="kb-1"');
  expect(html).toContain('data-document="doc-1"');
});
