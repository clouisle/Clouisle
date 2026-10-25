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
const selectChangeContext = React.createContext<((value?: string) => void) | undefined>(undefined)
mock.module('@/components/ui/select', () => ({
  Select: ({ children, value, disabled, onValueChange }: { children?: React.ReactNode; value?: string; disabled?: boolean; onValueChange?: (value?: string) => void }) => <selectChangeContext.Provider value={onValueChange}><div data-select-value={value} data-select-disabled={disabled}>{children}</div></selectChangeContext.Provider>,
  SelectContent: ({ children }: { children?: React.ReactNode }) => <div>{children}</div>,
  SelectEmpty: ({ children }: { children?: React.ReactNode }) => <div>{children}</div>,
  SelectItem: ({ children, value, disabled }: { children?: React.ReactNode; value: string; disabled?: boolean }) => {
    const onValueChange = React.useContext(selectChangeContext)
    return <button data-value={value} disabled={disabled} onClick={() => onValueChange?.(value)}>{children}</button>
  },
  SelectTrigger: ({ children }: { children?: React.ReactNode }) => <div>{children}</div>,
  SelectValue: ({ children }: { children?: React.ReactNode }) => <span>{children}</span>,
}))
import { ApiError } from '@/lib/api/client'
mock.module('@/components/ui/button', () => ({
  Button: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => <button {...props}>{children}</button>,
}))
let numericCodeOnChange: ((event: { target: { value: string } }) => void) | undefined
let userNameOnChange: ((event: { target: { value: string } }) => void) | undefined
mock.module('@/components/ui/input', () => ({
  Input: (props: React.InputHTMLAttributes<HTMLInputElement>) => {
    if (props.inputMode === 'numeric') numericCodeOnChange = props.onChange as typeof numericCodeOnChange
    if (props.id?.endsWith('-user_name')) userNameOnChange = props.onChange as typeof userNameOnChange
    return <input {...props} />
  },
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
  Card: ({ children, ...props }: React.HTMLAttributes<HTMLDivElement>) => <div data-slot="card" {...props}>{children}</div>,
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

const state: {
  features: { agent_chat: boolean; knowledge_collection: boolean }
  bindings: WeChatBinding[]
  agents: WeChatAgentOption[]
  targets: WeChatTarget[]
  agentError: unknown
  targetsError: unknown
  modelsError: unknown
  featuresError: unknown
  bindingsError: unknown
} = {
  features: { agent_chat: true, knowledge_collection: true },
  bindings: [],
  agents: [agentOption],
  targets: [target],
  agentError: null,
  targetsError: null,
  modelsError: null,
  featuresError: null,
  bindingsError: null,
}
const purposeMock = mock(() => Promise.resolve(binding()))
const stopRunMock = mock(() => Promise.resolve({}))
const loginMock = mock(() => Promise.resolve({ id: 'login-1', status: 'wait', qrcode_content: 'qr-content', expires_at: '2099-01-01T00:00:00Z' }))
const pollMock = mock<(id: string, code?: string) => ReturnType<typeof loginMock>>(() => Promise.resolve({ id: 'login-1', status: 'need_verifycode', qrcode_content: 'qr-content', expires_at: '2099-01-01T00:00:00Z' }))
const disconnectMock = mock<(id: string) => Promise<{ id: string }>>(() => Promise.resolve({ id: 'binding-1' }))

mock.module('@/lib/api/wechat-knowledge', () => ({
  WECHAT_ACTIVE_RUN_STATUSES: ['queued', 'running', 'stopping', 'completing', 'waiting'],
  wechatKnowledgeApi: {
    features: () => state.featuresError ? Promise.reject(state.featuresError) : Promise.resolve(state.features),
    bindings: () => state.bindingsError ? Promise.reject(state.bindingsError) : Promise.resolve(state.bindings),
    targets: () => state.targetsError ? Promise.reject(state.targetsError) : Promise.resolve(state.targets),
    models: () => state.modelsError ? Promise.reject(state.modelsError) : Promise.resolve({ vision: [], stt: [sttModel] }),
    agents: () => state.agentError ? Promise.reject(state.agentError) : Promise.resolve(state.agents),
    agentModels: () => Promise.resolve({ stt: [sttModel] }),
    purpose: purposeMock,
    stopRun: stopRunMock,
    login: loginMock,
    poll: pollMock,
    disconnect: disconnectMock,
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
  state.agents = [agentOption]
  state.targets = [target]
  state.agentError = null
  state.targetsError = null
  state.modelsError = null
  state.featuresError = null
  state.bindingsError = null
  loginMock.mockReset()
  loginMock.mockImplementation(() => Promise.resolve({ id: 'login-1', status: 'wait', qrcode_content: 'qr-content', expires_at: '2099-01-01T00:00:00Z' }))
  pollMock.mockReset()
  pollMock.mockImplementation(() => Promise.resolve({ id: 'login-1', status: 'need_verifycode', qrcode_content: 'qr-content', expires_at: '2099-01-01T00:00:00Z' }))
  disconnectMock.mockReset()
  disconnectMock.mockImplementation(() => Promise.resolve({ id: 'binding-1' }))
  stopRunMock.mockReset()
  stopRunMock.mockImplementation(() => Promise.resolve({}))
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
  await React.act(async () => { root.render(<WeChatKnowledge active />) })
  await flush(container, state.bindingsError instanceof Error ? state.bindingsError.message : state.bindings.length > 0 ? 'change' : 'empty')
  return { container }
}

function buttonForBinding(container: HTMLElement, botId: string, label: string) {
  const card = [...container.querySelectorAll('[data-slot="card"]')].find(node => node.textContent?.includes(botId))
  return [...(card?.querySelectorAll('button') ?? [])].find(node => node.textContent === label)
}
function buttonByLabel(container: HTMLElement, label: string) {
  return [...container.querySelectorAll('button')].find(node =>
    node.textContent?.includes(label) || node.getAttribute('aria-label') === label || node.title === label
  )
}

async function click(container: HTMLElement, label: string) {
  const button = buttonByLabel(container, label)
  expect(button).toBeTruthy()
  await React.act(async () => {
    button!.dispatchEvent(new domWindow.MouseEvent('click', { bubbles: true }))
    await settle(20)
  })
}

describe('additional purpose form behavior', () => {
  test('initializes defaults, omits hidden fields, validates edits, and submits select and checkbox changes', async () => {
    const configurableAgent: WeChatAgentOption = {
      ...agentOption,
      variables: [
        { name: 'mode', type: 'select', label: 'Mode', required: true, options: ['brief', 'full'], default: 'brief' },
        { name: 'enabled', type: 'checkbox', label: 'Enabled', required: false, default: 'true', description: 'Enable option' },
        { name: 'hidden', type: 'text', label: 'Hidden', required: false, hidden: true, default: 'secret' },
        { name: 'priority', type: 'number', label: 'Priority', required: true, min: 1, max: 5, default: '2' },
        { name: 'short', type: 'text', label: 'Short', required: false, default: 'long', maxLength: 3 },
      ],
    }
    state.agents = [configurableAgent]
    const { container } = await render({ bindings: [binding({ purpose: 'agent', agent_config: {
      agent_id: 'agent-1', agent_name: 'Support Agent', variables: { mode: 'invalid', short: 'long' }, stt_model_id: null,
      conversation_id: null, run_id: null, run_status: null,
    } })] })
    await click(container, 'change')
    await flush(container, 'Mode')
    expect(container.querySelector('[data-select-value="invalid"]')).toBeTruthy()
    expect(container.querySelector<HTMLInputElement>('input[type="checkbox"]')?.checked).toBe(true)
    expect(container.textContent).not.toContain('Hidden')
    const number = container.querySelector<HTMLInputElement>('input[type="number"]')!
    expect(number.min).toBe('1')
    expect(number.max).toBe('5')
    await click(container, 'save')
    expect(container.textContent).toContain('variableOptionInvalid')
    expect(container.textContent).toContain('variableTooLong')
    const short = [...container.querySelectorAll<HTMLInputElement>('input')].find(input => input.type === 'text')!
    expect(short.value).toBe('long')
    expect(short.max).toBe('')
    await click(container, 'full')
    expect(container.textContent).not.toContain('variableOptionInvalid')
    const checkbox = container.querySelector<HTMLInputElement>('input[type="checkbox"]')!
    checkbox.click()
    await click(container, 'save')
    expect(purposeMock).not.toHaveBeenCalled()
    expect(container.textContent).toContain('variableTooLong')
  })

  test('preserves an edited Agent draft across same-agent polling and resets it on identity changes', async () => {
    const savedBinding = binding({ purpose: 'agent', agent_config: {
      agent_id: 'agent-1', agent_name: 'Support Agent', variables: { user_name: 'Saved', priority: '2', notes: '' },
      stt_model_id: 'stt-1', conversation_id: null, run_id: null, run_status: null,
    } })
    state.agents = [agentOption, { ...agentOption, id: 'agent-2', name: 'Second Agent', variables: [{ name: 'other', type: 'text', label: 'Other', required: false }] }]
    const { container } = await render({ bindings: [savedBinding] })
    await click(container, 'change')
    await flushInputValue(container, 'Saved')
    expect(userNameOnChange).toBeDefined()
    await React.act(async () => { userNameOnChange!({ target: { value: 'Draft' } }) })
    await flushInputValue(container, 'Draft')

    // Simulate a binding poll returning new binding/agent object references for the same IDs.
    state.bindings = [{ ...savedBinding, last_received_at: '2026-10-19T00:00:00Z', agent_config: { ...savedBinding.agent_config!, variables: { user_name: 'New saved value', priority: '4', notes: '' }, stt_model_id: null } }]
    const refresh = buttonByLabel(container, 'refresh')!
    await React.act(async () => { refresh.click(); await settle(20) })
    expect([...container.querySelectorAll<HTMLInputElement>('input')].find(input => input.value === 'Draft')).toBeTruthy()
    expect(container.querySelector('[data-select-value="stt-1"]')).toBeTruthy()

    const choices = [...container.querySelectorAll('button[data-value]')]
    await React.act(async () => { choices.find(button => button.getAttribute('data-value') === 'agent-2')!.click() })
    await flush(container, 'Other')
    expect(container.querySelector<HTMLInputElement>('input')?.value).not.toBe('Draft')
  })

  test('shows target and model load errors without preventing editor recovery', async () => {
    state.targetsError = new Error('targets offline')
    state.modelsError = new Error('models offline')
    const { container } = await render({ bindings: [binding({ purpose: 'knowledge_collection', collection: {
      knowledge_base_id: 'kb-1', knowledge_base_name: 'Handbook', vision_model_id: null, stt_model_id: null,
    } })] })
    await click(container, 'change')
    await click(container, 'purposeKnowledgeCollection')
    await flush(container, 'failed')
    expect(container.textContent).toContain('noTargets')
    expect(buttonByLabel(container, 'save')?.disabled).toBe(false)
    expect(purposeMock).not.toHaveBeenCalled()
  })
  test('shows agent load error and recovers when reopening the purpose editor', async () => {
    state.agentError = new ApiError(500, 'Agent choices unavailable')
    const { container } = await render({ bindings: [binding({ purpose: 'agent', agent_config: {
      agent_id: 'agent-1', agent_name: 'Support Agent', variables: {}, stt_model_id: null,
      conversation_id: null, run_id: null, run_status: null,
    } })] })
    await click(container, 'change')
    await flush(container, 'Agent choices unavailable')
    await click(container, 'cancel')
    state.agentError = null
    await click(container, 'change')
    await flush(container, 'User name')
    expect(buttonByLabel(container, 'save')?.disabled).toBe(false)
  })

  test('shows purpose save errors without closing or marking the editor successful', async () => {
    const { container } = await render({ bindings: [binding({
      purpose: 'knowledge_collection', collection: {
        knowledge_base_id: 'kb-1', knowledge_base_name: 'Handbook', vision_model_id: null, stt_model_id: null,
      },
    })] })
    await click(container, 'change')
    purposeMock.mockRejectedValueOnce(new ApiError(500, 'Purpose rejected'))
    await click(container, 'save')
    await flush(container, 'Purpose rejected')
    expect(container.textContent).toContain('Purpose rejected')
    expect(buttonByLabel(container, 'cancel')).toBeTruthy()
    purposeMock.mockRejectedValueOnce(new Error('network unavailable'))
    await click(container, 'save')
    await flush(container, 'failed')
    expect(container.textContent).toContain('failed')
    expect(buttonByLabel(container, 'cancel')).toBeTruthy()
  })
})

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
test('disabled collection feature keeps saved binding visible and explains paused configuration', async () => {
  const { container } = await render({
    features: { agent_chat: true, knowledge_collection: false },
    bindings: [binding({ purpose: 'knowledge_collection', collection: {
      knowledge_base_id: 'kb-1', knowledge_base_name: 'Handbook', vision_model_id: null, stt_model_id: null,
    } })],
  })
  expect(container.textContent).toContain('Handbook')
  expect(container.textContent).toContain('featurePaused')
  await click(container, 'change')
  expect(container.querySelector('[data-value="knowledge_collection"]')?.getAttribute('disabled')).not.toBeNull()
  expect(container.textContent).not.toContain('target')
  expect(buttonByLabel(container, 'save')?.disabled).toBe(true)
  expect(purposeMock).not.toHaveBeenCalled()
})

test('selecting a knowledge base clears model choices and binds the selected target', async () => {
  const secondTarget: WeChatTarget = { id: 'kb-2', name: 'Policies', team_name: 'Team B' }
  state.targets = [target, secondTarget]
  const { container } = await render({ bindings: [binding()] })
  await click(container, 'change')
  await click(container, 'purposeKnowledgeCollection')
  await flush(container, 'Handbook')
  const targetTrigger = container.querySelector('label[for$="-target"]')?.nextElementSibling
  expect(targetTrigger?.textContent).toContain('Team A / Handbook')
  await click(container, 'Team B / Policies')
  await flush(container, 'Policies')
  expect(purposeMock).not.toHaveBeenCalled()
  await click(container, 'save')
  expect(purposeMock).toHaveBeenCalledWith('binding-1', expect.objectContaining({
    purpose: 'knowledge_collection', knowledge_base_id: 'kb-2', vision_model_id: null, stt_model_id: null,
  }))
  await flush(container, 'saved')
  expect(buttonByLabel(container, 'change')).toBeTruthy()
})

test('successful QR login displays its status and close action clears the QR', async () => {
  const { container } = await render({ bindings: [] })
  await click(container, 'showQr')
  await flush(container, 'login.wait')
  expect(loginMock).toHaveBeenCalledTimes(1)
  expect(container.querySelector('[data-testid="qr"]')).toBeTruthy()
  await click(container, 'closeQr')
  expect(container.querySelector('[data-testid="qr"]')).toBeNull()
  expect(container.textContent).not.toContain('login.wait')
})

test('login API failure surfaces an alert and leaves retry available', async () => {
  const { container } = await render({ bindings: [] })
  loginMock.mockRejectedValueOnce(new ApiError(503, 'Login unavailable'))
  await click(container, 'showQr')
  await flush(container, 'Login unavailable')
  expect(container.querySelector('[role="alert"]')?.textContent).toContain('Login unavailable')
  expect(buttonByLabel(container, 'showQr')?.disabled).toBe(false)
  expect(container.querySelector('[data-testid="qr"]')).toBeNull()
})

test('failed verification preserves the code and QR session for retry', async () => {
  const { container } = await render({ bindings: [] })
  await click(container, 'showQr')
  await flush(container, 'login.wait')
  await flush(container, 'login.need_verifycode')
  await React.act(async () => numericCodeOnChange?.({ target: { value: '5678' } }))
  await flushInputValue(container, '5678')
  pollMock.mockRejectedValueOnce(new ApiError(400, 'Code rejected'))
  await click(container, 'verify')
  await flush(container, 'Code rejected')
  expect(container.querySelector<HTMLInputElement>('input[inputmode="numeric"]')?.value).toBe('5678')
  expect(container.querySelector('[data-testid="qr"]')).toBeTruthy()
  expect(pollMock).toHaveBeenLastCalledWith('login-1', '5678')
})

test('disconnect confirmation closes the binding and reports refreshed empty state', async () => {
  const { container } = await render({ bindings: [binding()] })
  disconnectMock.mockImplementationOnce(async () => {
    state.bindings = []
    return { id: 'binding-1' }
  })
  buttonForBinding(container, 'bot-1', 'disconnect')!.click()
  await settle(20)
  const confirm = [...container.querySelectorAll('button')].filter(button => button.textContent === 'disconnect').at(-1)!
  confirm.click()
  await flush(container, 'empty')
  expect(disconnectMock).toHaveBeenCalledWith('binding-1')
  expect(container.textContent).not.toContain('bot-1')
  expect(container.querySelector('[role="dialog"]')).toBeNull()
})

test('onboarding focuses on authorization without empty history sections', async () => {
  const { container } = await render({ bindings: [] })
  expect(buttonByLabel(container, 'showQr')?.disabled).toBe(false)
  expect(buttonByLabel(container, 'change')).toBeUndefined()
})
test('shows connection errors, disabled disconnect, and collection summaries for saved bindings', async () => {
  const { container } = await render({ bindings: [
    binding({ id: 'error-binding', status: 'error', last_error: null, bot_id: 'broken-bot' }),
    binding({ id: 'offline-binding', status: 'disconnected', last_error: 'Old connection detail', bot_id: 'offline-bot' }),
    binding({ id: 'collection-binding', purpose: 'knowledge_collection', collection: {
      knowledge_base_id: 'kb-1', knowledge_base_name: 'Handbook', vision_model_id: 'vision-1', stt_model_id: 'stt-1',
    } }),
  ] })

  expect(container.textContent).toContain('connectionError')
  expect(container.textContent).toContain('Old connection detail')
  expect(container.textContent).toContain('collectionActive:Handbook')
  expect(buttonForBinding(container, 'offline-bot', 'disconnect')?.disabled).toBe(true)
})

test('renders nothing while inactive and does not load bindings', async () => {
  const container = document.createElement('div')
  document.body.appendChild(container)
  containers.push(container)
  const root = createRoot(container)
  roots.push(root)
  root.render(<WeChatKnowledge active={false} />)
  await settle(20)

  expect(container.childElementCount).toBe(0)
})
test('surfaces binding load failure and allows retry through refresh', async () => {
  state.bindingsError = new ApiError(503, 'Bindings unavailable')
  const { container } = await render()
  await flush(container, 'Bindings unavailable')
  expect(container.querySelector('[role="alert"]')?.textContent).toContain('Bindings unavailable')
  state.bindingsError = null
  await click(container, 'refresh')
  await settle(20)
  await flush(container, 'bot-1')
  expect(container.textContent).toContain('bot-1')
})

test('starts QR login, polls for verification, and submits only numeric code with login id', async () => {
  const { container } = await render({ bindings: [] })
  await click(container, 'showQr')
  await flush(container, 'login.wait')
  expect(loginMock).toHaveBeenCalledTimes(1)
  expect(container.querySelector('[data-testid="qr"]')).toBeTruthy()
  await flush(container, 'verifyCode')
  expect(pollMock).toHaveBeenCalledWith('login-1')
  await React.act(async () => numericCodeOnChange?.({ target: { value: '12x34' } }))
  await flushInputValue(container, '1234')
  await click(container, 'verify')
  expect(pollMock).toHaveBeenLastCalledWith('login-1', '1234')
  expect(container.textContent).toContain('login.need_verifycode')
})

test('reports a failed run stop and keeps the active run available', async () => {
  const { container } = await render({ bindings: [binding({ purpose: 'agent', agent_config: {
    agent_id: 'agent-1', agent_name: 'Support Agent', variables: {}, stt_model_id: null,
    conversation_id: 'conv-1', run_id: 'run-9', run_status: 'running',
  } })] })
  stopRunMock.mockRejectedValueOnce(new ApiError(500, 'Stop rejected'))
  await click(container, 'stop')
  await flush(container, 'Stop rejected')
  expect(stopRunMock).toHaveBeenCalledWith('agent-1', 'run-9')
  expect(container.textContent).toContain('runStatus.running')
  expect(container.querySelector('[role="alert"]')?.textContent).toContain('Stop rejected')
})

test('disconnect confirmation sends binding id', async () => {
  const { container } = await render({ bindings: [binding()] })
  buttonForBinding(container, 'bot-1', 'disconnect')!.click()
  await settle(20)
  const confirm = [...container.querySelectorAll('button')].filter(button => button.textContent === 'disconnect').at(-1)!
  confirm.click()
  await settle(30)
  expect(disconnectMock).toHaveBeenCalledWith('binding-1')
})
