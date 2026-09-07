import { afterEach, expect, mock, test } from 'bun:test'
import { Window } from 'happy-dom'
import React, { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { PptxPreview } from './pptx-preview'

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

test('renders PptxPreview when given a valid presentation blob', async () => {
  const blob = new Blob([new Uint8Array([0x50, 0x4b, 0x03, 0x04])], {
    type: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
  })
  const onError = mock(() => {})
  const container = render(<PptxPreview blob={blob} onError={onError} />)

  await act(async () => {
    await Bun.sleep(10)
  })

  expect(onError).not.toHaveBeenCalled()
  expect(container.querySelector('div')).toBeTruthy()
})

test('calls onError when blob arrayBuffer reading fails', async () => {
  const blob = {
    arrayBuffer: () => Promise.reject(new Error('Corrupt blob')),
  } as unknown as Blob

  const onError = mock(() => {})
  render(<PptxPreview blob={blob} onError={onError} />)

  await act(async () => {
    await Bun.sleep(10)
  })

  expect(onError).toHaveBeenCalledTimes(1)
})
