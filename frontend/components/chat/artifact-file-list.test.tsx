import { expect, mock, test } from 'bun:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import type { FilePart } from './types'

const icon = ({ name, className }: { name: string; className?: string }) => (
  <svg data-icon={name} className={className} />
)

mock.module('next-intl', () => ({
  useTranslations: () => (key: string) => key === 'preview' ? 'Preview' : key === 'download' ? 'Download' : key === 'generatedFiles' ? 'Generated files' : 'Files',
}))
mock.module('lucide-react', () => ({
  FileIcon: (props: { className?: string }) => icon({ ...props, name: 'FileIcon' }),
  FileImage: (props: { className?: string }) => icon({ ...props, name: 'FileImage' }),
  FileVideo: (props: { className?: string }) => icon({ ...props, name: 'FileVideo' }),
  FileAudio: (props: { className?: string }) => icon({ ...props, name: 'FileAudio' }),
  FileText: (props: { className?: string }) => icon({ ...props, name: 'FileText' }),
  FileCode: (props: { className?: string }) => icon({ ...props, name: 'FileCode' }),
  Download: (props: { className?: string }) => icon({ ...props, name: 'Download' }),
  Eye: (props: { className?: string }) => icon({ ...props, name: 'Eye' }),
}))

const { ArtifactFileList } = await import('./artifact-file-list')

const report: FilePart = {
  type: 'file',
  path: '/workspace/report.csv',
  filename: 'report.csv',
  url: '/files/report.csv',
  mimeType: 'text/csv',
  size: 2048,
}

test('renders localized artifact file actions and a browser download link', () => {
  const html = renderToStaticMarkup(<ArtifactFileList files={[report]} onOpenPreview={() => {}} />)

  expect(html).toContain('data-artifact-file-list')
  expect(html).toContain('Generated files')
  expect(html).toContain('report.csv')
  expect(html).toContain('2.0 KB')
  expect(html).toContain('aria-label="Preview: report.csv"')
  expect(html).toContain('aria-label="Download: report.csv"')
  expect(html).toContain('href="/files/report.csv"')
  expect(html).toContain('download="report.csv"')
})

test('does not render preview for unsupported artifacts or without a callback', () => {
  const unsupported: FilePart = { type: 'file', filename: 'report.docx', url: '/files/report.docx' }
  const unsupportedHtml = renderToStaticMarkup(<ArtifactFileList files={[unsupported]} onOpenPreview={() => {}} />)
  const noCallbackHtml = renderToStaticMarkup(<ArtifactFileList files={[report]} />)

  expect(unsupportedHtml).not.toContain('aria-label="Preview: report.docx"')
  expect(unsupportedHtml).toContain('download="report.docx"')
  expect(noCallbackHtml).not.toContain('aria-label="Preview: report.csv"')
  expect(noCallbackHtml).toContain('download="report.csv"')
})

test('renders nothing for an empty artifact list', () => {
  expect(renderToStaticMarkup(<ArtifactFileList files={[]} />)).toBe('')
})
