import { afterEach, expect, mock, test } from 'bun:test'
import { Window } from 'happy-dom'
import React, { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { IconPlaceholder } from './icon-placeholder'

const window = new Window({ url: 'http://localhost' })
Object.assign(globalThis, {
  window,
  document: window.document,
  navigator: window.navigator,
  Element: window.Element,
  HTMLElement: window.HTMLElement,
  Node: window.Node,
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

test('renders the matching lucide icon and forwards svg props', () => {
  const container = render(<IconPlaceholder lucide="Search" aria-label="search" className="size-4" />)
  const icon = container.querySelector('svg')

  expect(icon).toBeTruthy()
  expect(icon?.getAttribute('aria-label')).toBe('search')
  expect(icon?.getAttribute('class')).toContain('size-4')
})

test('renders nothing for an icon name outside the supported set', () => {
  const warn = mock(() => {})
  const originalWarn = console.warn
  console.warn = warn

  try {
    const container = render(<IconPlaceholder lucide="NotARealIcon" />)
    expect(container.querySelector('svg')).toBeNull()
    expect(warn).toHaveBeenCalledTimes(1)
  } finally {
    console.warn = originalWarn
  }
})
