/** @jsxRuntime classic */
import { describe, expect, mock, test } from 'bun:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import type { ChatMessage, MessagePart } from './types'

const messageProps: Array<Record<string, unknown>> = []

mock.module('next-intl', () => ({
  useTranslations: () => (key: string, values?: Record<string, unknown>) => `${key}:${values?.count ?? ''}`,
}))
mock.module('lucide-react', () => ({ ArrowDown: () => <svg data-icon="arrow-down" /> }))
mock.module('@/components/ui/button', () => ({
  Button: ({ children, ...props }: React.ComponentProps<'button'>) => <button {...props}>{children}</button>,
}))
mock.module('./message', () => ({
  Message: (props: Record<string, unknown>) => {
    messageProps.push(props)
    const message = props.message as ChatMessage
    return (
      <article data-message-id={message.id} data-streaming={String(props.isStreaming)}>
        {message.parts.map((part, index) => (
          props.renderPart
            ? <React.Fragment key={index}>{(props.renderPart as (part: MessagePart, index: number) => React.ReactNode)(part, index)}</React.Fragment>
            : part.type === 'text' ? <p key={index}>{part.text}</p> : null
        ))}
      </article>
    )
  },
}))

const { ChatContainer } = await import('./chat-container')

function textMessage(id: string, role: ChatMessage['role'], text: string): ChatMessage {
  return { id, role, parts: [{ type: 'text', text }] }
}

function renderContainer(element: React.ReactElement) {
  messageProps.length = 0
  return renderToStaticMarkup(element)
}

describe('ChatContainer', () => {
  test('renders the provided empty state instead of message rows', () => {
    const html = renderContainer(<ChatContainer messages={[]} className="custom-empty" emptyState={<span>No messages</span>} />)

    expect(html).toContain('No messages')
    expect(html).toContain('custom-empty')
    expect(messageProps).toHaveLength(0)
  })

  test('headerInset offsets the message scroller and empty state', () => {
    const messages = [textMessage('u1', 'user', 'hello')]
    const scrolled = renderContainer(<ChatContainer messages={messages} headerInset />)
    expect(scrolled).toContain('top-[60px]')

    const empty = renderContainer(<ChatContainer messages={[]} headerInset emptyState={<span>No messages</span>} />)
    expect(empty).toContain('pt-[60px]')
    expect(empty).toContain('No messages')
  })

  test('without headerInset the scroller spans the full viewport', () => {
    const messages = [textMessage('u1', 'user', 'hello')]
    const html = renderContainer(<ChatContainer messages={messages} />)
    expect(html).toContain('absolute inset-x-0 bottom-0 overflow-y-auto')
    expect(html).not.toContain('top-[60px]')
  })

  test('renders messages, custom parts, and marks only the latest message as streaming', () => {
    const messages = [
      textMessage('u1', 'user', 'hello'),
      textMessage('a1', 'assistant', 'answer'),
    ]

    const html = renderContainer(
      <ChatContainer
        messages={messages}
        isStreaming
        renderPart={(part) => part.type === 'text' ? <strong>{part.text.toUpperCase()}</strong> : null}
      />
    )

    expect(html).toContain('HELLO')
    expect(html).toContain('ANSWER')
    expect(messageProps.map((props) => props.isStreaming)).toEqual([false, true])
  })

  test('initially renders the newest batch and offers to load older messages', () => {
    const messages = Array.from({ length: 25 }, (_, index) => textMessage(`m${index + 1}`, 'assistant', `message ${index + 1}`))
    const html = renderContainer(<ChatContainer messages={messages} />)

    expect(messageProps.map((props) => (props.message as ChatMessage).id)).toEqual(messages.slice(5).map((message) => message.id))
    expect(html).toContain('message.loadOlderMessages:5')
    expect(messageProps.some((props) => (props.message as ChatMessage).id === 'm1')).toBe(false)
    expect(html).toContain('message 25')
  })

  test('wraps role-specific message callbacks and forwards shared props', async () => {
    const onRegenerate = mock(() => {})
    const onEditMessage = mock(() => Promise.resolve())
    const onSwitchVersion = mock(() => {})
    const onSelectOption = mock(() => {})
    const onOpenCodePreview = mock(() => {})
    const messages = [
      textMessage('u1', 'user', 'hello'),
      textMessage('a1', 'assistant', 'answer'),
    ]

    renderContainer(
      <ChatContainer
        messages={messages}
        onRegenerate={onRegenerate}
        onEditMessage={onEditMessage}
        onSwitchVersion={onSwitchVersion}
        onSelectOption={onSelectOption}
        onOpenCodePreview={onOpenCodePreview}
        hideToolCalls
      />
    )

    await (messageProps[0].onEditMessage as (content: string) => Promise<void>)('edited')
    ;(messageProps[1].onRegenerate as () => void)()
    ;(messageProps[1].onSwitchVersion as (version: number) => void)(2)
    ;(messageProps[0].onSelectOption as (option: string) => void)('yes')

    expect(messageProps[0].onRegenerate).toBeUndefined()
    expect(messageProps[1].onEditMessage).toBeUndefined()
    expect(onEditMessage).toHaveBeenCalledWith('u1', 'edited')
    expect(onRegenerate).toHaveBeenCalledWith('a1')
    expect(onSwitchVersion).toHaveBeenCalledWith('a1', 2)
    expect(onSelectOption).toHaveBeenCalledWith('yes')
    expect(messageProps.every((props) => props.hideToolCalls === true)).toBe(true)
    expect(messageProps.every((props) => props.onOpenCodePreview === onOpenCodePreview)).toBe(true)
  })
})
