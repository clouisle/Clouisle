import { afterEach, expect, mock, test } from 'bun:test'
import { Window } from 'happy-dom'
import React, { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { DocxPreview } from './docx-preview'

const mockImportDocxFile = mock(() => Promise.resolve())
const mockRevealPage = mock(() => {})
const mockEditor = {
  model: { sections: [] },
  fileName: 'document.docx',
  importDocxFile: mockImportDocxFile,
  isImporting: false,
  importError: null,
  currentPage: 1,
  totalPages: 3,
  revealPage: mockRevealPage,
}

mock.module('@extend-ai/react-docx', () => ({
  useDocxEditor: () => mockEditor,
  useDocxPageThumbnails: () => ({
    thumbnails: [
      {
        pageIndex: 0,
        pageNumber: 1,
        widthPx: 100,
        heightPx: 140,
        pixelWidthPx: 200,
        pixelHeightPx: 280,
        scale: 0.12,
        paint: mock(() => true),
      },
      {
        pageIndex: 1,
        pageNumber: 2,
        widthPx: 100,
        heightPx: 140,
        pixelWidthPx: 200,
        pixelHeightPx: 280,
        scale: 0.12,
        paint: mock(() => true),
      },
    ],
  }),
  DocxEditorViewer: (props: Record<string, unknown>) => {
    const safeProps = Object.fromEntries(
      Object.entries(props).filter(([key]) => !key.startsWith('page') && key !== 'editor')
    )
    return <div data-testid="docx-viewer" {...safeProps} />
  },
}))

class TestResizeObserver {
  private readonly callback: ResizeObserverCallback

  constructor(callback: ResizeObserverCallback) {
    this.callback = callback
  }

  observe() {}
  unobserve() {}
  disconnect() {}
  trigger() {
    this.callback([], this as unknown as ResizeObserver)
  }
}

const window = new Window({ url: 'http://localhost' })
Object.assign(globalThis, {
  window,
  document: window.document,
  navigator: window.navigator,
  Element: window.Element,
  HTMLElement: window.HTMLElement,
  Node: window.Node,
  Event: window.Event,
  ResizeObserver: TestResizeObserver as unknown as typeof ResizeObserver,
  requestAnimationFrame: (cb: FrameRequestCallback) => setTimeout(cb, 0),
  cancelAnimationFrame: (id: number) => clearTimeout(id),
  getComputedStyle: window.getComputedStyle.bind(window),
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

test('renders DocxPreview with unified toolbar, wheel zoom support, and thumbnail rail', async () => {
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
          zoomReset: 'Fit to width',
          toggleThumbnails: 'Toggle thumbnails',
          fitToWidth: 'Fit to width',
        }}
        onError={onError}
      />
    )
    await Bun.sleep(10)
  })

  expect(container.textContent).toContain('quarterly-report.docx')
  expect(container.textContent).toContain('1/3')
  expect(container.textContent).toContain('Fit')
  expect(container.querySelector('[data-testid="docx-viewer"]')).toBeTruthy()
  expect(container.querySelector('[data-testid="docx-thumbnail-sidebar"]')).toBeTruthy()

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

  const resetFitBtn = container.querySelector('button[aria-label="Fit to width"]') as HTMLButtonElement
  expect(resetFitBtn).toBeTruthy()
  await act(async () => {
    resetFitBtn?.click()
    await Bun.sleep(1)
  })
  expect(container.textContent).toContain('Fit')

  // Test Wheel Zoom with metaKey / ctrlKey
  const viewport = container.querySelector('[data-testid="docx-viewport"]') as HTMLDivElement
  await act(async () => {
    const wheelEvent = new window.Event('wheel') as unknown as WheelEvent
    Object.assign(wheelEvent, { deltaY: -100, metaKey: true, ctrlKey: false, deltaMode: 0, preventDefault: () => {} })
    viewport.dispatchEvent(wheelEvent)
    await Bun.sleep(1)
  })
  expect(container.textContent).not.toContain('(Fit)')
})

test('supports thumbnail sidebar toggle and page selection', async () => {
  const blob = new Blob(['docx-mock-content'])
  let container!: HTMLDivElement

  await act(async () => {
    container = render(
      <DocxPreview
        blob={blob}
        labels={{
          loading: 'Loading...',
          parseError: 'Error',
          toggleThumbnails: 'Toggle thumbnails',
          thumbnails: 'Thumbnails (3)',
          pageNumber: ({ page }) => `Page Number ${page}`,
        }}
      />
    )
    await Bun.sleep(20)
  })

  expect(container.querySelector('[data-testid="docx-thumbnail-sidebar"]')).toBeTruthy()

  const toggleBtn = container.querySelector('button[aria-label="Toggle thumbnails"]') as HTMLButtonElement
  await act(async () => {
    toggleBtn?.click()
    await Bun.sleep(1)
  })
  expect(container.querySelector('[data-testid="docx-thumbnail-sidebar"]')).toBeNull()

  await act(async () => {
    toggleBtn?.click()
    await Bun.sleep(1)
  })
  const page2Btn = container.querySelector('button[aria-label="Page Number 2"]') as HTMLButtonElement
  await act(async () => {
    page2Btn?.click()
    await Bun.sleep(1)
  })
  expect(mockRevealPage).toHaveBeenCalledWith(1)
})

test('synchronizes the active thumbnail with editor.currentPage after rerender', async () => {
  const blob = new Blob(['docx-mock-content'])
  let container!: HTMLDivElement
  const rerenderRef = { current: () => {} }

  function EditorHarness() {
    const [, setRevision] = React.useState(0)
    React.useEffect(() => {
      rerenderRef.current = () => setRevision((revision) => revision + 1)
    })
    return <DocxPreview blob={blob} />
  }

  await act(async () => {
    container = render(<EditorHarness />)
    await Bun.sleep(10)
  })

  const page1Btn = container.querySelector('button[aria-label="Page 1"]') as HTMLButtonElement
  const page2Btn = container.querySelector('button[aria-label="Page 2"]') as HTMLButtonElement
  expect(page1Btn.className).toContain('font-semibold')
  expect(page2Btn.className).not.toContain('font-semibold')

  mockEditor.currentPage = 2
  await act(async () => {
    rerenderRef.current()
    await Bun.sleep(10)
  })

  expect(page1Btn.className).not.toContain('font-semibold')
  expect(page2Btn.className).toContain('font-semibold')
  expect(container.textContent).toContain('2/3')

  mockEditor.currentPage = 1
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
