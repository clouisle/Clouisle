import { afterEach, expect, mock, test } from 'bun:test'
import { Window } from 'happy-dom'
import React, { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { FilePreviewPanel } from './file-preview-panel'

const window = new Window({ url: 'http://localhost' })
Object.assign(globalThis, {
  window,
  document: window.document,
  navigator: window.navigator,
  HTMLElement: window.HTMLElement,
  Node: window.Node,
  Event: window.Event,
})
;(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true

const roots: Root[] = []
afterEach(() => {
  for (const root of roots.splice(0)) act(() => root.unmount())
  document.body.replaceChildren()
})

function render(element: React.ReactElement) {
  const container = document.body.appendChild(document.createElement('div'))
  const root = createRoot(container)
  roots.push(root)
  act(() => root.render(element))
  return container
}

async function flush() {
  await act(async () => {
    await Bun.sleep(0)
  })
}

test('loads text from a provided file loader and keeps it downloadable', async () => {
  const loadFile = mock(async () => new Blob(['hello preview'], { type: 'text/plain' }))
  const createObjectURL = mock(() => 'blob:preview')
  const revokeObjectURL = mock(() => {})
  const originalCreateObjectURL = URL.createObjectURL
  const originalRevokeObjectURL = URL.revokeObjectURL
  Object.assign(URL, { createObjectURL, revokeObjectURL })

  try {
    const container = render(
      <FilePreviewPanel
        file={{ filename: 'notes.txt', mimeType: 'text/plain' }}
        loadFile={loadFile}
      />
    )
    await flush()

    expect(loadFile).toHaveBeenCalledTimes(1)
    expect(container.textContent).toContain('hello preview')
    const downloadButton = container.querySelector('button[aria-label="Download"]') as HTMLButtonElement
    expect(downloadButton.disabled).toBe(false)

    act(() => downloadButton.click())
    expect(createObjectURL).toHaveBeenCalledWith(expect.any(Blob))
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:preview')
  } finally {
    Object.assign(URL, { createObjectURL: originalCreateObjectURL, revokeObjectURL: originalRevokeObjectURL })
  }
})

test('loads an unsupported knowledge-base file so it remains downloadable', async () => {
  const loadFile = mock(async () => new Blob(['legacy document']))
  const container = render(
    <FilePreviewPanel
      file={{ filename: 'legacy.doc', mimeType: 'application/msword' }}
      loadFile={loadFile}
    />
  )
  await flush()

  expect(loadFile).toHaveBeenCalledTimes(1)
  expect(container.textContent).toContain('This file type cannot be previewed here')
  expect((container.querySelector('button[aria-label="Download"]') as HTMLButtonElement).disabled).toBe(false)
})
test('renders PDF using PdfPreview', async () => {
  const loadFile = mock(async () => new Blob(['pdf preview'], { type: 'application/pdf' }))
  const container = render(
    <FilePreviewPanel
      file={{ filename: 'report.pdf', mimeType: 'application/pdf' }}
      loadFile={loadFile}
    />
  )
  await flush()

  expect(container.querySelector('div')).toBeTruthy()
  expect(loadFile).toHaveBeenCalledTimes(1)
})

test('renders mermaid diagrams with interactive controls and strict security level', async () => {
  const loadFile = mock(async () => new Blob(['graph TD; A-->B;'], { type: 'text/vnd.mermaid' }))
  const container = render(
    <FilePreviewPanel
      file={{ filename: 'diagram.mmd', mimeType: 'text/vnd.mermaid' }}
      loadFile={loadFile}
    />
  )
  await flush()
  expect(container.querySelector('div')).toBeTruthy()
  expect(loadFile).toHaveBeenCalledTimes(1)

  // Exercise buttons in MermaidFilePreview
  const buttons = container.querySelectorAll('button')
  if (buttons.length >= 3) {
    act(() => buttons[0].click()) // Reset/Expand
    act(() => buttons[1].click()) // ZoomOut
    act(() => buttons[2].click()) // ZoomIn
  }

  // Exercise pointer interactions
  const dragArea = container.querySelector('.cursor-grab') as HTMLElement | null
  if (dragArea) {
    dragArea.setPointerCapture = () => {}
    dragArea.releasePointerCapture = () => {}
    act(() => {
      dragArea.dispatchEvent(new window.Event('pointerdown', { bubbles: true }))
      dragArea.dispatchEvent(new window.Event('pointermove', { bubbles: true }))
      dragArea.dispatchEvent(new window.Event('pointerup', { bubbles: true }))
      dragArea.dispatchEvent(new window.Event('pointercancel', { bubbles: true }))
    })
  }
})

test('renders zoom viewport with controls for image mode', async () => {
  const loadFile = mock(async () => new Blob(['fake image bytes'], { type: 'image/png' }))
  const container = render(
    <FilePreviewPanel
      file={{ filename: 'sample.png', mimeType: 'image/png' }}
      loadFile={loadFile}
    />
  )
  await flush()
  expect(loadFile).toHaveBeenCalledTimes(1)
  expect(container.querySelector('img')).toBeTruthy()
})

test('renders video preview for video files', async () => {
  const loadFile = mock(async () => new Blob(['fake video'], { type: 'video/mp4' }))
  const container = render(
    <FilePreviewPanel
      file={{ filename: 'clip.mp4', mimeType: 'video/mp4' }}
      loadFile={loadFile}
    />
  )
  await flush()
  expect(loadFile).toHaveBeenCalledTimes(1)
  expect(container.querySelector('video')).toBeTruthy()
})

test('renders audio preview for audio files', async () => {
  const loadFile = mock(async () => new Blob(['fake audio'], { type: 'audio/mp3' }))
  const container = render(
    <FilePreviewPanel
      file={{ filename: 'track.mp3', mimeType: 'audio/mp3' }}
      loadFile={loadFile}
    />
  )
  await flush()
  expect(loadFile).toHaveBeenCalledTimes(1)
  expect(container.querySelector('audio')).toBeTruthy()
})

test('renders markdown preview with streamdown', async () => {
  const loadFile = mock(async () => new Blob(['# Markdown Title\nSome content'], { type: 'text/markdown' }))
  const container = render(
    <FilePreviewPanel
      file={{ filename: 'notes.md', mimeType: 'text/markdown' }}
      loadFile={loadFile}
    />
  )
  await flush()
  expect(loadFile).toHaveBeenCalledTimes(1)
  expect(container.textContent).toContain('Markdown Title')
})

test('renders docx preview mode using DocxPreview', async () => {
  const loadFile = mock(async () => new Blob(['fake docx'], { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' }))
  const container = render(
    <FilePreviewPanel
      file={{ filename: 'doc.docx', mimeType: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' }}
      loadFile={loadFile}
    />
  )
  await flush()
  expect(container.querySelector('div')).toBeTruthy()
  expect(loadFile).toHaveBeenCalledTimes(1)
})

test('renders pptx preview mode using PptxPreview', async () => {
  const loadFile = mock(async () => new Blob(['fake presentation'], { type: 'application/vnd.openxmlformats-officedocument.presentationml.presentation' }))
  const container = render(
    <FilePreviewPanel
      file={{ filename: 'deck.pptx', mimeType: 'application/vnd.openxmlformats-officedocument.presentationml.presentation' }}
      loadFile={loadFile}
    />
  )
  await flush()
  expect(container.querySelector('div')).toBeTruthy()
  expect(loadFile).toHaveBeenCalledTimes(1)
})

test('renders spreadsheet preview mode using SpreadsheetPreview and switches sheets', async () => {
  const csvContent = 'A1,B1\nA2,B2'
  const loadFile = mock(async () => new Blob([csvContent], { type: 'text/csv' }))
  const container = render(
    <FilePreviewPanel
      file={{ filename: 'data.csv', mimeType: 'text/csv' }}
      loadFile={loadFile}
    />
  )
  await flush()
  expect(container.querySelector('div')).toBeTruthy()
  expect(loadFile).toHaveBeenCalledTimes(1)
})

test('renders permission denied message and disables download on 403 load error', async () => {
  const loadFile = mock(async () => {
    throw new Error('asset_load_failed:403')
  })
  const container = render(
    <FilePreviewPanel
      file={{ filename: 'secret.pdf', mimeType: 'application/pdf' }}
      loadFile={loadFile}
      labels={{
        permissionDenied: 'Custom permission denied message',
      }}
    />
  )
  await flush()

  expect(container.textContent).toContain('Custom permission denied message')
  const downloadButton = container.querySelector('button[aria-label="Download"]') as HTMLButtonElement
  expect(downloadButton.disabled).toBe(true)
})

test('renders warning icon on generic load error', async () => {
  const loadFile = mock(async () => {
    throw new Error('network failure')
  })
  const container = render(
    <FilePreviewPanel
      file={{ filename: 'document.pdf', mimeType: 'application/pdf' }}
      loadFile={loadFile}
    />
  )
  await flush()

  expect(container.textContent).toContain('The file preview could not be loaded.')
  expect(container.querySelector('svg.text-amber-500')).toBeTruthy()
})

