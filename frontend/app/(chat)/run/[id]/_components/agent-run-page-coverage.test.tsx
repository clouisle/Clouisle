import { afterEach, beforeEach, describe, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'

const routerPush = mock(() => {})
const routerReplace = mock(() => {})
const reconnect = mock(() => {})
const stop = mock(() => {})
const sendMessage = mock(async () => {})
const submitAskUser = mock(async () => {})
const getPublicAgent = mock(async () => metadata)
const translate = (key: string) => key
const searchParams = new URLSearchParams('source=preview&conversation=existing')
const navigationSearchParams = {
  get: (key: string) => searchParams.get(key),
  toString: () => searchParams.toString(),
}
const router = { push: routerPush, replace: routerReplace }

type InputProps = {
  onSubmit: (text: string) => void | Promise<void>
}
type PendingAskUserProps = {
  pendingToolCallId?: string | null
  onSubmit: (answers: unknown) => void | Promise<void>
}
type RunOptions = {
  conversationId?: string
  onConversationChange: (conversationId: string) => void
}
type ButtonProps = {
  onClick?: () => void
  [key: string]: unknown
}

let renderer: ReactTestRenderer | undefined
let inputProps: InputProps | undefined
let pendingAskUserProps: PendingAskUserProps | undefined
let runOptions: RunOptions | undefined
let buttonProps: ButtonProps[] = []
let formConfig = {
  values: {} as Record<string, unknown>,
  needsInput: false,
  isValid: true,
  fieldErrors: {} as Record<string, string>,
  validate: mock(() => true),
}
let runState = {
  messages: [] as unknown[],
  isStreaming: false,
  isLoading: false,
  sendMessage,
  stop,
  conversationId: null as string | null,
  runId: null as string | null,
  runStatus: null as string | null,
  pendingAskUserToolCallId: null as string | null,
  submitAskUser,
  reconnect,
}

const metadata = {
  id: 'agent-1',
  name: 'Agent',
  description: 'Description',
  icon: 'A',
  avatar_url: '',
  opening_message: 'Welcome',
  suggested_questions: ['What can you do?'],
  powered_by_text: 'Acme Inc',
  variables: [
    { name: 'confirmed', type: 'checkbox', required: true, hidden: false },
    { name: 'items', type: 'array', required: true, hidden: false },
    { name: 'jsonItems', type: 'array', required: true, hidden: false },
    { name: 'invalidItems', type: 'array', required: true, hidden: false },
    { name: 'hidden', type: 'string', required: true, hidden: true },
    { name: 'optional', type: 'string', required: false, hidden: false },
  ],
  enable_attachments: false,
  attachment_config: null,
  hide_tool_calls: false,
  hide_message_actions: false,
  hide_reasoning: false,
  created_by: { username: 'owner' },
}

class MockApiError extends Error {
  code: number

  constructor(message: string, code: number) {
    super(message)
    this.code = code
  }
}

const Button = (props: ButtonProps) => {
  buttonProps.push(props)
  return null
}
const Alert = ({ children }: React.PropsWithChildren) => children
const AlertDescription = ({ children }: React.PropsWithChildren) => children
const AlertTitle = ({ children }: React.PropsWithChildren) => children
const AgentChatEmptyState = ({ suggestedQuestions = [], onSuggestedQuestion }: { suggestedQuestions?: string[]; onSuggestedQuestion: (question: string) => void }) => (
  React.createElement('div', null, suggestedQuestions.map((question) => React.createElement('button', {
    key: question,
    onClick: () => onSuggestedQuestion(question),
  })))
)
const AgentChatSurface = (props: Record<string, unknown>) => {
  inputProps = { onSubmit: props.onSubmit as InputProps['onSubmit'] }
  pendingAskUserProps = props.pendingAskUserToolCallId
    ? {
        pendingToolCallId: props.pendingAskUserToolCallId as string,
        onSubmit: props.onSubmitAskUser as PendingAskUserProps['onSubmit'],
      }
    : undefined
  const variables = props.variables as Array<{ hidden?: boolean }> | undefined
  const variablePanel = variables?.some((variable) => !variable.hidden)
    ? React.createElement('div', { className: 'rounded-t-lg border border-b-0 bg-muted/30 w-[70%]' })
    : null
  return React.createElement(React.Fragment, null, props.emptyState, variablePanel)
}
const useVariableForm = () => ({
  ...formConfig,
  setValues: mock(() => {}),
})
const useRun = (options: Record<string, unknown>) => {
  runOptions = options as unknown as RunOptions
  return runState
}
const extractVariables = (agent: { variables?: unknown[] } | null) => agent?.variables ?? []
const cn = (...values: unknown[]) => values.filter(Boolean).join(' ')

mock.module('next/navigation', () => ({ useRouter: () => router, useSearchParams: () => navigationSearchParams }))
mock.module('next-intl', () => ({ useTranslations: () => translate }))
mock.module('next/image', () => ({ default: () => null }))
mock.module('lucide-react', () => ({ AlertCircle: () => null, ChevronDown: () => null, ChevronUp: () => null, Loader2: () => null, RefreshCw: () => null, Sparkles: () => null }))
mock.module('@/lib/api', () => ({ ApiError: MockApiError, publicAgentsApi: { getPublicAgent } }))
mock.module('@/components/ui/button', () => ({ Button }))
mock.module('@/components/ui/alert', () => ({ Alert, AlertDescription, AlertTitle }))
mock.module('@/components/chat', () => ({ AgentChatEmptyState, AgentChatSurface, useVariableForm }))
mock.module('@/hooks/use-run', () => ({ useRun }))
mock.module('@/lib/utils/extract-variables', () => ({ extractVariables }))
mock.module('@/lib/utils', () => ({ cn }))

const { AgentRunPage } = await import('./agent-run-page')
globalThis.IS_REACT_ACT_ENVIRONMENT = true

async function renderPage() {
  await act(async () => {
    renderer = create(React.createElement(AgentRunPage, { id: 'agent-1' }))
    await Promise.resolve()
    await Promise.resolve()
  })
}

async function updatePage() {
  await act(async () => {
    renderer!.update(React.createElement(AgentRunPage, { id: 'agent-1' }))
    await Promise.resolve()
  })
}

beforeEach(() => {
  renderer = undefined
  inputProps = undefined
  pendingAskUserProps = undefined
  runOptions = undefined
  buttonProps = []
  formConfig = {
    values: {
      confirmed: false,
      items: ['one'],
      jsonItems: '["one"]',
      invalidItems: 'not-json',
    },
    needsInput: false,
    isValid: true,
    fieldErrors: {},
    validate: mock(() => true),
  }
  runState = {
    messages: [],
    isStreaming: false,
    isLoading: false,
    sendMessage,
    stop,
    conversationId: null,
    runId: null,
    runStatus: null,
    pendingAskUserToolCallId: null,
    submitAskUser,
    reconnect,
  }
  getPublicAgent.mockReset()
  getPublicAgent.mockResolvedValue(metadata)
  sendMessage.mockClear()
  submitAskUser.mockClear()
  reconnect.mockClear()
  stop.mockClear()
  routerPush.mockClear()
  routerReplace.mockClear()
})

afterEach(() => {
  renderer?.unmount()
})

describe('AgentRunPage uncovered durable-run paths', () => {
  test('loads metadata, counts required values, sends text, and preserves conversation query', async () => {
    await renderPage()

    expect(inputProps).toBeDefined()
    expect(runOptions?.conversationId).toBe('existing')

    const suggestedQuestion = renderer!.root.findAllByType('button').find((button) => button.props.onClick)
    expect(suggestedQuestion).toBeDefined()
    await act(async () => {
      suggestedQuestion!.props.onClick()
    })
    expect(sendMessage).toHaveBeenCalledWith('What can you do?')

    sendMessage.mockClear()
    await act(async () => {
      await inputProps!.onSubmit('  ')
    })
    expect(sendMessage).not.toHaveBeenCalled()

    await act(async () => {
      await inputProps!.onSubmit('hello')
    })
    expect(sendMessage).toHaveBeenCalledWith('hello')

    runOptions!.onConversationChange('conversation-1')
    expect(routerReplace).toHaveBeenCalledWith(
      '/run/agent-1?source=preview&conversation=conversation-1',
    )
  })

  test('reopens variables instead of sending when required input is invalid', async () => {
    await renderPage()
    formConfig.needsInput = true
    formConfig.isValid = false
    formConfig.validate = mock(() => false)
    await updatePage()

    await act(async () => {
      await inputProps!.onSubmit('hello')
    })

    expect(formConfig.validate).toHaveBeenCalled()
    expect(sendMessage).not.toHaveBeenCalled()
  })

  test('renders pending ask_user controls and reconnects an active run', async () => {
    await renderPage()
    runState = {
      ...runState,
      conversationId: 'conversation-1',
      runId: 'run-1',
      runStatus: 'waiting',
      pendingAskUserToolCallId: 'call-1',
    }
    await updatePage()

    expect(pendingAskUserProps?.pendingToolCallId).toBe('call-1')
    await act(async () => {
      await pendingAskUserProps!.onSubmit({ target: 'cloud' })
    })
    expect(submitAskUser).toHaveBeenCalledWith({ target: 'cloud' })

    const reconnectButton = buttonProps.find((props) => props.onClick)
    expect(reconnectButton).toBeDefined()
    reconnectButton!.onClick!()
    expect(reconnect).toHaveBeenCalled()
  })
  test('keeps the configure panel at the intended 70 percent width', async () => {
    metadata.variables = [{ name: 'query', type: 'string', required: true, hidden: false }]
    await renderPage()

    const panel = renderer!.root.find((node) => {
      const className = node.props?.className
      return typeof className === 'string' && className.includes('rounded-t-lg') && className.includes('bg-muted/30')
    })
    expect(panel.props.className).toContain('w-[70%]')
  })

  test('handles not-found metadata errors', async () => {
    getPublicAgent.mockRejectedValueOnce(new MockApiError('missing', 404))
    await renderPage()

    expect(renderer!.toJSON()).toBeDefined()
    expect(getPublicAgent).toHaveBeenCalledWith('agent-1')

    const backButton = buttonProps.find((props) => props.onClick)
    expect(backButton).toBeDefined()
    backButton!.onClick!()
    expect(routerPush).toHaveBeenCalledWith('/')
  })
})
