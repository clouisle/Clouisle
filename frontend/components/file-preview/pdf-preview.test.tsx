import { afterEach, expect, mock, test } from 'bun:test'
import { Window } from 'happy-dom'
import React, { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
const init = mock(() => ({} as HTMLElement))
mock.module('@embedpdf/viewer', () => ({
  default: { init },
  defineChrome: (config: unknown) => config,
  group: (...args: unknown[]) => ({ type: 'group', args }),
  item: (...args: unknown[]) => ({ type: 'item', args }),
  custom: (...args: unknown[]) => ({ type: 'custom', args }),
}))
// Dynamic import is required so the module mock is registered before PdfPreview evaluates.
const { PdfPreview } = await import('./pdf-preview')

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
const originalCreateObjectURL = URL.createObjectURL
const originalRevokeObjectURL = URL.revokeObjectURL

const roots: Root[] = []
afterEach(() => {
  for (const root of roots.splice(0)) act(() => root.unmount())
  document.body.replaceChildren()
  URL.createObjectURL = originalCreateObjectURL
  URL.revokeObjectURL = originalRevokeObjectURL
  init.mockReset()
  init.mockImplementation(() => ({} as HTMLElement))
})

function render(element: React.ReactElement) {
  const container = document.body.appendChild(document.createElement('div'))
  const root = createRoot(container)
  roots.push(root)
  act(() => root.render(element))
  return container
}

test('initializes PdfPreview with a generated source and locale', async () => {
  const createObjectUrl = mock(() => 'blob:pdf')
  const revokeObjectUrl = mock(() => {})
  URL.createObjectURL = createObjectUrl as typeof URL.createObjectURL
  URL.revokeObjectURL = revokeObjectUrl as typeof URL.revokeObjectURL
  const blob = new Blob(['%PDF-1.4 mock content'], { type: 'application/pdf' })
  const onError = mock(() => {})
  const container = render(<PdfPreview blob={blob} locale="zh" onError={onError} />)

  await act(async () => {
    await Bun.sleep(10)
  })

  expect(onError).not.toHaveBeenCalled()
  expect(init).toHaveBeenCalledTimes(1)
  const options = init.mock.calls[0]?.[0] as { target?: HTMLElement; src?: string; locale?: string }
  expect(options.target).toBe(container.firstElementChild?.firstElementChild)
  expect(options.src).toBe('blob:pdf')
  expect(options.locale).toBe('zh')
})

test('reports synchronous PDF viewer initialization errors', async () => {
  URL.createObjectURL = mock(() => 'blob:pdf') as typeof URL.createObjectURL
  URL.revokeObjectURL = mock(() => {}) as typeof URL.revokeObjectURL
  init.mockImplementation(() => {
    throw new Error('viewer initialization failed')
  })
  const blob = new Blob(['%PDF-1.4 mock content'], { type: 'application/pdf' })
  const onError = mock(() => {})

  render(<PdfPreview blob={blob} locale="zh" onError={onError} />)
  await act(async () => {
    await Bun.sleep(0)
  })

  expect(onError).toHaveBeenCalledTimes(1)
})
