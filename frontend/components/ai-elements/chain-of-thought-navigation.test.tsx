import { afterEach, expect, mock, test } from 'bun:test'
import { Window } from 'happy-dom'
import React, { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'

const window = new Window({ url: 'http://localhost' })
Object.assign(globalThis, {
  window, document: window.document, navigator: window.navigator,
  HTMLElement: window.HTMLElement, HTMLButtonElement: window.HTMLButtonElement,
  getComputedStyle: window.getComputedStyle,
  requestAnimationFrame: (callback: FrameRequestCallback) => setTimeout(callback, 0),
  cancelAnimationFrame: clearTimeout,
  IS_REACT_ACT_ENVIRONMENT: true,
})
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
// Load after the translation mock is registered.
const { ChainOfThought, ChainOfThoughtContent, ChainOfThoughtHeader } = await import('./chain-of-thought')

let root: Root | undefined
afterEach(() => {
  if (root) act(() => root!.unmount())
  root = undefined
  document.body.replaceChildren()
})

test('sticky header collapses and only scrolls when the thought starts above the viewport', () => {
  const scroller = document.createElement('div')
  scroller.setAttribute('data-chat-scroller', '')
  document.body.appendChild(scroller)
  const container = document.createElement('div')
  scroller.appendChild(container)
  root = createRoot(container)
  act(() => root!.render(<ChainOfThought defaultOpen>
    <ChainOfThoughtHeader title="Thought" />
    <ChainOfThoughtContent>Details</ChainOfThoughtContent>
  </ChainOfThought>))

  const trace = container.querySelector('[data-slot="trace"]') as HTMLElement
  const header = container.querySelector('button')!
  const scrollBy = mock(() => {})
  scroller.scrollBy = scrollBy
  scroller.getBoundingClientRect = () => ({ top: 100 } as DOMRect)
  trace.getBoundingClientRect = () => ({ top: 30 } as DOMRect)
  act(() => header.click())
  expect(scrollBy).toHaveBeenCalledWith({ top: -70, behavior: 'instant' })
  expect(header.getAttribute('aria-expanded')).toBe('false')

  act(() => header.click())
  scrollBy.mockClear()
  trace.getBoundingClientRect = () => ({ top: 120 } as DOMRect)
  act(() => header.click())
  expect(scrollBy).not.toHaveBeenCalled()
  expect(header.getAttribute('aria-expanded')).toBe('false')
})
