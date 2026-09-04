/** @jsxRuntime classic */
import { describe, expect, mock, test } from 'bun:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import type { ChatMessage } from './types'

const chatContainerProps: Array<Record<string, unknown>> = []
const chatInputProps: Array<Record<string, unknown>> = []
const pendingAskUserProps: Array<Record<string, unknown>> = []
const variableFormProps: Array<Record<string, unknown>> = []

mock.module('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}))
mock.module('next/image', () => ({
  default: ({ alt }: { alt: string }) => <img alt={alt} />,
}))
mock.module('lucide-react', () => ({
  ChevronDown: () => <span data-icon="down" />,
  ChevronUp: () => <span data-icon="up" />,
  Sparkles: () => <span data-icon="sparkles" />,
}))
mock.module('@/lib/utils', () => ({
  cn: (...values: unknown[]) => values.filter(Boolean).join(' '),
}))
mock.module('@/components/ui/collapsible', () => ({
  Collapsible: ({ children }: React.PropsWithChildren) => <div data-collapsible>{children}</div>,
  CollapsibleContent: ({ children }: React.PropsWithChildren) => <div data-collapsible-content>{children}</div>,
  CollapsibleTrigger: ({ children, ...props }: React.PropsWithChildren) => <button {...props}>{children}</button>,
}))
mock.module('./chat-container', () => ({
  ChatContainer: (props: Record<string, unknown>) => {
    chatContainerProps.push(props)
    return <section data-chat-container>{props.emptyState as React.ReactNode}</section>
  },
}))
mock.module('./chat-input', () => ({
  ChatInput: (props: Record<string, unknown>) => {
    chatInputProps.push(props)
    return <div data-chat-input />
  },
}))
mock.module('./ask-user-form', () => ({
  PendingAskUserForm: (props: Record<string, unknown>) => {
    pendingAskUserProps.push(props)
    return <aside data-pending-ask-user />
  },
}))
mock.module('./variable-form', () => ({
  VariableForm: (props: Record<string, unknown>) => {
    variableFormProps.push(props)
    return <div data-variable-form />
  },
}))

const { AgentChatEmptyState, AgentChatSurface } = await import('./agent-chat-surface')

const messages: ChatMessage[] = [{ id: 'assistant-1', role: 'assistant', parts: [] }]
const onSubmit = mock(() => Promise.resolve())
const onVariablesChange = mock(() => {})

function renderSurface(overrides: Record<string, unknown> = {}) {
  chatContainerProps.length = 0
  chatInputProps.length = 0
  pendingAskUserProps.length = 0
  variableFormProps.length = 0
  return renderToStaticMarkup(
    <AgentChatSurface
      messages={messages}
      inputValue="draft"
      onInputChange={mock(() => {})}
      onSubmit={onSubmit}
      variables={[{ name: 'query', type: 'string', required: true, hidden: false }] as never}
      variableValues={{ query: 'value' }}
      onVariablesChange={onVariablesChange}
      {...overrides}
    />,
  )
}

describe('AgentChatSurface', () => {
  test('preserves the intended 70 percent configure-panel width', () => {
    const html = renderSurface()

    expect(chatContainerProps[0].messages).toBe(messages)
    expect(chatContainerProps[0].className).toContain('flex-1')
    expect(chatInputProps[0].value).toBe('draft')
    expect(chatInputProps[0].onSubmit).toBe(onSubmit)
    expect(variableFormProps[0].onChange).toBe(onVariablesChange)
    expect(html).toContain('max-w-3xl')
    expect(html).toContain('w-full')
    expect(html).toContain('w-[70%]')
    expect(html).not.toContain('w-full overflow-hidden rounded-t-lg')
  })

  test('prioritizes the pending ask_user form over variables', () => {
    renderSurface({
      pendingAskUserToolCallId: 'call-1',
      onSubmitAskUser: mock(() => Promise.resolve()),
      isStreaming: true,
    })

    expect(pendingAskUserProps[0]).toMatchObject({
      messages,
      pendingToolCallId: 'call-1',
      disabled: true,
    })
    expect(variableFormProps).toHaveLength(0)
  })
})

describe('AgentChatEmptyState', () => {
  test('renders the opening message and caps suggested questions at four', () => {
    const onSuggestedQuestion = mock(() => {})
    const html = renderToStaticMarkup(
      <AgentChatEmptyState
        agentName="Support"
        icon=""
        avatarUrl={null}
        openingMessage="Welcome"
        fallbackMessage="Fallback"
        suggestedQuestions={['One', 'Two', 'Three', 'Four', 'Five']}
        onSuggestedQuestion={onSuggestedQuestion}
      />,
    )

    expect(html).toContain('Welcome')
    expect(html).toContain('Four')
    expect(html).not.toContain('Five')
  })
})
