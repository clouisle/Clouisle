import { describe, expect, test } from 'bun:test'
import { getDocumentMimeType, getFilePreviewMode, isFilePreviewable } from './file-preview-types'

describe('file preview types', () => {
  test('classifies common document formats for the shared renderer', () => {
    expect(getFilePreviewMode({ filename: 'report.pdf' })).toBe('pdf')
    expect(getFilePreviewMode({
      filename: 'brief.docx',
      mimeType: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    })).toBe('docx')
    expect(getFilePreviewMode({ filename: 'deck.pptx' })).toBe('pptx')
    expect(getFilePreviewMode({ filename: 'slides.ppt', mimeType: 'application/vnd.ms-powerpoint' })).toBe('pptx')
    expect(getFilePreviewMode({ filename: 'budget.xlsx' })).toBe('spreadsheet')
    expect(getFilePreviewMode({ filename: 'budget.xls', mimeType: 'application/vnd.ms-excel' })).toBe('spreadsheet')
    expect(getFilePreviewMode({ filename: 'rows.csv', mimeType: 'text/csv' })).toBe('spreadsheet')
  })

  test('keeps unsupported binary files downloadable without previewing them', () => {
    expect(getFilePreviewMode({ filename: 'archive.zip', mimeType: 'application/zip' })).toBe('unsupported')
    expect(isFilePreviewable({ filename: 'archive.zip', mimeType: 'application/zip' })).toBe(false)
  })

  test('maps knowledge-base document names to preview MIME types', () => {
    expect(getDocumentMimeType('Guide.DOCX', 'docx')).toBe('application/vnd.openxmlformats-officedocument.wordprocessingml.document')
    expect(getDocumentMimeType('budget.xlsx', 'xlsx')).toBe('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    expect(getDocumentMimeType('source', 'url')).toBe('text/html')
    expect(getDocumentMimeType('deck.pptx', 'pptx')).toBe('application/vnd.openxmlformats-officedocument.presentationml.presentation')
    expect(getDocumentMimeType('slides.ppt', 'ppt')).toBe('application/vnd.ms-powerpoint')
    expect(getDocumentMimeType('data.tsv', 'tsv')).toBe('text/tab-separated-values')
    expect(getDocumentMimeType('uploaded-file', 'pdf')).toBe('application/pdf')
  })
})
