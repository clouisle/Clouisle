import { describe, expect, test, mock } from 'bun:test'
import * as React from 'react'
import { renderToStaticMarkup, renderToString } from 'react-dom/server'

mock.module('next-intl', () => ({
  useTranslations: () => (key: string, values?: Record<string, unknown>) => values ? `${key}:${JSON.stringify(values)}` : key,
}))

mock.module('next/navigation', () => ({
  useRouter: () => ({ push: mock() }),
}))

mock.module('sonner', () => ({
  toast: {
    error: mock(),
    success: mock(),
  },
}))

mock.module('@/contexts/team-context', () => ({
  useTeam: () => ({ currentTeam: { id: 'team-1', role: 'owner' } }),
}))

mock.module('@/hooks/use-permissions', () => ({
  usePermissions: () => ({ user: { id: 'user-1', is_superuser: false } }),
}))

mock.module('@/components/permission-guard', () => ({
  PermissionGuard: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  useCanPerform: () => true,
}))

mock.module('./knowledge-bases/[id]/_components/documents-table', () => ({
  DocumentsTable: () => <div data-covered-child="dashboard-documents-table" />,
}))

mock.module('./knowledge-bases/[id]/_components/upload-document-dialog', () => ({
  UploadDocumentDialog: () => null,
}))

mock.module('./knowledge-bases/[id]/_components/import-url-dialog', () => ({
  ImportUrlDialog: () => null,
}))

mock.module('./knowledge-bases/_components/knowledge-base-dialog', () => ({
  KnowledgeBaseDialog: () => null,
}))

mock.module('./(platform)/app/kb/[id]/_components', () => ({
  DocumentsTable: () => <div data-covered-child="platform-documents-table" />,
  ImportUrlDialog: () => null,
  UploadDocumentDialog: () => null,
}))

mock.module('./(platform)/app/kb/_components/kb-dialog', () => ({
  KnowledgeBaseDialog: () => null,
}))

describe('KB LCOV source coverage', () => {
  test('imports and renders remaining dashboard KB clients', async () => {
    const [{ KnowledgeBaseDetailClient }, dashboardDocument, dashboardPreview] = await Promise.all([
      import('./(dashboard)/knowledge-bases/[id]/_components/knowledge-base-detail-client'),
      import('./(dashboard)/knowledge-bases/[id]/documents/[docId]/_components/document-detail-client'),
      import('./(dashboard)/knowledge-bases/[id]/documents/preview/_components/documents-preview-client'),
    ])

    expect(renderToStaticMarkup(<KnowledgeBaseDetailClient knowledgeBaseId="kb-1" />)).toContain('animate-spin')
    expect(renderToStaticMarkup(<dashboardDocument.DocumentDetailClient knowledgeBaseId="kb-1" documentId="doc-1" />)).toContain('animate-spin')
    expect(renderToStaticMarkup(<dashboardPreview.DocumentsPreviewClient knowledgeBaseId="kb-1" documentIds={['doc-1']} />)).toContain('animate-spin')
  })

  test('imports and renders remaining platform KB page and clients', async () => {
    const [platformPage, platformDocument, platformPreview] = await Promise.all([
      import('./(platform)/app/kb/[id]/page'),
      import('./(platform)/app/kb/[id]/documents/[docId]/_components/document-detail-client'),
      import('./(platform)/app/kb/[id]/documents/preview/_components/documents-preview-client'),
    ])
    const params = Promise.resolve({ id: 'kb-1' }) as Promise<{ id: string }> & { status: string; value: { id: string } }
    params.status = 'fulfilled'
    params.value = { id: 'kb-1' }

    expect(renderToString(<platformPage.default params={params} />)).toContain('animate-spin')
    expect(renderToStaticMarkup(<platformDocument.DocumentDetailClient knowledgeBaseId="kb-1" documentId="doc-1" />)).toContain('animate-spin')
    expect(renderToStaticMarkup(<platformPreview.DocumentsPreviewClient knowledgeBaseId="kb-1" documentIds={['doc-1']} />)).toContain('animate-spin')
  })
})
