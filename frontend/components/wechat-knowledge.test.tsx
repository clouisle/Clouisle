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
  WeChatBinding,
  WeChatModel,
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
mock.module('@/components/ui/tooltip', () => ({
  Tooltip: ({ children }: React.PropsWithChildren) => <>{children}</>,
  TooltipTrigger: (props: React.ButtonHTMLAttributes<HTMLButtonElement>) => <button {...props} />,
  TooltipContent: ({ children }: React.PropsWithChildren) => <>{children}</>,
}))
mock.module('@/components/ui/select', () => ({
  Select: ({ children, value }: { children?: React.ReactNode; value?: string }) => <div data-select-value={value}>{children}</div>,
  SelectContent: ({ children }: { children?: React.ReactNode }) => <div>{children}</div>,
  SelectEmpty: ({ children }: { children?: React.ReactNode }) => <div>{children}</div>,
  SelectItem: ({ children, value, disabled }: { children?: React.ReactNode; value: string; disabled?: boolean }) => <button data-value={value} disabled={disabled}>{children}</button>,
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
  features: { agent_chat: true, knowledge_collection: true },
  bindings: [] as WeChatBinding[],
}
const purposeMock = mock(() => Promise.resolve(binding()))
const stopRunMock = mock(() => Promise.resolve({}))

mock.module('@/lib/api/wechat-knowledge', () => ({
  WECHAT_ACTIVE_RUN_STATUSES: ['queued', 'running', 'stopping', 'completing', 'waiting'],
  wechatKnowledgeApi: {
    features: () => Promise.resolve(state.features),
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

async function render(options: { bindings?: WeChatBinding[]; features?: { agent_chat: boolean; knowledge_collection: boolean } } = {}) {
  purposeMock.mockClear()
  stopRunMock.mockClear()
  state.features = options.features ?? { agent_chat: true, knowledge_collection: true }
  state.bindings = options.bindings ?? [binding()]
  const container = document.createElement('div')
  document.body.appendChild(container)
  containers.push(container)
  const root = createRoot(container)
  roots.push(root)
  root.render(<WeChatKnowledge active />)
  await flush(container, state.bindings.length > 0 ? 'change' : 'empty')
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

  test('offers stop for a nonterminal run', async () => {
    const { container } = await render({
      bindings: [binding({
        purpose: 'agent',
        agent_config: {
          agent_id: 'agent-1', agent_name: 'Support Agent', variables: {},
          stt_model_id: null, conversation_id: 'conv-1', run_id: 'run-9', run_status: 'running',
        },
      })],
    })
    const content = container.textContent ?? ''
    expect(content).toContain('runStatus.running')
    await click(container, 'stop')
    expect(stopRunMock).toHaveBeenCalledWith('agent-1', 'run-9')
  })
})

test('disabled features retain existing configuration but block login and purpose saving', async () => {
  const { container } = await render({
    features: { agent_chat: false, knowledge_collection: false },
    bindings: [binding({ purpose: 'agent', agent_config: {
      agent_id: 'agent-1', agent_name: 'Support Agent', variables: {},
      stt_model_id: null, conversation_id: null, run_id: null, run_status: null,
    } })],
  })
  expect(container.textContent).toContain('featuresDisabled')
  expect(container.textContent).toContain('Support Agent')
  expect(buttonByLabel(container, 'showQr')?.disabled).toBe(true)
  expect(buttonByLabel(container, 'disconnect')?.disabled).toBe(false)
  await click(container, 'change')
  expect(container.querySelector<HTMLButtonElement>('[data-value="agent"]')?.disabled).toBe(true)
  expect(container.querySelector<HTMLButtonElement>('[data-value="knowledge_collection"]')?.disabled).toBe(true)
  expect(buttonByLabel(container, 'save')?.disabled).toBe(true)
  expect(purposeMock).not.toHaveBeenCalled()
})

test('onboarding focuses on authorization without empty history sections', async () => {
  const { container } = await render({ bindings: [] })
  expect(buttonByLabel(container, 'showQr')?.disabled).toBe(false)
  expect(buttonByLabel(container, 'change')).toBeUndefined()
})
