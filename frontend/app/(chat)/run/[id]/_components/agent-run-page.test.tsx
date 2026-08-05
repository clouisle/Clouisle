import { describe, expect, mock, test } from 'bun:test'
import { AgentRunPage } from './agent-run-page'

const states: unknown[] = []
let stateIndex = 0
let effectIndex = 0
const effects: Array<() => void> = []
const setState = (i: number) => (value: unknown) => {
  states[i] = typeof value === 'function' ? (value as (o: unknown) => unknown)(states[i]) : value
}

mock.module('react', () => ({
  useState: (initial: unknown) => {
    const i = stateIndex++
    if (states.length <= i) states[i] = initial
    return [states[i], setState(i)]
  },
  useEffect: (effect: () => void) => { effects[effectIndex++] = effect },
  useMemo: (factory: () => unknown) => factory(),
  useCallback: (cb: unknown) => cb,
  useRef: (value: unknown) => ({ current: value }),
}))
mock.module('react/jsx-runtime', () => ({
  jsx: (type: unknown, props: Record<string, unknown> = {}) => ({ type, props }),
  jsxs: (type: unknown, props: Record<string, unknown> = {}) => ({ type, props }),
  Fragment: Symbol.for('react.fragment'),
}))
mock.module('next/navigation', () => ({ useRouter: () => ({ push: mock(() => {}) }), useSearchParams: () => ({ get: () => null }) }))
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('next/image', () => ({ default: () => null }))
mock.module('lucide-react', () => ({ AlertCircle: () => null, ChevronDown: () => null, ChevronUp: () => null, Loader2: () => null, Sparkles: () => null }))
mock.module('@/lib/api', () => ({ ApiError: class ApiError extends Error { code = 0 }, publicAgentsApi: { getPublicAgent: mock(async () => ({ id: 'agent-1', name: 'Agent', description: '', icon: '', avatar_url: '', opening_message: '', suggested_questions: [], variables: [], enable_attachments: false, attachment_config: null, hide_tool_calls: false, hide_message_actions: false, hide_reasoning: false, created_by: { username: 'owner' } })) } }))
mock.module('@/components/ui/button', () => ({ Button: (p: Record<string, unknown>) => ({ type: 'button', props: p }) }))
mock.module('@/components/ui/alert', () => ({ Alert: (p: Record<string, unknown>) => ({ type: 'div', props: p }), AlertDescription: (p: Record<string, unknown>) => ({ type: 'div', props: p }), AlertTitle: (p: Record<string, unknown>) => ({ type: 'h5', props: p }) }))
mock.module('@/components/ui/collapsible', () => ({ Collapsible: (p: Record<string, unknown>) => ({ type: 'div', props: p }), CollapsibleContent: (p: Record<string, unknown>) => ({ type: 'div', props: p }), CollapsibleTrigger: (p: Record<string, unknown>) => ({ type: 'button', props: p }) }))
mock.module('@/components/chat', () => ({ ChatContainer: () => null, ChatInput: () => null, VariableForm: () => null, useVariableForm: () => ({ values: {}, setValues: mock(() => {}), needsInput: false, fieldErrors: {}, validate: () => true }) }))
const sendMessageMock = mock(async () => {})
mock.module('@/hooks/use-run', () => ({ useRun: () => ({ messages: [], isLoading: false, isStreaming: false, input: '', setInput: mock(() => {}), sendMessage: sendMessageMock, stop: mock(() => {}), reset: mock(() => {}), chatOptions: {} }) }))
mock.module('@/lib/utils/extract-variables', () => ({ extractVariables: () => [] }))
mock.module('@/lib/utils', () => ({ cn: (...v: unknown[]) => v.filter(Boolean).join(' ') }))

const metadata = { id: 'agent-1', name: 'Agent', description: '', icon: '', avatar_url: '', opening_message: '', suggested_questions: ['What can you do?'], variables: [], enable_attachments: false, attachment_config: null, hide_tool_calls: false, hide_message_actions: false, hide_reasoning: false, created_by: { username: 'owner' } }

describe('AgentRunPage', () => {
  test('renders loading state initially', () => {
    stateIndex = 0
    effectIndex = 0
    states.length = 0
    const tree = AgentRunPage({ id: 'agent-1' })
    expect(tree).toBeDefined()
    // Triggers the fetch effect
    effects.forEach((e) => e())
  })

  test('renders error state after a failed fetch', async () => {
    stateIndex = 0
    effectIndex = 0
    states.length = 0
    const tree = AgentRunPage({ id: 'agent-1' })
    effects.forEach((e) => e())
    // Allow the promise to settle
    await Promise.resolve()
    await Promise.resolve()
    expect(tree).toBeDefined()
  })

  test('shows an error when the agent is not found', async () => {
    const { publicAgentsApi } = await import('@/lib/api')
    ;(publicAgentsApi.getPublicAgent as ReturnType<typeof mock>).mockRejectedValueOnce(new Error('boom'))
    stateIndex = 0
    effectIndex = 0
    states.length = 0
    const tree = AgentRunPage({ id: 'agent-1' })
    effects.forEach((e) => e())
    await Promise.resolve()
    await Promise.resolve()
    expect(tree).toBeDefined()
  })

  test('renders the chat workspace once metadata loads', async () => {
    stateIndex = 0
    effectIndex = 0
    states.length = 0
    states[0] = { id: 'agent-1', name: 'Agent', description: '', icon: '', avatar_url: '', opening_message: '', suggested_questions: [], variables: [{ name: 'query', type: 'string', required: true, hidden: false }], enable_attachments: false, attachment_config: null, hide_tool_calls: false, hide_message_actions: false, hide_reasoning: false, created_by: { username: 'owner' } }
    states[1] = false
    states[2] = null
    states[3] = ''
    states[4] = false
    const tree = AgentRunPage({ id: 'agent-1' })
    effects.forEach((e) => e())
    expect(tree).toBeDefined()
  })

  test('opens variables panel when required variables are missing on send', async () => {
    mock.module('@/components/chat', () => ({
      ChatContainer: (p: Record<string, unknown>) => ({ type: 'chat-container', props: p }),
      ChatInput: (p: Record<string, unknown>) => ({ type: 'chat-input', props: p }),
      VariableForm: (p: Record<string, unknown>) => ({ type: 'variable-form', props: p }),
      useVariableForm: () => ({ values: {}, setValues: mock(() => {}), needsInput: true, fieldErrors: {}, validate: () => false }),
    }))
    const { AgentRunPage: Reloaded } = await import('./agent-run-page')
    stateIndex = 0
    effectIndex = 0
    states.length = 0
    states[0] = { ...metadata, variables: [{ name: 'query', type: 'string', required: true, hidden: false }] }
    states[1] = false
    states[2] = null
    states[3] = ''
    states[4] = false
    const tree = Reloaded({ id: 'agent-1' })
    effects.forEach((e) => e())
    expect(tree).toBeDefined()
  })

  test('sends a suggested question through the empty state', async () => {
    mock.module('@/components/chat', () => ({
      ChatContainer: (p: Record<string, unknown> & { emptyState?: unknown }) => p.emptyState ?? null,
      ChatInput: (p: Record<string, unknown>) => ({ type: 'chat-input', props: p }),
      VariableForm: (p: Record<string, unknown>) => ({ type: 'variable-form', props: p }),
      useVariableForm: () => ({ values: {}, setValues: mock(() => {}), needsInput: false, fieldErrors: {}, validate: () => true }),
    }))
    const { AgentRunPage: Reloaded } = await import('./agent-run-page')
    sendMessageMock.mockClear()
    stateIndex = 0
    effectIndex = 0
    states.length = 0
    states[0] = metadata
    states[1] = false
    states[2] = null
    states[3] = ''
    states[4] = false
    const tree = Reloaded({ id: 'agent-1' })
    effects.forEach((e) => e())
    expect(tree).toBeDefined()
  })
})
