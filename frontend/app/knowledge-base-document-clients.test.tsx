import { describe, expect, test } from 'bun:test'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
const root = import.meta.dir

function source(path: string) {
  return readFileSync(join(root, path), 'utf8')
}

describe('knowledge-base document clients', () => {
  test('exports dashboard and platform client components', () => {
    const files = [
      source('(dashboard)/knowledge-bases/[id]/documents/[docId]/_components/document-detail-client.tsx'),
      source('(dashboard)/knowledge-bases/[id]/documents/preview/_components/documents-preview-client.tsx'),
      source('(platform)/app/kb/[id]/documents/[docId]/_components/document-detail-client.tsx'),
      source('(platform)/app/kb/[id]/documents/preview/_components/documents-preview-client.tsx'),
    ]

    expect(files[0]).toContain('export function DocumentDetailClient')
    expect(files[1]).toContain('export function DocumentsPreviewClient')
    expect(files[2]).toContain('export function DocumentDetailClient')
    expect(files[3]).toContain('export function DocumentsPreviewClient')
  })

  test('keeps dashboard document clients on admin API and dashboard routes', () => {
    const detail = source('(dashboard)/knowledge-bases/[id]/documents/[docId]/_components/document-detail-client.tsx')
    const preview = source('(dashboard)/knowledge-bases/[id]/documents/preview/_components/documents-preview-client.tsx')

    expect(detail).toContain('adminKnowledgeBasesApi')
    expect(detail).toContain('/knowledge-bases/${knowledgeBaseId}/documents/preview?docs=${documentId}')
    expect(preview).toContain('adminKnowledgeBasesApi')
    expect(preview).toContain('/knowledge-bases/${knowledgeBaseId}')
    expect(`${detail}\n${preview}`).not.toContain('/app/kb/${knowledgeBaseId}')
  })

  test('keeps platform document clients on user API and platform routes', () => {
    const detail = source('(platform)/app/kb/[id]/documents/[docId]/_components/document-detail-client.tsx')
    const preview = source('(platform)/app/kb/[id]/documents/preview/_components/documents-preview-client.tsx')

    expect(detail).toContain('knowledgeBasesApi')
    expect(detail).toContain('/app/kb/${knowledgeBaseId}/documents/preview?docs=${documentId}')
    expect(preview).toContain('knowledgeBasesApi')
    expect(preview).toContain('/app/kb/${knowledgeBaseId}')
    expect(`${detail}\n${preview}`).not.toContain('adminKnowledgeBasesApi')
  })
})
