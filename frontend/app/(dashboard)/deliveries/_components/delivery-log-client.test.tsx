import { Window } from 'happy-dom'
import { afterEach, expect, mock, test } from 'bun:test'
import * as React from 'react'
import type { Root } from 'react-dom/client'
import type { DeliveryPage, DeliveryQuery, DeliveryRecord } from '@/lib/api/deliveries'

const domWindow = new Window()
const globals = globalThis as unknown as Record<string, unknown>
for (const key of [
  'window', 'document', 'navigator', 'Element', 'Node', 'HTMLElement',
  'getComputedStyle', 'MutationObserver', 'ResizeObserver', 'requestAnimationFrame',
  'cancelAnimationFrame', 'SVGElement', 'CustomEvent', 'KeyboardEvent',
  'FocusEvent', 'InputEvent', 'PointerEvent', 'MouseEvent', 'localStorage',
]) {
  if (key in domWindow) globals[key] = (domWindow as unknown as Record<string, unknown>)[key]
}
globals.IS_REACT_ACT_ENVIRONMENT = true
const { createRoot } = await import('react-dom/client')

const translate = (key: string, values?: Record<string, number | string>) => {
  if (key === 'pageInfo') return `page ${values?.page}/${values?.total}`
  return key.split('.').pop() ?? key
}
mock.module('next-intl', () => ({ useTranslations: () => translate, useLocale: () => 'en' }))
let searchParams = new URLSearchParams()
const replace = mock(() => {})
mock.module('next/navigation', () => ({
  usePathname: () => '/deliveries',
  useSearchParams: () => searchParams,
  useRouter: () => router,
}))
const router = { replace }

const record: DeliveryRecord = {
  id: 'delivery-1', provider_type: 'feishu', run_id: 'run-1',
  user_id: 'user-1', agent_id: 'agent-1', chat_id: 'chat-1', message_id: 'om-1',
  event_key: 'final-asset', sequence: 0, kind: 'asset', filename: 'report.pptx',
  content_type: 'application/vnd.ms-powerpoint', size: 512, media_type: 'file',
  status: 'error', error: 'feishu_agent_asset_upload_failed',
  error_detail: 'FeishuAPIError: Access denied\nHTTP 403 | code 131006',
  has_media_key: false, created_at: '2026-10-22T10:00:00Z', updated_at: '2026-10-22T10:00:01Z',
}
const listMock = mock(async (params: DeliveryQuery): Promise<DeliveryPage> => ({
  items: [record], total: 60, limit: params.limit ?? 20, offset: params.offset ?? 0,
}))
mock.module('@/lib/api/deliveries', () => ({ deliveriesApi: { list: listMock } }))

// Keep the actual Card, Input, Select, Popover, faceted filter and Table implementations.
const { DeliveryLogClient } = await import('./delivery-log-client')
const roots: Root[] = []

async function settle() {
  await React.act(async () => {
    await Bun.sleep(350)
  })
}
async function render() {
  const container = document.createElement('div')
  document.body.append(container)
  const root = createRoot(container)
  roots.push(root)
  await React.act(async () => root.render(<DeliveryLogClient />))
  return container
}
async function click(element: HTMLElement | null | undefined) {
  expect(element).toBeTruthy()
  await React.act(async () => { element!.click() })
}
function button(text: string, scope: ParentNode = document) {
  return [...scope.querySelectorAll<HTMLButtonElement>('button')].find(node => node.textContent?.trim() === text)
}
function inputValue(input: HTMLInputElement, value: string) {
  const setter = Object.getOwnPropertyDescriptor(domWindow.HTMLInputElement.prototype, 'value')!.set!
  setter.call(input, value)
  input.dispatchEvent(new domWindow.Event('input', { bubbles: true }) as unknown as Event)
}

afterEach(async () => {
  await React.act(async () => { roots.splice(0).forEach(root => root.unmount()) })
  document.body.replaceChildren()
  searchParams = new URLSearchParams()
  mock.clearAllMocks()
})

test('renders real filters, readable original errors and working pagination', async () => {
  const container = await render()
  expect(container.querySelectorAll('[data-slot="popover-trigger"]')).toHaveLength(2)
  expect(container.textContent).toContain(record.error_detail)
  expect(container.querySelector('[data-slot="select-trigger"]')?.textContent).toContain('20')
  await click(container.querySelector('button[aria-label="nextPage"]'))
  expect(container.textContent).toContain('page 2/3')
  expect(listMock.mock.calls.at(-1)?.[0].offset).toBe(20)

  await click(container.querySelector('[data-slot="popover-trigger"]'))
  await click(button('feishu', document.querySelector('[data-slot="popover-content"]')!))
  expect(listMock.mock.calls.at(-1)?.[0].provider_type).toEqual(['feishu'])
  expect(container.textContent).toContain('page 1/3')
  await click(button('wechat', document.querySelector('[data-slot="popover-content"]')!))
  expect(listMock.mock.calls.at(-1)?.[0].provider_type).toEqual(['feishu', 'wechat'])
  await click(button('clearFilters', document.querySelector('[data-slot="popover-content"]')!))
  expect(listMock.mock.calls.at(-1)?.[0].provider_type).toBeUndefined()
  await React.act(async () => {
    document.dispatchEvent(new domWindow.KeyboardEvent('keydown', { key: 'Escape', bubbles: true }) as unknown as KeyboardEvent)
  })
  await click(container.querySelectorAll<HTMLElement>('[data-slot="popover-trigger"]')[1])
  const popup = document.querySelector('[data-slot="popover-content"]')!
  await click(button('error', popup))
  await click(button('unknown', popup))
  expect(listMock.mock.calls.at(-1)?.[0].status).toEqual(['error', 'unknown'])
  expect(container.querySelectorAll('[data-slot="popover-trigger"]')[1].textContent).toContain('unknown')
  await React.act(async () => {
    document.dispatchEvent(new domWindow.KeyboardEvent('keydown', { key: 'Escape', bubbles: true }) as unknown as KeyboardEvent)
  })
  await click(container.querySelector('[data-slot="select-trigger"]'))
  const sizeOption = [...document.querySelectorAll<HTMLElement>('[data-slot="select-item"]')]
    .find(node => node.textContent?.trim() === '50')
  await click(sizeOption)
  expect(container.querySelector('[data-slot="select-trigger"]')?.textContent).toContain('50')
  expect(container.textContent).toContain('page 1/2')
  expect(listMock.mock.calls.at(-1)?.[0]).toMatchObject({ limit: 50, offset: 0 })
})

test('search restores from the URL, resets page and clears with the filters', async () => {
  searchParams = new URLSearchParams('search=report')
  const container = await render()
  const search = container.querySelector<HTMLInputElement>('input[aria-label="searchPlaceholder"]')!
  expect(search.value).toBe('report')
  expect(listMock.mock.calls.at(-1)?.[0].filename).toBe('report')
  await click(container.querySelector('button[aria-label="nextPage"]'))
  await React.act(async () => { inputValue(search, 'invoice') })
  await settle()
  expect(listMock.mock.calls.at(-1)?.[0]).toMatchObject({ filename: 'invoice', offset: 0 })
  expect(replace).toHaveBeenLastCalledWith('/deliveries?search=invoice', { scroll: false })
  await click(button('reset', container))
  await settle()
  expect(search.value).toBe('')
  expect(listMock.mock.calls.at(-1)?.[0].filename).toBeUndefined()
})

test('refresh hides stale rows until the replacement page arrives', async () => {
  const container = await render()
  const pending = Promise.withResolvers<DeliveryPage>()
  listMock.mockImplementationOnce(() => pending.promise)
  await click(container.querySelector('button[aria-label="refresh"]'))
  expect(container.querySelector('tbody')?.textContent).toContain('loading')
  expect(container.querySelector('tbody')?.textContent).not.toContain('report.pptx')
  expect(container.querySelector<HTMLButtonElement>('button[aria-label="nextPage"]')?.disabled).toBe(true)
  await React.act(async () => {
    pending.resolve({ items: [], total: 0, limit: 20, offset: 0 })
  })
  expect(container.querySelector('tbody')?.textContent).toContain('empty')
  expect(container.querySelector<HTMLButtonElement>('button[aria-label="nextPage"]')?.disabled).toBe(true)
})

test('one search switches between exact run ID and file name without retaining the previous filter', async () => {
  const runId = '12345678-1234-4234-8234-123456789abc'
  searchParams = new URLSearchParams({ search: runId })
  const container = await render()
  expect(container.querySelector('input[aria-label="runIdPlaceholder"]')).toBeNull()
  expect(listMock.mock.calls.at(-1)?.[0]).toMatchObject({ run_id: runId, filename: undefined })
  const search = container.querySelector<HTMLInputElement>('input[aria-label="searchPlaceholder"]')!
  await React.act(async () => { inputValue(search, 'report.pptx') })
  await settle()
  expect(listMock.mock.calls.at(-1)?.[0]).toMatchObject({ run_id: undefined, filename: 'report.pptx', offset: 0 })
  await React.act(async () => { inputValue(search, ` ${runId.toUpperCase()} `) })
  await settle()
  expect(listMock.mock.calls.at(-1)?.[0]).toMatchObject({ run_id: runId.toUpperCase(), filename: undefined })
  await click(button('reset', container))
  await settle()
  expect(listMock.mock.calls.at(-1)?.[0]).toMatchObject({ run_id: undefined, filename: undefined })
})
