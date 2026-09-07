import { afterEach, expect, test } from 'bun:test'
import * as XLSX from 'xlsx'
import { Window } from 'happy-dom'
import React, { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { SpreadsheetPreview } from './spreadsheet-preview'

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

test('renders workbook sheets and keeps visible table columns aligned', async () => {
  const workbook = XLSX.utils.book_new()
  XLSX.utils.book_append_sheet(workbook, XLSX.utils.aoa_to_sheet([
    ['Name', 'Value'],
    ['Alice', 42],
  ]), 'Summary')
  XLSX.utils.book_append_sheet(workbook, XLSX.utils.aoa_to_sheet([['Status'], ['Ready']]), 'Status')
  const bytes = XLSX.write(workbook, { type: 'array', bookType: 'xlsx' })
  const container = render(
    <SpreadsheetPreview
      blob={new Blob([bytes])}
      labels={{
        loading: 'Loading spreadsheet...',
        sheet: 'Sheet',
        rowsLimited: () => 'limited',
        parseError: 'parse error',
      }}
    />
  )

  const start = Date.now()
  while (!container.textContent?.includes('Alice')) {
    if (Date.now() - start > 3000) {
      throw new Error('Timed out waiting for workbook to render')
    }
    await act(async () => {
      await Bun.sleep(10)
    })
  }
  expect(container.textContent).toContain('Summary')
  expect(container.textContent).toContain('Alice')
  expect(container.querySelectorAll('thead th')).toHaveLength(3)
  expect(container.querySelectorAll('tbody tr')).toHaveLength(2)

  act(() => (container.querySelectorAll('button')[1] as HTMLButtonElement).click())
  expect(container.textContent).toContain('Ready')
  expect(container.querySelectorAll('thead th')).toHaveLength(2)
})

test('decodes GBK / GB18030 encoded CSV without garbled characters', async () => {
  // GBK bytes for "姓名,年龄\n张三,28\n李四,32"
  const gbkBytes = new Uint8Array([
    0xd0, 0xd5, 0xc3, 0xfb, 0x2c, 0xc4, 0xea, 0xc1, 0xe4, 0x0a, // 姓名,年龄\n
    0xd5, 0xc5, 0xc8, 0xfd, 0x2c, 0x32, 0x38, 0x0a,             // 张三,28\n
    0xc0, 0xee, 0xcb, 0xc4, 0x2c, 0x33, 0x32,                   // 李四,32
  ])
  const container = render(
    <SpreadsheetPreview
      blob={new Blob([gbkBytes], { type: 'text/csv' })}
      labels={{
        loading: 'Loading spreadsheet...',
        sheet: 'Sheet',
        rowsLimited: () => 'limited',
        parseError: 'parse error',
      }}
    />
  )

  const start = Date.now()
  while (!container.textContent?.includes('张三')) {
    if (Date.now() - start > 3000) {
      throw new Error('Timed out waiting for GBK CSV to render')
    }
    await act(async () => {
      await Bun.sleep(10)
    })
  }

  expect(container.textContent).toContain('姓名')
  expect(container.textContent).toContain('张三')
  expect(container.textContent).toContain('李四')
  expect(container.textContent).not.toContain('ÕÅÈý')
})
