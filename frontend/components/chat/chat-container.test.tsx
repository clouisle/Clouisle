/** @jsxRuntime classic */
import { describe, expect, mock, test } from 'bun:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import type { ChatMessage, FilePart, MessagePart } from './types'

const messageProps: Array<Record<string, unknown>> = []
const artifactListProps: Array<{
  files: FilePart[]
  onOpenPreview?: (file: FilePart) => void
}> = []

mock.module('next-intl', () => ({
  useTranslations: () => (key: string, values?: Record<string, unknown>) => `${key}:${values?.count ?? ''}`,
}))
mock.module('lucide-react', () => ({ ArrowDown: () => <svg data-icon="arrow-down" /> }))
mock.module('@/components/ui/button', () => ({
  Button: ({ children, ...props }: React.ComponentProps<'button'>) => <button {...props}>{children}</button>,
}))
mock.module('./artifact-file-list', () => ({
  ArtifactFileList: (props: { files: FilePart[]; className?: string; onOpenPreview?: (file: FilePart) => void }) => {
    artifactListProps.push(props)
    return props.files.length > 0
      ? <aside data-artifact-file-list>{props.files.map((file) => <span key={file.path ?? file.filename}>{file.filename}</span>)}</aside>
      : null
  },
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
        {props.afterContent as React.ReactNode}
      </article>
    )
  },
}))


const { ChatContainer, computeUserMessageTicks, userMessagePreview } = await import('./chat-container')

function textMessage(id: string, role: ChatMessage['role'], text: string): ChatMessage {
  return { id, role, parts: [{ type: 'text', text }] }
}

function renderContainer(element: React.ReactElement) {
  messageProps.length = 0
  artifactListProps.length = 0
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
  test('forwards a custom loading label to the assistant placeholder', () => {
    const message: ChatMessage = { id: 'assistant-loading', role: 'assistant', parts: [], metadata: { isLoading: true } }
    renderContainer(<ChatContainer messages={[message]} isLoading loadingLabel="Queued" />)

    expect(messageProps[0].loadingLabel).toBe('Queued')
  })


  test('initially renders the newest batch and offers to load older messages', () => {
    const messages = Array.from({ length: 25 }, (_, index) => textMessage(`m${index + 1}`, 'assistant', `message ${index + 1}`))
    const html = renderContainer(<ChatContainer messages={messages} />)

    expect(messageProps.map((props) => (props.message as ChatMessage).id)).toEqual(messages.slice(5).map((message) => message.id))
    expect(html).toContain('message.loadOlderMessages:5')
    expect(messageProps.some((props) => (props.message as ChatMessage).id === 'm1')).toBe(false)
    expect(html).toContain('message 25')
  })
  test('renders each artifact list inside its owning assistant message', () => {
    const onOpenCodePreview = mock(() => {})
    const messages: ChatMessage[] = [
      {
        id: 'assistant-1',
        role: 'assistant',
        parts: [
          { type: 'text', text: 'Earlier answer' },
          { type: 'tool-call', toolCallId: 'artifact-1', toolName: 'Artifact', input: {}, state: 'done' },
          {
            type: 'tool-result',
            toolCallId: 'artifact-1',
            toolName: 'Artifact',
            output: { artifacts: [{ path: '/workspace/report.csv', url: '/api/old-report.csv', size: 10, content_type: 'text/csv' }] },
          },
        ],
      },
      {
        id: 'assistant-2',
        role: 'assistant',
        parts: [
          { type: 'text', text: 'Final answer' },
          { type: 'tool-call', toolCallId: 'artifact-2', toolName: 'artifact', input: {}, state: 'done' },
          {
            type: 'tool-result',
            toolCallId: 'artifact-2',
            toolName: 'artifact',
            output: {
              artifacts: [
                { path: '/workspace/report.csv', url: '/api/new-report.csv', size: 18, content_type: 'text/csv' },
                { path: '/workspace/summary.md', url: '/api/summary.md', contentType: 'text/markdown' },
              ],
            },
          },
        ],
      },
    ]

    const html = renderContainer(<ChatContainer messages={messages} onOpenCodePreview={onOpenCodePreview} />)
    expect(html.indexOf('report.csv')).toBeGreaterThan(html.indexOf('Earlier answer'))
    expect(html.indexOf('Final answer')).toBeGreaterThan(html.indexOf('report.csv'))
    expect(html.indexOf('summary.md')).toBeGreaterThan(html.indexOf('Final answer'))
    expect(messageProps[0].afterContent).toBeDefined()
    expect(messageProps[1].afterContent).toBeDefined()
    expect(artifactListProps).toHaveLength(2)
    expect(artifactListProps.map((props) => props.files.map((file) => file.url))).toEqual([
      ['/api/old-report.csv'],
      ['/api/new-report.csv', '/api/summary.md'],
    ])

    artifactListProps[0].onOpenPreview?.(artifactListProps[0].files[0])
    expect(onOpenCodePreview).toHaveBeenCalledWith({
      id: 'artifact:/workspace/report.csv',
      kind: 'artifact',
      file: artifactListProps[0].files[0],
    })
  })


  test('wraps role-specific message callbacks and forwards shared props', async () => {
    const onRegenerate = mock(() => {})
    const onEditMessage = mock(() => Promise.resolve())
    const onSwitchVersion = mock(() => {})
    const onSubmitAskUser = mock(async () => undefined)
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
        pendingAskUserToolCallId="ask-1"
        onSubmitAskUser={onSubmitAskUser}
        onOpenCodePreview={onOpenCodePreview}
        hideToolCalls
      />
    )

    await (messageProps[0].onEditMessage as (content: string) => Promise<void>)('edited')
    ;(messageProps[1].onRegenerate as () => void)()
    ;(messageProps[1].onSwitchVersion as (version: number) => void)(2)
    await (messageProps[0].onSubmitAskUser as (toolCallId: string, answers: Record<string, unknown>) => Promise<void>)('ask-1', { q: 'a' })

    expect(messageProps[0].onRegenerate).toBeUndefined()
    expect(messageProps[1].onEditMessage).toBeUndefined()
    expect(onEditMessage).toHaveBeenCalledWith('u1', 'edited')
    expect(onRegenerate).toHaveBeenCalledWith('a1')
    expect(onSwitchVersion).toHaveBeenCalledWith('a1', 2)
    expect(onSubmitAskUser).toHaveBeenCalledWith('ask-1', { q: 'a' })
    expect(messageProps.every((props) => props.hideToolCalls === true)).toBe(true)
    expect(messageProps.every((props) => props.pendingAskUserToolCallId === 'ask-1')).toBe(true)
    expect(messageProps.every((props) => props.onSubmitAskUser === onSubmitAskUser)).toBe(true)
    expect(messageProps.every((props) => props.onOpenCodePreview === onOpenCodePreview)).toBe(true)
  })
  test('withholds editing until a user message is persisted and the run is idle', () => {
    const onEditMessage = mock(() => Promise.resolve())
    const pendingMessage = {
      ...textMessage('user-pending', 'user', 'hello'),
      metadata: { pendingPersistence: true },
    }

    renderContainer(<ChatContainer messages={[pendingMessage]} onEditMessage={onEditMessage} />)
    expect(messageProps[0].onEditMessage).toBeUndefined()

    renderContainer(<ChatContainer messages={[textMessage('user-1', 'user', 'hello')]} isLoading onEditMessage={onEditMessage} />)
    expect(messageProps[0].onEditMessage).toBeUndefined()

    renderContainer(<ChatContainer messages={[textMessage('user-1', 'user', 'hello')]} isStreaming onEditMessage={onEditMessage} />)
    expect(messageProps[0].onEditMessage).toBeUndefined()

    renderContainer(<ChatContainer messages={[textMessage('user-1', 'user', 'hello')]} onEditMessage={onEditMessage} />)
    expect(typeof messageProps[0].onEditMessage).toBe('function')
  })


  test('renders the user message scale only when enabled', () => {
    const messages = [textMessage('u1', 'user', 'hello')]
    expect(renderContainer(<ChatContainer messages={messages} />)).not.toContain('data-user-message-scale')

    const html = renderContainer(<ChatContainer messages={messages} showUserMessageScale />)
    expect(html).toContain('data-user-message-scale')
    expect(html).toContain('pointer-events-none')
  })

  test('user message scale track aligns with the scroller top', () => {
    const messages = [textMessage('u1', 'user', 'hello')]
    const html = renderContainer(<ChatContainer messages={messages} showUserMessageScale headerInset />)
    const track = html.match(/<div data-user-message-scale[^>]*>/)?.[0] ?? ''
    expect(track).toContain('top-[60px]')
  })

  test('renders no scale ticks under SSR because positions come from measured layout', () => {
    const messages = [
      textMessage('u1', 'user', 'hello'),
      textMessage('a1', 'assistant', 'answer'),
      textMessage('u2', 'user', 'again'),
    ]
    const html = renderContainer(<ChatContainer messages={messages} showUserMessageScale />)
    expect(html).toContain('data-user-message-scale')
    expect(html).not.toContain('data-user-message-tick')
  })
})

describe('computeUserMessageTicks', () => {
  const ordinals: Record<string, number> = { u1: 1, u2: 2, u3: 3 }

  test('lays ticks out at a fixed 12px pitch, centered in the track', () => {
    const entries = [
      { id: 'u1', preview: 'hello' },
      { id: 'u2', preview: 'again' },
    ]

    // 400px track, 2 ticks → cluster 24px tall, centered at 188..212.
    expect(computeUserMessageTicks(entries, 400, ordinals, 'u2')).toEqual([
      { id: 'u1', y: 194, ordinal: 1, preview: 'hello', current: false },
      { id: 'u2', y: 206, ordinal: 2, preview: 'again', current: true },
    ])
  })

  test('marks only the currently in-view message as current', () => {
    const entries = [{ id: 'u1', preview: '' }, { id: 'u3', preview: '' }]
    expect(computeUserMessageTicks(entries, 600, ordinals, 'u3')).toEqual([
      { id: 'u1', y: 294, ordinal: 1, preview: '', current: false },
      { id: 'u3', y: 306, ordinal: 3, preview: '', current: true },
    ])
  })

  test('centers a single tick in the track when no current id is known', () => {
    const entries = [{ id: 'u1', preview: '' }]
    expect(computeUserMessageTicks(entries, 400, ordinals, null)).toEqual([
      { id: 'u1', y: 200, ordinal: 1, preview: '', current: false },
    ])
  })

  test('skips entries without a known user ordinal', () => {
    const entries = [{ id: 'unknown', preview: '' }, { id: 'u2', preview: '' }]

    expect(computeUserMessageTicks(entries, 400, ordinals, null)).toEqual([
      { id: 'u2', y: 206, ordinal: 2, preview: '', current: false },
    ])
  })

  test('compresses the pitch evenly when the list overflows the track', () => {
    const entries = Array.from({ length: 100 }, (_, index) => ({ id: `u${index + 1}`, preview: '' }))
    const ordinalsAll: Record<string, number> = {}
    for (let i = 0; i < 100; i += 1) ordinalsAll[`u${i + 1}`] = i + 1

    // 100 ticks at 12px = 1200px > 400px track → pitch compressed to 4px.
    const ticks = computeUserMessageTicks(entries, 400, ordinalsAll, null)
    expect(ticks).toHaveLength(100)
    expect(ticks[0].y).toBe(2)
    expect(ticks[1].y).toBe(6)
    expect(ticks[99].y).toBe(398)
    expect(new Set(ticks.map((tick) => tick.y)).size).toBe(100)
  })
})

describe('userMessagePreview', () => {
  test('joins text parts and trims whitespace', () => {
    expect(userMessagePreview({
      id: 'u1',
      role: 'user',
      parts: [
        { type: 'text', text: 'first' },
        { type: 'tool-call', toolCallId: 't1', toolName: 'search', input: {} },
        { type: 'text', text: 'second' },
      ],
    })).toBe('first second')
  })

  test('returns an empty string when a user message has no text parts', () => {
    expect(userMessagePreview({
      id: 'u1',
      role: 'user',
      parts: [{ type: 'image', url: 'https://example.test/a.png' }],
    })).toBe('')
  })
})
