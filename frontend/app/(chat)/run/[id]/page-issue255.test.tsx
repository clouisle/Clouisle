import { beforeAll, beforeEach, describe, expect, mock, test } from 'bun:test'
import type { ReactElement, ReactNode } from 'react'

let states: unknown[] = []
let stateIndex = 0
let effects: Array<() => void> = []
let search = new Map<string, string>()
let variables: Array<{ name: string; type: string; required?: boolean; hidden?: boolean }> = []
let variableForm = {
  values: {} as Record<string, unknown>,
  setValues: mock(() => {}),
  needsInput: false,
  isValid: true,
  fieldErrors: {},
  validate: mock(() => true),
}

const push = mock(() => {})
const getPublicAgent = mock(() => Promise.resolve({
  name: 'Public agent',
  description: 'Helpful agent',
  opening_message: 'Welcome',
  suggested_questions: ['First question'],
  hide_tool_calls: true,
  created_by: { username: 'Ada' },
  icon: '✨',
}))
const getWorkflow = mock(() => Promise.resolve({ name: 'Workflow', description: 'Workflow description' }))
const sendMessage = mock(() => Promise.resolve())
const stop = mock(() => {})
const useRun = mock(() => ({
  messages: [],
  isStreaming: false,
  isLoading: false,
  sendMessage,
  stop,
}))

const ChatContainer = () => null
const ChatInput = () => null
const VariableForm = () => null
const Button = () => null

class ApiError extends Error {
  constructor(public code: number, message: string) {
    super(message)
  }
}

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react', () => ({
  useState: (initial: unknown) => {
    const index = stateIndex++
    if (states.length <= index) states[index] = typeof initial === 'function' ? initial() : initial
    return [states[index], (value: unknown) => {
      states[index] = typeof value === 'function'
        ? (value as (previous: unknown) => unknown)(states[index])
        : value
    }]
  },
  useEffect: (callback: () => void) => effects.push(callback),
  useMemo: (factory: () => unknown) => factory(),
  useCallback: (callback: unknown) => callback,
}))
mock.module('next/navigation', () => ({
  useRouter: () => ({ push }),
  useSearchParams: () => ({ get: (key: string) => search.get(key) ?? null }),
}))
mock.module('next-intl', () => ({
  useTranslations: (namespace: string) => (key: string, values?: { name?: string }) =>
    values?.name ? `${namespace}.${key}:${values.name}` : `${namespace}.${key}`,
}))
mock.module('next/image', () => ({ default: 'img' }))
mock.module('lucide-react', () => ({
  Loader2: 'loader', AlertCircle: 'alert-circle', Sparkles: 'sparkles', GitBranch: 'git-branch',
  ChevronDown: 'chevron-down', ChevronUp: 'chevron-up',
}))
mock.module('@/lib/api', () => ({
  ApiError,
  publicAgentsApi: { getPublicAgent },
  workflowsApi: { getWorkflow },
}))
mock.module('@/components/ui/button', () => ({ Button }))
mock.module('@/components/ui/alert', () => ({
  Alert: 'alert', AlertDescription: 'alert-description', AlertTitle: 'alert-title',
}))
mock.module('@/components/ui/collapsible', () => ({
  Collapsible: 'collapsible', CollapsibleContent: 'collapsible-content', CollapsibleTrigger: 'collapsible-trigger',
}))
mock.module('@/components/chat', () => ({
  ChatContainer,
  ChatInput,
  VariableForm,
  useVariableForm: () => variableForm,
}))
mock.module('@/hooks/use-run', () => ({ useRun }))
mock.module('@/lib/utils/extract-variables', () => ({ extractVariables: () => variables }))
mock.module('@/lib/utils', () => ({ cn: (...values: unknown[]) => values.filter(Boolean).join(' ') }))

type Page = typeof import('./page').default
let UnifiedRunPage: Page

function render(params: Promise<{ id: string }> = Promise.resolve({ id: 'item-1' })) {
  stateIndex = 0
  effects = []
  return UnifiedRunPage({ params })
}

async function runEffects() {
  for (const effect of effects) effect()
  await Promise.resolve()
  await Promise.resolve()
}

function findByType(node: ReactNode, type: unknown): ReactElement | undefined {
  if (!node || typeof node !== 'object') return undefined
  if (Array.isArray(node)) {
    for (const child of node) {
      const found = findByType(child, type)
      if (found) return found
    }
    return undefined
  }
  const element = node as ReactElement<{ children?: ReactNode }>
  if (element.type === type) return element
  return findByType(element.props?.children, type)
}

function text(node: ReactNode): string {
  if (node == null || typeof node === 'boolean') return ''
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (Array.isArray(node)) return node.map(text).join('')
  return text((node as ReactElement<{ children?: ReactNode }>).props?.children)
}

beforeAll(async () => {
  ({ default: UnifiedRunPage } = await import('./page'))
})

beforeEach(() => {
  states = []
  stateIndex = 0
  effects = []
  search = new Map()
  variables = []
  variableForm = {
    values: {}, setValues: mock(() => {}), needsInput: false, isValid: true,
    fieldErrors: {}, validate: mock(() => true),
  }
  push.mockClear()
  getPublicAgent.mockClear()
  getWorkflow.mockClear()
  sendMessage.mockClear()
  stop.mockClear()
  useRun.mockClear()
  getPublicAgent.mockImplementation(() => Promise.resolve({
    name: 'Public agent', description: 'Helpful agent', opening_message: 'Welcome',
    suggested_questions: ['First question'], hide_tool_calls: true,
    created_by: { username: 'Ada' }, icon: '✨',
  }))
  getWorkflow.mockImplementation(() => Promise.resolve({ name: 'Workflow', description: 'Workflow description' }))
})

describe('UnifiedRunPage', () => {
  test('shows loading until params and metadata resolve, then renders the agent callbacks', async () => {
    const pending = Promise.withResolvers<{ id: string }>()
    let tree = render(pending.promise)
    expect(findByType(tree, 'loader')).toBeDefined()

    await runEffects()
    pending.resolve({ id: 'agent-1' })
    await Promise.resolve()
    tree = render(pending.promise)
    await runEffects()
    tree = render(pending.promise)

    expect(getPublicAgent).toHaveBeenCalledWith('agent-1')
    expect(useRun).toHaveBeenLastCalledWith(expect.objectContaining({ id: 'agent-1', type: 'agent' }))
    const container = findByType(tree, ChatContainer)
    expect(text(container?.props.emptyState)).toContain('Welcome')
    expect(container?.props).toMatchObject({ hideToolCalls: true })

    const input = findByType(tree, ChatInput)
    await input?.props.onSubmit('  Hello  ')
    expect(sendMessage).toHaveBeenCalledWith('  Hello  ')
    input?.props.onStop()
    expect(stop).toHaveBeenCalledTimes(1)

    const suggestion = findByType(container?.props.emptyState, 'button')
    await suggestion?.props.onClick()
    expect(sendMessage).toHaveBeenCalledWith('First question')
    container?.props.onSelectOption('Selected option')
    await Promise.resolve()
    expect(sendMessage).toHaveBeenCalledWith('Selected option')
  })

  test('shows translated API errors and navigates home', async () => {
    getPublicAgent.mockRejectedValueOnce(new ApiError(404, 'missing'))
    const params = Promise.resolve({ id: 'missing' })
    render(params)
    await runEffects()
    render(params)
    await runEffects()
    const tree = render(params)

    expect(text(tree)).toContain('run.notFound')
    findByType(tree, Button)?.props.onClick()
    expect(push).toHaveBeenCalledWith('/')
  })

  test('loads workflows, filters query variables, validates required input, and forwards debug options', async () => {
    search = new Map([['type', 'workflow'], ['debug', 'true']])
    variables = [
      { name: 'query', type: 'text', required: true },
      { name: 'items', type: 'array', required: true },
    ]
    variableForm = {
      ...variableForm,
      values: { items: '[]' },
      needsInput: true,
      isValid: false,
      validate: mock(() => false),
    }
    const params = Promise.resolve({ id: 'workflow-1' })
    render(params)
    await runEffects()
    render(params)
    await runEffects()
    const tree = render(params)

    expect(getWorkflow).toHaveBeenCalledWith('workflow-1')
    expect(useRun).toHaveBeenLastCalledWith(expect.objectContaining({
      id: 'workflow-1', type: 'workflow', isDebug: true, variables: { items: '[]' },
    }))
    const variableFormElement = findByType(tree, VariableForm)
    expect(variableFormElement?.props.variables).toEqual([variables[1]])

    await findByType(tree, ChatInput)?.props.onSubmit('Run it')
    expect(variableForm.validate).toHaveBeenCalledTimes(1)
    expect(sendMessage).not.toHaveBeenCalled()
  })
})
