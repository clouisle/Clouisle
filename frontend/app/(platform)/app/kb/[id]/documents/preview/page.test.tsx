import { expect, mock, test } from "bun:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

mock.module("./_components/documents-preview-client", () => ({
  DocumentsPreviewClient: ({ knowledgeBaseId, documentIds }: { knowledgeBaseId: string; documentIds: string[] }) => (
    <div data-kb={knowledgeBaseId} data-documents={documentIds.join("|")} />
  ),
}));

const { default: DocumentsPreviewPage } = await import("./page");

test("passes parsed document IDs to the preview", async () => {
  const page = await DocumentsPreviewPage({
    params: Promise.resolve({ id: "kb-1" }),
    searchParams: Promise.resolve({ docs: "doc-1,doc-2" }),
  });
  const html = renderToStaticMarkup(page);

  expect(html).toContain('data-kb="kb-1"');
  expect(html).toContain('data-documents="doc-1|doc-2"');
});
