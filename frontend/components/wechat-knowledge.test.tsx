import { Window } from 'happy-dom'
import { afterEach, describe, expect, mock, test } from 'bun:test'
import * as React from 'react'
import { createRoot, type Root } from 'react-dom/client'

const domWindow = new Window()
const globals = globalThis as unknown as Record<string, unknown>
for (const key of [
  'window', 'document', 'navigator', 'Element', 'Node', 'HTMLElement',
  'getComputedStyle', 'MutationObserver', 'requestAnimationFrame',
  'cancelAnimationFrame', 'SVGElement', 'CustomEvent', 'KeyboardEvent',
  'FocusEvent', 'InputEvent', 'localStorage',
]) {
  if (key in domWindow) globals[key] = (domWindow as unknown as Record<string, unknown>)[key]
}
globals.window = domWindow
globals.document = domWindow.document
globals.IS_REACT_ACT_ENVIRONMENT = false

import type {
  WeChatAgentOption,
  WeChatAgentReceipt,
  WeChatBinding,
  WeChatModel,
  WeChatReceipt,
  WeChatTarget,
} from '@/lib/api/wechat-knowledge'

const translate = (key: string, values?: Record<string, string>) => {
  if (values?.purpose != null) return `${key}:${values.purpose}`
  if (values?.target != null) return `${key}:${values.target}`
  if (values?.status != null) return `${key}:${values.status}`
  return key
}

mock.module('next-intl', () => ({ useTranslations: () => translate }))
mock.module('next/link', () => ({
  default: ({ children, href }: { children?: React.ReactNode; href: string }) => <a href={href}>{children}</a>,
}))
mock.module('qrcode.react', () => ({ QRCodeSVG: () => <div data-testid="qr" /> }))
mock.module('@/components/ui/select', () => ({
  Select: ({ children, value }: { children?: React.ReactNode; value?: string }) => <div data-select-value={value}>{children}</div>,
  SelectContent: ({ children }: { children?: React.ReactNode }) => <div>{children}</div>,
  SelectEmpty: ({ children }: { children?: React.ReactNode }) => <div>{children}</div>,
  SelectItem: ({ children, value }: { children?: React.ReactNode; value: string }) => <button data-value={value}>{children}</button>,
  SelectTrigger: ({ children }: { children?: React.ReactNode }) => <div>{children}</div>,
  SelectValue: ({ children }: { children?: React.ReactNode }) => <span>{children}</span>,
}))
mock.module('@/components/ui/button', () => ({
  Button: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => <button {...props}>{children}</button>,
}))
mock.module('@/components/ui/input', () => ({
  Input: (props: React.InputHTMLAttributes<HTMLInputElement>) => <input {...props} />,
}))
mock.module('@/components/ui/textarea', () => ({
  Textarea: (props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) => <textarea {...props} />,
}))
mock.module('@/components/ui/label', () => ({
  Label: ({ children, ...props }: React.LabelHTMLAttributes<HTMLLabelElement>) => <label {...props}>{children}</label>,
}))
mock.module('@/components/ui/alert', () => ({
  Alert: ({ children }: { children?: React.ReactNode }) => <div role="alert">{children}</div>,
  AlertDescription: ({ children }: { children?: React.ReactNode }) => <p>{children}</p>,
}))
mock.module('@/components/ui/card', () => ({
  Card: ({ children }: { children?: React.ReactNode }) => <div>{children}</div>,
  CardContent: ({ children }: { children?: React.ReactNode }) => <div>{children}</div>,
  CardDescription: ({ children }: { children?: React.ReactNode }) => <p>{children}</p>,
  CardHeader: ({ children }: { children?: React.ReactNode }) => <div>{children}</div>,
  CardTitle: ({ children }: { children?: React.ReactNode }) => <h3>{children}</h3>,
}))
mock.module('@/components/ui/alert-dialog', () => ({
  AlertDialog: ({ children, open }: { children?: React.ReactNode; open?: boolean }) => (open ? <div role="dialog">{children}</div> : null),
  AlertDialogAction: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => <button {...props}>{children}</button>,
  AlertDialogCancel: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => <button {...props}>{children}</button>,
  AlertDialogContent: ({ children }: { children?: React.ReactNode }) => <div>{children}</div>,
  AlertDialogDescription: ({ children }: { children?: React.ReactNode }) => <p>{children}</p>,
  AlertDialogFooter: ({ children }: { children?: React.ReactNode }) => <div>{children}</div>,
  AlertDialogHeader: ({ children }: { children?: React.ReactNode }) => <div>{children}</div>,
  AlertDialogTitle: ({ children }: { children?: React.ReactNode }) => <h3>{children}</h3>,
}))

const agentOption: WeChatAgentOption = {
  id: 'agent-1', name: 'Support Agent', team_name: 'Team A',
  variables: [
    { name: 'user_name', type: 'text', label: 'User name', required: true },
    { name: 'priority', type: 'number', label: 'Priority', required: true, min: 1, max: 5 },
    { name: 'notes', type: 'paragraph', label: 'Notes', required: false },
  ],
  enable_attachments: true, attachment_config: null,
}
const target: WeChatTarget = { id: 'kb-1', name: 'Handbook', team_name: 'Team A' }
const sttModel: WeChatModel = { id: 'stt-1', name: 'STT One' }

function binding(overrides: Partial<WeChatBinding> = {}): WeChatBinding {
  return {
    id: 'binding-1', status: 'connected', last_error: null, last_received_at: null,
    created_at: '2026-10-18T00:00:00Z', bot_id: 'bot-1', purpose: 'none',
    collection: null, agent_config: null, ...overrides,
  }
}

const state = {
  bindings: [] as WeChatBinding[],
  receipts: [] as WeChatReceipt[],
  agentReceipts: [] as WeChatAgentReceipt[],
}
const purposeMock = mock(() => Promise.resolve(binding()))
const stopRunMock = mock(() => Promise.resolve({}))

mock.module('@/lib/api/wechat-knowledge', () => ({
  WECHAT_ACTIVE_RECEIPT_STATUSES: ['pending', 'submitted'],
  WECHAT_ACTIVE_RUN_STATUSES: ['queued', 'running', 'stopping', 'completing', 'waiting'],
  wechatKnowledgeApi: {
    bindings: () => Promise.resolve(state.bindings),
    targets: () => Promise.resolve([target]),
    models: () => Promise.resolve({ vision: [], stt: [sttModel] }),
    agents: () => Promise.resolve([agentOption]),
    agentModels: () => Promise.resolve({ stt: [sttModel] }),
    purpose: purposeMock,
    stopRun: stopRunMock,
    login: () => Promise.reject(new Error('unused')),
    poll: () => Promise.reject(new Error('unused')),
    disconnect: () => Promise.resolve({ id: 'binding-1' }),
    receipts: () => Promise.resolve(state.receipts),
    agentReceipts: () => Promise.resolve(state.agentReceipts),
    original: () => Promise.resolve(),
  },
}))

// Deferred on purpose: `mock.module` must be registered before the component
// module graph (and its API client import) is evaluated.
const { WeChatKnowledge } = await import('./wechat-knowledge')

const containers: HTMLDivElement[] = []
const roots: Root[] = []

afterEach(() => {
  for (const root of roots) root.unmount()
  roots.length = 0
  for (const container of containers) container.remove()
  containers.length = 0
})

async function settle(milliseconds: number) {
  const { promise, resolve } = Promise.withResolvers<void>()
  setTimeout(resolve, milliseconds)
  await promise
}

async function flush(container: HTMLElement, expected: string) {
  for (let attempt = 0; attempt < 100; attempt++) {
    if ((container.textContent ?? '').includes(expected)) return
    await settle(10)
  }
  throw new Error(`Timed out waiting for rendered text: ${expected}`)
}

async function flushInputValue(container: HTMLElement, value: string) {
  for (let attempt = 0; attempt < 100; attempt++) {
    const inputs = [...container.querySelectorAll('input, textarea')]
    if (inputs.some(input => input.value === value)) return
    await settle(10)
  }
  throw new Error(`Input value did not appear: ${value}`)
}

async function render(options: { bindings?: WeChatBinding[]; receipts?: WeChatReceipt[]; agentReceipts?: WeChatAgentReceipt[] } = {}) {
  purposeMock.mockClear()
  stopRunMock.mockClear()
  state.bindings = options.bindings ?? [binding()]
  state.receipts = options.receipts ?? []
  state.agentReceipts = options.agentReceipts ?? []
  const container = document.createElement('div')
  document.body.appendChild(container)
  containers.push(container)
  const root = createRoot(container)
  roots.push(root)
  root.render(<WeChatKnowledge active />)
  await flush(container, 'purposeTitle')
  return { container }
}

function buttonByLabel(container: HTMLElement, label: string) {
  return [...container.querySelectorAll('button')].find(node => node.textContent === label)
}

async function click(container: HTMLElement, label: string) {
  const button = buttonByLabel(container, label)
  expect(button).toBeTruthy()
  button!.dispatchEvent(new domWindow.MouseEvent('click', { bubbles: true }))
  await settle(20)
}

describe('WeChatKnowledge purpose selection', () => {
  test('shows one purpose per connection and no second enable switch', async () => {
    const { container } = await render({
      bindings: [binding({
        purpose: 'agent',
        agent_config: {
          agent_id: 'agent-1', agent_name: 'Support Agent', variables: { user_name: 'Ada' },
          stt_model_id: null, conversation_id: null, run_id: null, run_status: null,
        },
      })],
    })
    const content = container.textContent ?? ''
    expect(content).toContain('purposeTitle')
    expect(content).toContain('purposeActive:purposeAgent')
    expect(content).not.toContain('"enable"')
    expect(content).not.toContain('"disable"')
  })

  test('saves the Agent purpose with variables and speech model', async () => {
    const { container } = await render({
      bindings: [binding({
        purpose: 'agent',
        agent_config: {
          agent_id: 'agent-1', agent_name: 'Support Agent', variables: { user_name: 'Ada', priority: '2', notes: '' },
          stt_model_id: 'stt-1', conversation_id: null, run_id: null, run_status: null,
        },
      })],
    })
    await click(container, 'change')
    await flush(container, 'User name')
    await flushInputValue(container, 'Ada')
    await click(container, 'save')
    expect(purposeMock).toHaveBeenCalledTimes(1)
    expect(purposeMock.mock.calls[0]?.[1]).toMatchObject({
      purpose: 'agent',
      agent_id: 'agent-1',
      variables: { user_name: 'Ada', priority: '2', notes: '' },
      stt_model_id: 'stt-1',
    })
  })

  test('blocks saving the Agent purpose when a required variable is empty', async () => {
    const { container } = await render({
      bindings: [binding({
        purpose: 'agent',
        agent_config: {
          agent_id: 'agent-1', agent_name: 'Support Agent', variables: { user_name: '', priority: '9', notes: '' },
          stt_model_id: null, conversation_id: null, run_id: null, run_status: null,
        },
      })],
    })
    await click(container, 'change')
    await click(container, 'save')
    expect(purposeMock).not.toHaveBeenCalled()
    expect(container.textContent ?? '').toContain('variablesRequired')
    expect(container.textContent ?? '').toContain('variableNumberInvalid')
  })

  test('saves the knowledge collection purpose with the selected target', async () => {
    const { container } = await render({
      bindings: [binding({
        purpose: 'knowledge_collection',
        collection: {
          knowledge_base_id: 'kb-1', knowledge_base_name: 'Handbook',
          vision_model_id: null, stt_model_id: null,
        },
      })],
    })
    await click(container, 'change')
    await click(container, 'save')
    expect(purposeMock).toHaveBeenCalledTimes(1)
    expect(purposeMock.mock.calls[0]?.[1]).toMatchObject({
      purpose: 'knowledge_collection',
      knowledge_base_id: 'kb-1',
      vision_model_id: null,
      stt_model_id: null,
    })
  })

  test('renders Agent delivery outcomes and the web conversation link', async () => {
    const { container } = await render({
      agentReceipts: [{
        id: 'receipt-1', binding_id: 'binding-1', status: 'completed', agent_name: 'Support Agent',
        agent_id: 'agent-1', conversation_id: 'conv-1', run_id: 'run-1', run_status: 'completed',
        error: null, delivery_status: ['submitted'], created_at: '2026-10-18T00:00:00Z',
      }],
    })
    const content = container.textContent ?? ''
    expect(content).toContain('receiptStatus.completed')
    expect(content).toContain('agentDelivery:deliverySubmitted')
    expect(container.querySelector('a')?.getAttribute('href')).toBe('/chat/agent-1?conversation=conv-1')
  })

  test('offers stop for a nonterminal run and keeps collection receipts distinct', async () => {
    const { container } = await render({
      bindings: [binding({
        purpose: 'agent',
        agent_config: {
          agent_id: 'agent-1', agent_name: 'Support Agent', variables: {},
          stt_model_id: null, conversation_id: 'conv-1', run_id: 'run-9', run_status: 'running',
        },
      })],
      receipts: [{
        id: 'kb-1', binding_id: 'binding-1', knowledge_base_id: 'kb-1', status: 'completed',
        last_error: null, reply_status: 'sent', results: [], created_at: '2026-10-18T00:00:00Z',
      }],
    })
    const content = container.textContent ?? ''
    expect(content).toContain('runStatus.running')
    expect(content).toContain('collectionReceiptsTitle')
    expect(content).toContain('agentReceiptsTitle')
    await click(container, 'stop')
    expect(stopRunMock).toHaveBeenCalledWith('agent-1', 'run-9')
  })
})
