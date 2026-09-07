import { afterEach, expect, mock, test } from 'bun:test'
import { Window } from 'happy-dom'
import React, { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { DocxPreview } from './docx-preview'

const mockImportDocxFile = mock(() => Promise.resolve())

mock.module('@extend-ai/react-docx', () => ({
  useDocxEditor: () => ({
    model: { sections: [] },
    fileName: 'document.docx',
    importDocxFile: mockImportDocxFile,
    isImporting: false,
    importError: null,
    currentPage: 1,
    totalPages: 3,
  }),
  DocxEditorViewer: (props: Record<string, unknown>) => <div data-testid="docx-viewer" {...props} />,
}))

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

test('renders DocxPreview with toolbar and handles zoom actions', async () => {
  const blob = new Blob(['docx-mock-content'], {
    type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  })
  const onError = mock(() => {})
  let container!: HTMLDivElement
  await act(async () => {
    container = render(
      <DocxPreview
        blob={blob}
        filename="quarterly-report.docx"
        labels={{
          loading: 'Loading docx...',
          parseError: 'Parse error',
          zoomIn: 'Zoom in',
          zoomOut: 'Zoom out',
          zoomReset: 'Reset zoom',
        }}
        onError={onError}
      />
    )
    await Bun.sleep(10)
  })

  expect(container.textContent).toContain('quarterly-report.docx')
  expect(container.textContent).toContain('1 / 3')
  expect(container.textContent).toContain('100%')
  expect(container.querySelector('[data-testid="docx-viewer"]')).toBeTruthy()

  const zoomInBtn = container.querySelector('button[aria-label="Zoom in"]') as HTMLButtonElement
  const zoomOutBtn = container.querySelector('button[aria-label="Zoom out"]') as HTMLButtonElement

  await act(async () => {
    zoomInBtn?.click()
    await Bun.sleep(1)
  })
  expect(container.textContent).toContain('110%')

  await act(async () => {
    zoomOutBtn?.click()
    await Bun.sleep(1)
  })
  expect(container.textContent).toContain('100%')
})

test('triggers onError on docx import failure', async () => {
  mockImportDocxFile.mockImplementationOnce(() => Promise.reject(new Error('Import failed')))
  const blob = new Blob(['corrupt-docx'])
  const onError = mock(() => {})
  await act(async () => {
    render(<DocxPreview blob={blob} onError={onError} />)
    await Bun.sleep(10)
  })

  expect(onError).toHaveBeenCalledTimes(1)
})
