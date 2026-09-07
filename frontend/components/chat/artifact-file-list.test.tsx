import { expect, mock, test } from 'bun:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { act as rendererAct, create as createRenderer, type ReactTestRenderer } from '@/test-utils/rtl-renderer'
import type { FilePart } from './types'

const icon = ({ name, className }: { name: string; className?: string }) => (
  <svg data-icon={name} className={className} />
)

mock.module('next-intl', () => ({
  useTranslations: () => (key: string, values?: Record<string, unknown>) => {
    if (key === 'preview') return 'Preview'
    if (key === 'download') return 'Download'
    if (key === 'showMore') return `Show ${values?.count ?? ''} more`
    if (key === 'showLess') return 'Show less'
    if (key === 'artifacts') return 'Artifacts'
    return 'Files'
  },
}))
mock.module('lucide-react', () => ({
  ChevronDown: (props: { className?: string }) => icon({ ...props, name: 'ChevronDown' }),
  ChevronUp: (props: { className?: string }) => icon({ ...props, name: 'ChevronUp' }),
  Package: (props: { className?: string }) => icon({ ...props, name: 'Package' }),
  FileIcon: (props: { className?: string }) => icon({ ...props, name: 'FileIcon' }),
  FileImage: (props: { className?: string }) => icon({ ...props, name: 'FileImage' }),
  FileVideo: (props: { className?: string }) => icon({ ...props, name: 'FileVideo' }),
  FileAudio: (props: { className?: string }) => icon({ ...props, name: 'FileAudio' }),
  FileText: (props: { className?: string }) => icon({ ...props, name: 'FileText' }),
  FileType: (props: { className?: string }) => icon({ ...props, name: 'FileType' }),
  FileCode: (props: { className?: string }) => icon({ ...props, name: 'FileCode' }),
  Link: (props: { className?: string }) => icon({ ...props, name: 'Link' }),
  Download: (props: { className?: string }) => icon({ ...props, name: 'Download' }),
  Eye: (props: { className?: string }) => icon({ ...props, name: 'Eye' }),
  Expand: (props: { className?: string }) => icon({ ...props, name: 'Expand' }),
  ZoomIn: (props: { className?: string }) => icon({ ...props, name: 'ZoomIn' }),
  ZoomOut: (props: { className?: string }) => icon({ ...props, name: 'ZoomOut' }),
  X: (props: { className?: string }) => icon({ ...props, name: 'X' }),
}))

const { ArtifactFile, ArtifactFileList } = await import('./artifact-file-list')
globalThis.IS_REACT_ACT_ENVIRONMENT = true

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
  expect(html).toContain('Artifacts')
  expect(html).toContain('(1)')
  expect(html).toContain('data-icon="Package"')
  expect(html).not.toContain('Generated files')
  expect(html).toContain('data-icon="FileType"')
  expect(html).toContain('text-green-500')
  expect(html).toContain('report.csv')
  expect(html).toContain('2.0 KB')
  expect(html).toContain('aria-label="Preview: report.csv"')
  expect(html).toContain('aria-label="Download: report.csv"')
  expect(html).toContain('href="/files/report.csv"')
  expect(html).toContain('download="report.csv"')
})

test('shows three artifacts by default and expands the remaining files', () => {
  const files = Array.from({ length: 5 }, (_, index): FilePart => ({
    ...report,
    path: `/workspace/file-${index + 1}.txt`,
    filename: `file-${index + 1}.txt`,
    url: `/files/file-${index + 1}.txt`,
  }))
  let renderer!: ReactTestRenderer

  rendererAct(() => {
    renderer = createRenderer(<ArtifactFileList files={files} />)
  })

  try {
    const renderedFiles = () => renderer.root.findAllByType(ArtifactFile).map((node) => node.props.file.filename)
    expect(renderedFiles()).toEqual(['file-1.txt', 'file-2.txt', 'file-3.txt'])
    expect(renderer.root.findByProps({ 'aria-expanded': false }).findByType('span').children.join('')).toBe('Show 2 more')

    rendererAct(() => renderer.root.findByProps({ 'aria-expanded': false }).props.onClick())
    expect(renderedFiles()).toEqual(['file-1.txt', 'file-2.txt', 'file-3.txt', 'file-4.txt', 'file-5.txt'])
    expect(renderer.root.findByProps({ 'aria-expanded': true }).findByType('span').children.join('')).toBe('Show less')

    rendererAct(() => renderer.root.findByProps({ 'aria-expanded': true }).props.onClick())
    expect(renderedFiles()).toEqual(['file-1.txt', 'file-2.txt', 'file-3.txt'])
  } finally {
    rendererAct(() => renderer.unmount())
  }
})

test('renders preview for supported documents and omits it without a callback', () => {
  const supported: FilePart = {
    type: 'file',
    filename: 'report.docx',
    url: '/files/report.docx',
    mimeType: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  }
  const supportedHtml = renderToStaticMarkup(<ArtifactFileList files={[supported]} onOpenPreview={() => {}} />)
  const noCallbackHtml = renderToStaticMarkup(<ArtifactFileList files={[report]} />)

  expect(supportedHtml).toContain('aria-label="Preview: report.docx"')
  expect(supportedHtml).toContain('download="report.docx"')
  expect(noCallbackHtml).not.toContain('aria-label="Preview: report.csv"')
  expect(noCallbackHtml).toContain('download="report.csv"')
})

test('renders nothing for an empty artifact list', () => {
  expect(renderToStaticMarkup(<ArtifactFileList files={[]} />)).toBe('')
})
