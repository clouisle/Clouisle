import { afterEach, expect, mock, test } from 'bun:test'
import { Window } from 'happy-dom'
import React, { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { PdfPreview } from './pdf-preview'

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

test('renders PdfPreview component with a target element', async () => {
  const blob = new Blob(['%PDF-1.4 mock content'], { type: 'application/pdf' })
  const onError = mock(() => {})
  const container = render(<PdfPreview blob={blob} onError={onError} />)

  await act(async () => {
    await Bun.sleep(10)
  })

  expect(onError).not.toHaveBeenCalled()
  expect(container.querySelector('div')).toBeTruthy()
})
