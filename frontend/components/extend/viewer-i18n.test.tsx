import { afterEach, expect, test } from 'bun:test'
import { Window } from 'happy-dom'
import React, { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import {
  createViewerLabels,
  DEFAULT_VIEWER_LABELS,
  ViewerI18nProvider,
  useViewerLabels,
} from './viewer-i18n'

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

function Probe() {
  return <span>{useViewerLabels().slide}</span>
}

test('builds every label from the translator', () => {
  const t = (key: string, values?: Record<string, string | number>) =>
    values ? `${key}:${JSON.stringify(values)}` : key
  const labels = createViewerLabels(t)

  expect(labels.pageTotal({ total: 3 })).toBe('pageTotal:{"total":3}')
  expect(labels.slideLabel({ slide: 2 })).toBe('slideLabel:{"slide":2}')
  expect(labels.sheetPreview({ name: 'Sheet1' })).toBe(
    'sheetPreview:{"name":"Sheet1"}'
  )
  expect(labels.xlsxActions.cut).toBe('xlsxActions.cut')

  for (const value of Object.values(labels)) {
    if (typeof value === 'function') {
      value({ page: 1, slide: 1, total: 1, name: 'Sheet', index: 1 })
    }
  }
  for (const value of Object.values(DEFAULT_VIEWER_LABELS)) {
    if (typeof value === 'function') {
      value({ page: 1, slide: 1, total: 1, name: 'Sheet', index: 1 })
    }
  }
})

test('uses provider labels and falls back to English defaults', () => {
  const provided = render(
    <ViewerI18nProvider labels={{ ...DEFAULT_VIEWER_LABELS, slide: '第' }}>
      <Probe />
    </ViewerI18nProvider>
  )
  expect(provided.textContent).toBe('第')

  const fallback = render(<Probe />)
  expect(fallback.textContent).toBe(DEFAULT_VIEWER_LABELS.slide)
})
