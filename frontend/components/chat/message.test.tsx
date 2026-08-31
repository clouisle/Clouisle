import { afterEach, describe, expect, mock, test } from 'bun:test'
import { Window } from 'happy-dom'
import React, { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { renderToStaticMarkup } from 'react-dom/server'

const window = new Window({ url: 'http://localhost' })
Object.assign(globalThis, {
  window,
  document: window.document,
  navigator: window.navigator,
  HTMLElement: window.HTMLElement,
  HTMLTextAreaElement: window.HTMLTextAreaElement,
  MutationObserver: window.MutationObserver,
  NodeFilter: window.NodeFilter,
  Event: window.Event,
  CustomEvent: window.CustomEvent,
  localStorage: window.localStorage,
})
;(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true

const Icon = (props: React.ComponentProps<'svg'>) => <svg {...props} />
const openLightbox = mock(() => {})
const codeToTokens = mock(async () => ({ tokens: [] }))
let lastStreamdownProps: Record<string, unknown> = {}
let lastDialogProps: Record<string, unknown> = {}
let rendersCodeActions = true

mock.module('next-intl', () => ({
  useLocale: () => 'en-US',
  useTranslations: (namespace?: string) => (key: string, values?: Record<string, unknown>) => {
    const prefix = namespace ? `${namespace}.` : ''
    const suffix = values
      ? ` ${Object.entries(values).map(([name, value]) => `${name}=${String(value)}`).join(' ')}`
      : ''
    return `${prefix}${key}${suffix}`
  },
}))
mock.module('lucide-react', () => ({
  AlertTriangle: Icon,
  ArrowDown: Icon,
  ArrowUp: Icon,
  Brain: Icon,
  Check: Icon,
  ChevronLeft: Icon,
  ChevronRight: Icon,
  Copy: Icon,
  Eye: Icon,
  FileIcon: Icon,
  ImageIcon: Icon,
  Loader2: Icon,
  Pencil: Icon,
  Plus: Icon,
  RefreshCw: Icon,
  SearchIcon: Icon,
  SparklesIcon: Icon,
  Square: Icon,
  StopCircle: Icon,
  ThumbsDown: Icon,
  ThumbsUp: Icon,
  Timer: Icon,
  Upload: Icon,
  Volume2: Icon,
  Wrench: Icon,
  X: Icon,
}))
mock.module('@/lib/utils', () => ({ cn: (...classes: unknown[]) => classes.filter(Boolean).join(' ') }))
mock.module('@/components/ui/popover', () => ({ Popover: ({ children }: { children: React.ReactNode }) => <>{children}</>, PopoverContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>, PopoverTrigger: ({ render }: { render: React.ReactNode }) => <>{render}</> }))
mock.module('@/components/ui/dialog', () => ({ Dialog: (props: { children: React.ReactNode }) => { lastDialogProps = props as unknown as Record<string, unknown>; return <>{props.children}</> }, DialogContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>, DialogHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>, DialogTitle: ({ children }: { children: React.ReactNode }) => <h2>{children}</h2> }))
mock.module('@/components/ui/button', () => ({ Button: ({ children, ...props }: React.ComponentProps<'button'>) => <button {...props}>{children}</button> }))
const Textarea = React.forwardRef<HTMLTextAreaElement, React.ComponentProps<'textarea'>>(function Textarea({ onChange, ...props }, ref) {
  return <textarea ref={ref} {...props} onInput={onChange} />
})
mock.module('@/components/ui/textarea', () => ({ Textarea }))
mock.module('@/components/ai-elements/message', () => ({
  Message: ({ children }: { children: React.ReactNode }) => <article>{children}</article>,
  MessageAction: ({ children, tooltip, ...props }: React.ComponentProps<'button'> & { tooltip: string }) => <button type="button" aria-label={tooltip} {...props}>{children}</button>,
  MessageActions: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  MessageAttachment: ({ data }: { data: { filename?: string } }) => <span>{data.filename}</span>,
  MessageAttachments: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  MessageContent: ({ children }: { children: React.ReactNode }) => <section>{children}</section>,
}))
mock.module('@/components/ai-elements/chain-of-thought', () => ({
  ChainOfThought: ({ children, isStreaming, open, onOpenChange }: { children: React.ReactNode; isStreaming?: boolean; open?: boolean; onOpenChange?: (open: boolean) => void }) => <div data-chat-thought-process="true" data-streaming={String(Boolean(isStreaming))} data-open={String(Boolean(open))}><button type="button" onClick={() => onOpenChange?.(!open)}>toggle reasoning</button>{children}</div>,
  ChainOfThoughtContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  ChainOfThoughtHeader: ({ title }: { title: string }) => <h3>{title}</h3>,
  ChainOfThoughtStep: ({ children, label, status }: { children?: React.ReactNode; label: React.ReactNode; status?: string }) => <div data-step-status={status}>{label}{children}</div>,
}))
mock.module('@/components/ai-elements/tool', () => ({
  Tool: ({ children, defaultOpen, className }: { children: React.ReactNode; defaultOpen?: boolean; className?: string }) => <div data-chat-tool-node="true" data-tool-default-open={String(Boolean(defaultOpen))} className={className}>{children}</div>,
  ToolContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  ToolHeader: ({ title, state }: { title: string; state?: string }) => <h4 data-tool-state={state}>{title}</h4>,
  ToolInput: ({ input }: { input: unknown }) => <pre>{JSON.stringify(input)}</pre>,
  ToolOutput: ({ output, errorText }: { output?: unknown; errorText?: string }) => <pre>{errorText ?? JSON.stringify(output)}</pre>,
}))
mock.module('./image-lightbox', () => ({ ImageLightbox: ({ src, alt, isOpen }: { src: string; alt: string; isOpen: boolean }) => isOpen ? <div role="dialog" aria-label={alt}>{src}</div> : null, useLightbox: () => ({ isOpen: false, imageSrc: '', imageAlt: '', openLightbox, closeLightbox: mock(() => {}) }) }))
mock.module('./message-parts', () => ({ SourceContent: ({ sources }: { sources: unknown[] }) => <aside>sources:{sources.length}</aside> }))
mock.module('./user-input-request-card', () => ({ UserInputRequestCard: ({ question, options, onSelectOption }: { question: string; options: string[]; onSelectOption?: (option: string) => void }) => <fieldset><legend>{question}</legend>{options.map((option) => <button key={option} onClick={() => onSelectOption?.(option)}>{option}</button>)}</fieldset> }))
mock.module('streamdown', () => ({
  Block: ({ content }: { content: string }) => (
    <div data-streamdown="code-block">
      <div data-streamdown="code-block-header"><span /></div>
      {rendersCodeActions && <div data-streamdown="code-block-actions" />}
      <pre data-streamdown="code-block-body">{content}</pre>
    </div>
  ),
  Streamdown: (props: {
    children: React.ReactNode
    isAnimating?: boolean
    BlockComponent?: React.ComponentType<{
      content: string
      index: number
      shouldParseIncompleteMarkdown: boolean
      isIncomplete: boolean
    }>
  }) => {
    lastStreamdownProps = props as unknown as Record<string, unknown>
    const content = String(props.children)
    const isCodeFence = /^ {0,3}(?:`{3,}|~{3,})/.test(content)
    const hasClosingFence = /(?:^|\n) {0,3}(?:`{3,}|~{3,})[ \t]*$/.test(content)
    return <div>{props.BlockComponent && isCodeFence ? <props.BlockComponent content={content} index={0} shouldParseIncompleteMarkdown={false} isIncomplete={Boolean(props.isAnimating && !hasClosingFence)} /> : props.children}</div>
  },
  defaultRehypePlugins: { sanitize: 'sanitize', harden: 'harden' },
}))
mock.module('shiki', () => ({ bundledLanguages: { javascript: {} }, codeToTokens }))
mock.module('@streamdown/math', () => ({ createMathPlugin: () => ({}) }))

// Dynamic import is required so Bun module mocks are registered before Message evaluates.
const { Message } = await import('./message')

const roots: Root[] = []
afterEach(() => {
  for (const root of roots.splice(0)) act(() => root.unmount())
  document.body.replaceChildren()
  openLightbox.mockClear()
  rendersCodeActions = true
})

function render(element: React.ReactElement) {
  const container = document.body.appendChild(document.createElement('div'))
  const root = createRoot(container)
  roots.push(root)
  act(() => root.render(element))
  return container
}

function button(container: HTMLElement, label: string) {
  return [...container.querySelectorAll('button')].find((item) => item.textContent === label || item.getAttribute('aria-label') === label)!
}

describe('message rendering', () => {
  test('renders preserved error note, stopped marker, token stats, and assistant actions', () => {
    const html = renderToStaticMarkup(<Message
      message={{
        id: 'assistant-1',
        role: 'assistant',
        metadata: {
          isError: true,
          preservedPartialProgress: true,
          errorMessage: 'Network fell over',
          isManuallyStopped: true,
          usage: {
            prompt_tokens: 1200,
            completion_tokens: 34,
            total_tokens: 1234,
            cache_read_tokens: 900,
            cache_creation_tokens: 100,
            total_input_tokens: 1200,
          },
          timing: { first_token_ms: 250, duration_ms: 1234, tokens_per_second: 12.5 },
        },
        parts: [{ type: 'text', text: 'Partial answer [[cite:1]]' }],
      }}
      showFeedback
      onRegenerate={() => {}}
    />)

    expect(html).toContain('Partial answer')
    expect(html).toContain('Network fell over')
    expect(html).toContain('chat.message.manuallyStopped')
    expect(html).toContain('1,200')
    expect(html).toContain('1.2s')
    expect(html).toContain('chat.message.cachedTokens')
    expect(html).toContain('chat.message.cacheCreationTokens')
    expect(html).toContain('900')
    expect(html).toContain('100')
    expect(html).toContain('chat.message.helpful')
    expect(html).toContain('chat.message.regenerate')
  })

  test('renders user attachments and edit/version actions for editable user messages', () => {
    const html = renderToStaticMarkup(<Message
      message={{
        id: 'user-1',
        role: 'user',
        versionNumber: 2,
        versionCount: 3,
        parts: [
          { type: 'text', text: 'Please revise' },
          { type: 'file', filename: 'brief.txt', url: '/brief.txt', mimeType: 'text/plain' },
        ],
      }}
      onEditMessage={async () => {}}
      onSwitchVersion={() => {}}
    />)

    expect(html).toContain('Please revise')
    expect(html).toContain('brief.txt')
    expect(html).toContain('2/3')
    expect(html).toContain('chat.message.edit')
  })

  test('hides duplicated error text while keeping the error boundary visible', () => {
    const html = renderToStaticMarkup(<Message
      message={{
        id: 'assistant-error',
        role: 'assistant',
        metadata: { isError: true, errorMessage: 'network failed' },
        parts: [{ type: 'text', text: 'network failed' }],
      }}
    />)

    expect(html).toContain('network failed')
    expect(html).toContain('text-destructive')
    expect(html).not.toContain('<pre>network failed</pre>')
  })

  test('renders tool calls in content only when chain of thought is not hidden', () => {
    const parts = [
      { type: 'tool-call' as const, toolCallId: 'tool-1', toolName: 'search', input: { q: 'coverage' }, state: 'done' as const },
      { type: 'tool-result' as const, toolCallId: 'tool-1', toolName: 'search', output: { ok: true } },
    ]

    const visible = renderToStaticMarkup(<Message message={{ id: 'tool-visible', role: 'assistant', parts }} />)
    const hidden = renderToStaticMarkup(<Message
      message={{
        id: 'tool-hidden',
        role: 'assistant',
        parts: [{ type: 'reasoning' as const, text: 'thinking', state: 'done' as const }, ...parts],
      }}
      hideToolCalls
    />)

    expect(visible).toContain('search')
    expect(visible).toContain('&quot;q&quot;:&quot;coverage&quot;')
    expect(hidden).not.toContain('&quot;q&quot;:&quot;coverage&quot;')
    expect(hidden).toContain('chat.reasoning.thought')
  })

  test('renders iteration cap and stopped markers once', () => {
    const html = renderToStaticMarkup(<Message
      message={{
        id: 'assistant-marker',
        role: 'assistant',
        parts: [
          { type: 'text', text: 'chat.message.iterationCapReached' },
          { type: 'iteration-cap-reached' },
          { type: 'stopped' },
        ],
      }}
    />)

    expect(html.match(/chat\.message\.iterationCapReached/g)?.length).toBe(1)
    expect(html).toContain('chat.message.manuallyStopped')
  })

  test('shows assistant actions for reasoning-only messages and respects hide flags', () => {
    const parts = [{ type: 'reasoning' as const, text: 'Only thinking', state: 'done' as const }]
    const onRegenerate = mock(() => {})

    const visible = renderToStaticMarkup(<Message
      message={{ id: 'reasoning-only', role: 'assistant', parts }}
      onRegenerate={onRegenerate}
    />)
    expect(visible).toContain('chat.message.regenerate')
    expect(visible).toContain('chat.message.copy')

    // hideReasoning hides the chain-of-thought panel, not the actions
    const noChain = renderToStaticMarkup(<Message
      message={{ id: 'reasoning-hidden', role: 'assistant', parts }}
      hideReasoning
      onRegenerate={onRegenerate}
    />)
    expect(noChain).toContain('chat.message.regenerate')

    // hideMessageActions suppresses the bar entirely
    const noActions = renderToStaticMarkup(<Message
      message={{ id: 'actions-hidden', role: 'assistant', parts }}
      hideMessageActions
      onRegenerate={onRegenerate}
    />)
    expect(noActions).not.toContain('chat.message.regenerate')
    expect(noActions).not.toContain('chat.message.copy')
  })
})

  test('renders inserted content before message actions', () => {
    const html = renderToStaticMarkup(<Message
      message={{ id: 'artifact-order', role: 'assistant', parts: [{ type: 'text', text: 'Answer' }] }}
      afterContent={<div data-artifact-marker>files</div>}
      onRegenerate={() => {}}
    />)

    expect(html.indexOf('data-artifact-marker')).toBeGreaterThan(-1)
    expect(html.indexOf('data-artifact-marker')).toBeLessThan(html.indexOf('chat.message.regenerate'))
  })

describe('message behavior', () => {
  test('switches versions and forwards assistant actions', () => {
    const onSwitchVersion = mock(() => {})
    const onRegenerate = mock(() => {})
    const onFeedback = mock(() => {})
    const container = render(<Message
      message={{ id: 'assistant-actions', role: 'assistant', versionNumber: 2, versionCount: 3, parts: [{ type: 'text', text: 'Answer' }] }}
      onSwitchVersion={onSwitchVersion}
      onRegenerate={onRegenerate}
      onFeedback={onFeedback}
      showFeedback
    />)
    const versionButtons = [...container.querySelectorAll('button')].filter((item) => !item.getAttribute('aria-label'))

    act(() => versionButtons[0].click())
    act(() => versionButtons[1].click())
    act(() => button(container, 'chat.message.regenerate').click())
    act(() => button(container, 'chat.message.helpful').click())
    act(() => button(container, 'chat.message.notHelpful').click())

    expect(onSwitchVersion.mock.calls).toEqual([[0], [2]])
    expect(onRegenerate).toHaveBeenCalledTimes(1)
    expect(onFeedback.mock.calls).toEqual([['positive'], ['negative']])
  })

  test('edits user text with save and escape boundaries', async () => {
    const onEditMessage = mock(async () => {})
    const container = render(<Message
      message={{ id: 'user-edit', role: 'user', parts: [{ type: 'text', text: 'Original' }] }}
      onEditMessage={onEditMessage}
    />)

    act(() => button(container, 'chat.message.edit').click())
    const textarea = container.querySelector('textarea')!
    expect(textarea.value).toBe('Original')
    expect(button(container, 'chat.message.saveEdit').disabled).toBe(true)

    act(() => {
      Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value')!.set!.call(textarea, '  Revised  ')
      textarea.dispatchEvent(new window.Event('input', { bubbles: true }))
    })
    await act(async () => button(container, 'chat.message.saveEdit').click())
    expect(onEditMessage).toHaveBeenCalledWith('Revised')
    expect(container.querySelector('textarea')).toBeNull()

    act(() => button(container, 'chat.message.edit').click())
    act(() => container.querySelector('textarea')!.dispatchEvent(new window.KeyboardEvent('keydown', { key: 'Escape', bubbles: true })))
    expect(container.querySelector('textarea')).toBeNull()
  })

  test('routes sources, files, images, media, options, and boundary markers', () => {
    const onSelectOption = mock(() => {})
    const html = renderToStaticMarkup(<Message
      message={{
        id: 'mixed',
        role: 'assistant',
        parts: [
          { type: 'source-url', url: 'https://example.test', title: 'Example' },
          { type: 'source-document', documentName: 'Guide', content: 'Citation' },
          { type: 'file', filename: 'hidden.pdf', url: '/hidden.pdf' },
          { type: 'image', url: '/uploaded.png', alt: 'Uploaded chart' },
          { type: 'media-result', output: { kind: 'media.video', success: true, prompt: 'Demo', status: 'processing', progress: 0.42 } },
          { type: 'user-input-request', question: 'Choose one', options: ['Alpha', 'Beta'] },
          { type: 'truncated' },
        ],
      }}
      onSelectOption={onSelectOption}
    />)

    expect(html).toContain('sources:2')
    expect(html).not.toContain('hidden.pdf')
    expect(html).toContain('alt="Uploaded chart"')
    expect(html).toContain('chat.message.videoProcessing')
    expect(html).toContain('chat.message.progress')
    expect(html).toContain('Choose one')
    expect(html).toContain('chat.message.outputTruncated')

    const container = render(<Message
      message={{ id: 'option', role: 'assistant', parts: [{ type: 'user-input-request', question: 'Choose one', options: ['Alpha', 'Beta'] }] }}
      onSelectOption={onSelectOption}
    />)
    act(() => button(container, 'Beta').click())
    expect(onSelectOption).toHaveBeenCalledWith('Beta')
  })


  test('renders tool errors, artifact metadata without file cards, MCP results, and media failures', () => {
    const html = renderToStaticMarkup(<Message message={{
      id: 'tools',
      role: 'assistant',
      parts: [
        { type: 'tool-call', toolCallId: 'error', toolName: 'Failing tool', input: {}, state: 'error' },
        { type: 'tool-result', toolCallId: 'error', toolName: 'Failing tool', output: 'bad output', isError: true },
        { type: 'tool-call', toolCallId: 'artifact', toolName: 'Exporter', input: {}, state: 'done' },
        { type: 'tool-result', toolCallId: 'artifact', toolName: 'Exporter', output: { artifacts: [{ url: '/report.csv', path: '/tmp/report.csv' }, { path: '/tmp/missing.txt' }] } },
        { type: 'mcp-tool-call', toolCallId: 'mcp', serverName: 'docs', toolName: 'lookup', input: { id: 7 }, state: 'done' },
        { type: 'mcp-tool-result', toolCallId: 'mcp', serverName: 'docs', toolName: 'lookup', output: { found: true } },
        { type: 'media-result', output: { kind: 'media.image', success: false, prompt: 'Diagram', images: [], error: 'Generation failed' } },
      ],
    }} />)

    expect(html).toContain('chat.message.toolExecutionFailed')
    expect(html).not.toContain('artifacts:report.csv')
    expect(html).toContain('&quot;/report.csv&quot;')
    expect(html).toContain('docs/lookup')
    expect(html).toContain('&quot;found&quot;:true')
    expect(html).toContain('Generation failed')
  })

  test('opens uploaded and generated images through the lightbox callback', () => {
    const container = render(<Message message={{
      id: 'images',
      role: 'assistant',
      parts: [
        { type: 'image', url: '/uploaded.png', alt: 'Uploaded chart' },
        { type: 'media-result', output: { kind: 'media.image', success: true, prompt: 'Generated chart', images: [{ image: { url: '/generated.png' } }] } },
      ],
    }} />)

    act(() => button(container, 'chat.message.openCodePreview: Uploaded chart').click())
    act(() => button(container, 'chat.message.openCodePreview: Generated chart').click())
    expect(openLightbox.mock.calls).toEqual([
      ['/uploaded.png', 'Uploaded chart'],
      ['/generated.png', 'Generated chart'],
    ])
  })

  test('shows accessible loading and standalone error states without actions', () => {
    const loading = renderToStaticMarkup(<Message message={{ id: 'loading', role: 'assistant', metadata: { isLoading: true }, parts: [] }} />)
    const error = renderToStaticMarkup(<Message message={{ id: 'error', role: 'assistant', metadata: { isError: true }, parts: [] }} />)
    const streaming = renderToStaticMarkup(<Message
      message={{ id: 'streaming', role: 'assistant', parts: [{ type: 'text', text: 'In progress' }] }}
      isStreaming
      onRegenerate={() => {}}
    />)

    expect(loading).toContain('chat.message.thinking')
    expect(error).toContain('chat.message.error')
    expect(error).toContain('text-destructive')
    expect(streaming).not.toContain('chat.message.regenerate')
    expect(streaming).not.toContain('chat.message.copy')
  })
  test('uses a custom label for a loading placeholder', () => {
    const html = renderToStaticMarkup(<Message
      message={{ id: 'queued', role: 'assistant', metadata: { isLoading: true }, parts: [] }}
      loadingLabel="chat.message.runStatusQueued"
    />)

    expect(html).toContain('chat.message.runStatusQueued')
    expect(html).not.toContain('chat.message.thinking')
  })


  test('renders the error code badge with the conversation id for diagnosability', () => {
    const markup = renderToStaticMarkup(<Message
      message={{ id: 'error', role: 'assistant', metadata: { isError: true, errorMessage: 'Unknown error', errorCode: 1000 }, parts: [] }}
      conversationId="conv-123"
    />)

    expect(markup).toContain('Unknown error')
    expect(markup).toContain('chat.message.errorCode')
    expect(markup).toContain('1000')
    expect(markup).toContain('chat.message.conversationId')
    expect(markup).toContain('conv-123')
  })

  test('renders thought process nodes and maps task and tool states', () => {
    const onOpenChange = mock(() => {})
    const container = render(<Message
      message={{
        id: 'reasoning-states',
        role: 'assistant',
        parts: [
          { type: 'task', taskType: 'rag', state: 'completed', info: 3 },
          { type: 'task', taskType: 'compression', state: 'running', info: { trigger: 'context_length_error' } },
          { type: 'reasoning', text: 'Inspecting evidence', state: 'streaming' },
          { type: 'tool-call', toolCallId: 'running', toolName: 'search', toolDisplayName: 'Web search', input: { q: 'docs' }, state: 'running' },
          { type: 'tool-result', toolCallId: 'running', toolName: 'search', output: { hits: 2 } },
          { type: 'tool-call', toolCallId: 'failed', toolName: 'broken', input: {}, state: 'error' },
          { type: 'mcp-tool-call', toolCallId: 'pending', serverName: 'repo', toolName: 'read', input: {}, state: 'pending' },
          { type: 'mcp-tool-result', toolCallId: 'pending', serverName: 'repo', toolName: 'read', output: 'waiting' },
          { type: 'task', taskType: 'generating', state: 'error' },
        ],
      }}
      chainOfThoughtOpen
      onChainOfThoughtOpenChange={onOpenChange}
    />)

    expect(container.textContent).toContain('chat.task.foundSources')
    expect(container.textContent).toContain('chat.task.compressingContextReactive')
    expect(container.textContent).toContain('Web search')
    expect(container.textContent).toContain('broken')
    expect(container.textContent).toContain('repo/read')
    expect(container.textContent).toContain('chat.task.generating')
    expect([...container.querySelectorAll('[data-step-status]')].map((item) => item.getAttribute('data-step-status'))).toEqual(['complete', 'active', 'active', 'error'])
    expect(container.querySelector('[data-streaming="true"]')).not.toBeNull()
    expect([...container.querySelectorAll('[data-tool-state]')].map((item) => item.getAttribute('data-tool-state'))).toEqual(['input-available', 'output-error', 'input-streaming'])

    act(() => button(container, 'toggle reasoning').click())
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })

  test('renders compression at its original reasoning timeline position', () => {
    const container = render(<Message
      message={{
        id: 'timeline-order',
        role: 'assistant',
        parts: [
          { type: 'reasoning', text: 'before compression', state: 'done', duration: 1000 },
          {
            type: 'task',
            taskType: 'compression',
            state: 'completed',
            info: {
              before_tokens: 100,
              after_tokens: 50,
              summary_turns: 1,
              summary_source_tokens: 90000,
              summary_result_tokens: 1000,
              summary_saved_tokens: 89000,
            },
          },
          { type: 'reasoning', text: 'after compression', state: 'done', duration: 1000 },
        ],
      }}
      chainOfThoughtOpen
    />)

    expect([...container.querySelectorAll('[data-step-status]')].map((step) => step.textContent)).toEqual([
      expect.stringContaining('before compression'),
      expect.stringContaining('chat.task.compressionCompletedProactiveSummary before=90000 after=1000 saved=89000 count=1'),
      expect.stringContaining('after compression'),
    ])
  })
  test('renders repeated reasoning blocks at their original timeline positions', () => {
    const html = renderToStaticMarkup(<Message
      message={{
        id: 'alternating-timeline',
        role: 'assistant',
        parts: [
          { type: 'reasoning', text: 'Repeated thought', state: 'done', duration: 1000 },
          { type: 'text', text: 'Answer A', state: 'done' },
          { type: 'tool-call', toolCallId: 'timeline-tool', toolName: 'lookup', toolDisplayName: 'Lookup', input: {}, state: 'done' },
          { type: 'tool-result', toolCallId: 'timeline-tool', toolName: 'lookup', output: { answer: 'A' } },
          { type: 'reasoning', text: 'Repeated thought', state: 'done', duration: 2000 },
          { type: 'text', text: 'Answer B', state: 'done' },
        ],
      }}
    />)

    const firstReasoning = html.indexOf('Repeated thought')
    const tool = html.indexOf('Lookup')
    const secondReasoning = html.lastIndexOf('Repeated thought')
    expect(firstReasoning).toBeGreaterThanOrEqual(0)
    expect(secondReasoning).toBeGreaterThan(firstReasoning)
    expect(html.indexOf('Answer A')).toBeGreaterThan(firstReasoning)
    expect(tool).toBeGreaterThan(html.indexOf('Answer A'))
    expect(secondReasoning).toBeGreaterThan(tool)
    expect(html.indexOf('Answer B')).toBeGreaterThan(secondReasoning)
    expect(html.match(/Repeated thought/g)).toHaveLength(2)
    expect(html.match(/data-chat-thought-process="true"/g)).toHaveLength(2)
  })

  test('keeps each tool execution inside its thought process', () => {
    const container = render(<Message
      message={{
        id: 'nested-tool-process',
        role: 'assistant',
        parts: [
          { type: 'reasoning', text: 'Inspecting evidence', state: 'done', duration: 1000 },
          { type: 'tool-call', toolCallId: 'nested-tool', toolName: 'lookup', toolDisplayName: 'Lookup', input: { query: 'docs' }, state: 'done' },
          { type: 'tool-result', toolCallId: 'nested-tool', toolName: 'lookup', output: { ok: true } },
          { type: 'text', text: 'Final answer', state: 'done' },
        ],
      }}
    />)

    const thought = container.querySelector('[data-chat-thought-process="true"]')
    const tool = thought?.querySelector('[data-chat-tool-node="true"]')
    expect(thought).not.toBeNull()
    expect(tool).not.toBeNull()
    expect(tool?.getAttribute('data-tool-default-open')).toBe('false')
    expect(tool?.className).toContain('mb-2')
    expect(tool?.className).not.toContain('my-0')
    expect(thought?.textContent).toContain('Lookup')
    expect(thought?.textContent).not.toContain('Final answer')
    expect(container.textContent).toContain('Final answer')
  })

  test('hides reasoning independently while keeping tools in the timeline', () => {
    const html = renderToStaticMarkup(<Message
      hideReasoning
      message={{
        id: 'hidden-reasoning-tool',
        role: 'assistant',
        parts: [
          { type: 'reasoning', text: 'Do not show this', state: 'done' },
          { type: 'text', text: 'Visible answer', state: 'done' },
          { type: 'tool-call', toolCallId: 'visible-tool', toolName: 'lookup', toolDisplayName: 'Visible tool', input: {}, state: 'done' },
          { type: 'tool-result', toolCallId: 'visible-tool', toolName: 'lookup', output: 'done' },
        ],
      }}
    />)

    expect(html).not.toContain('Do not show this')
    expect(html).toContain('Visible answer')
    expect(html).toContain('Visible tool')
    expect(html).toContain('done')
  })


  test('renders completed compression variants and completed reasoning tools', () => {
    const html = renderToStaticMarkup(<Message message={{
      id: 'completed-steps',
      role: 'assistant',
      parts: [
        { type: 'task', taskType: 'compression', state: 'completed', info: { before_tokens: 100, after_tokens: 50, trigger: 'context_length_error' } },
        { type: 'task', taskType: 'compression', state: 'completed', info: { before_tokens: 90, after_tokens: 40, trigger: 'blocking_threshold', summary_turns: 2 } },
        { type: 'task', taskType: 'compression', state: 'completed', info: { before_tokens: 80, after_tokens: 30, pressure_level: 'blocking' } },
        { type: 'task', taskType: 'compression', state: 'completed', info: { before_tokens: 70, after_tokens: 20, summary_turns: 2, compacted_blocks: 4 } },
        { type: 'task', taskType: 'compression', state: 'completed', info: { before_tokens: 60, after_tokens: 10 } },
        { type: 'reasoning', text: 'Done thinking', state: 'done', duration: 1200 },
        { type: 'tool-call', toolCallId: 'done', toolName: 'lookup', input: {}, state: 'done' },
        { type: 'tool-result', toolCallId: 'done', toolName: 'lookup', output: { ok: true } },
      ],
    }} />)

    expect(html).toContain('chat.task.compressionCompletedReactive')
    expect(html).toContain('chat.task.compressionCompletedBlockingSummary')
    expect(html).toContain('chat.task.compressionCompletedBlocking')
    expect(html).toContain('chat.task.compressionCompletedProactiveSummary')
    expect(html).toContain('chat.task.compressionCompletedProactive')
    expect(html).toContain('lookup')
    expect(html).toContain('data-tool-state="output-available"')
    expect(html).toContain('Done thinking')
  })

  test('renders media URLs, fallbacks, string results, and artifact metadata without file cards', () => {
    const html = renderToStaticMarkup(<Message message={{
      id: 'media-variants',
      role: 'assistant',
      parts: [
        { type: 'media-result', output: { kind: 'media.video', success: true, prompt: 'Clip', status: 'completed', video: { url: '/clip.mp4' } } },
        { type: 'media-result', output: { kind: 'media.video', success: true, prompt: 'Missing clip', status: 'completed' } },
        { type: 'media-result', output: { kind: 'media.video', success: true, prompt: 'Unknown clip', status: 'failed', error: 'Codec failed' } },
        { type: 'media-result', output: { kind: 'media.image', success: true, prompt: '', images: [{ image: { base64: 'abc', format: 'webp' } }, { image: {} }] } },
        { type: 'tool-call', toolCallId: 'json', toolName: 'JSON tool', input: {}, state: 'done' },
        { type: 'tool-result', toolCallId: 'json', toolName: 'JSON tool', output: '{"answer":42}' },
        { type: 'tool-call', toolCallId: 'file', toolName: 'File tool', input: {}, state: 'done' },
        { type: 'tool-result', toolCallId: 'file', toolName: 'File tool', output: { artifacts: [{ url: '/download', filename: 'named.bin', size: 12, contentType: 'application/test' }] } },
      ],
    }} />)

    expect(html).toContain('src="/clip.mp4"')
    expect(html).toContain('controls=""')
    expect(html).toContain('chat.message.videoPreviewUnavailable')
    expect(html).toContain('chat.message.videoUnavailable')
    expect(html).toContain('Codec failed')
    expect(html).toContain('data:image/webp;base64,abc')
    expect(html).toContain('chat.message.generatedImageAlt')
    expect(html).toContain('&quot;answer&quot;:42')
    expect(html).not.toContain('artifacts:named.bin')
    expect(html).toContain('named.bin')
  })

  test('supports custom part rendering and user control boundaries', () => {
    const onSwitchVersion = mock(() => {})
    const renderPart = mock((part: { type: string }, index: number) => <span key={index}>custom:{part.type}:{index}</span>)
    const container = render(<Message
      message={{ id: 'custom-user', role: 'user', versionNumber: 1, versionCount: 2, parts: [{ type: 'text', text: 'Editable' }, { type: 'file', filename: 'notes.txt' }] }}
      renderPart={renderPart}
      onSwitchVersion={onSwitchVersion}
    />)

    expect(container.textContent).toContain('custom:file:0')
    expect(container.textContent).toContain('custom:text:0')
    const versionButtons = [...container.querySelectorAll('button')]
    expect(versionButtons[0].disabled).toBe(true)
    expect(versionButtons[1].disabled).toBe(false)
    act(() => versionButtons[1].click())
    expect(onSwitchVersion).toHaveBeenCalledWith(1)
    expect(container.firstElementChild?.getAttribute('data-role')).toBe('user')
  })

  test('saves edits with keyboard shortcuts and disables controls while saving', async () => {
    let finishSave!: () => void
    const onEditMessage = mock(() => new Promise<void>((resolve) => { finishSave = resolve }))
    const container = render(<Message message={{ id: 'edit-keyboard', role: 'user', parts: [{ type: 'text', text: 'Original' }] }} onEditMessage={onEditMessage} />)

    act(() => button(container, 'chat.message.edit').click())
    const textarea = container.querySelector('textarea')!
    act(() => {
      Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value')!.set!.call(textarea, 'Changed')
      textarea.dispatchEvent(new window.Event('input', { bubbles: true }))
    })
    act(() => textarea.dispatchEvent(new window.KeyboardEvent('keydown', { key: 'Enter', ctrlKey: true, bubbles: true })))

    expect(onEditMessage).toHaveBeenCalledWith('Changed')
    expect(container.querySelector('textarea')?.disabled).toBe(true)
    expect(button(container, 'chat.message.cancelEdit').disabled).toBe(true)
    await act(async () => finishSave())
    expect(container.querySelector('textarea')).toBeNull()
  })

  test('opens fenced code previews with a stable payload only after streaming', async () => {
    const onOpenCodePreview = mock(() => {})
    const code = '```xml\n<svg viewBox="0 0 1 1"></svg>\n```'
    const container = render(<Message message={{ id: 'preview', role: 'assistant', parts: [{ type: 'text', text: code, state: 'done' }] }} onOpenCodePreview={onOpenCodePreview} />)

    await act(async () => {})
    expect(container.querySelector('[data-streamdown="code-block-actions"]')?.textContent).toContain('chat.message.openCodePreview')
    act(() => button(container, 'chat.message.openCodePreview').click())
    expect(onOpenCodePreview).toHaveBeenCalledWith({
      id: 'xml:29:<svg viewBox="0 0 1 1"></svg>',
      language: 'xml',
      code: '<svg viewBox="0 0 1 1"></svg>',
      kind: 'svg',
    })

    const streaming = renderToStaticMarkup(<Message message={{ id: 'streaming-preview', role: 'assistant', parts: [{ type: 'text', text: code }] }} isStreaming onOpenCodePreview={onOpenCodePreview} />)
    expect(streaming).not.toContain('chat.message.openCodePreview')
  })

  test('keeps incomplete streaming code pinned to its own scroll bottom', () => {
    const container = render(<Message
      message={{ id: 'streaming-code', role: 'assistant', parts: [{ type: 'text', text: '```typescript\nconst value = 1', state: 'streaming' }] }}
      isStreaming
    />)
    const body = container.querySelector<HTMLElement>('[data-streamdown="code-block-body"]')!
    Object.defineProperty(body, 'scrollHeight', { configurable: true, value: 900 })
    body.scrollTop = 0

    const root = roots.at(-1)!
    act(() => root.render(<Message
      message={{ id: 'streaming-code', role: 'assistant', parts: [{ type: 'text', text: '```typescript\nconst value = 1\nconst value2 = 2', state: 'streaming' }] }}
      isStreaming
    />))

    expect(container.querySelector('[data-chat-code-autoscroll]')).not.toBeNull()
    expect(container.querySelector('[data-streamdown="code-block-body"]')).toBe(body)
    expect(body.scrollTop).toBe(900)
    expect(container.querySelector('[data-chat-code-loading]')).toBeNull()

    Object.defineProperty(body, 'scrollHeight', { configurable: true, value: 1200 })
    body.scrollTop = 200
    act(() => root.render(<Message
      message={{ id: 'streaming-code', role: 'assistant', parts: [{ type: 'text', text: '```typescript\nconst value = 1\nconst value2 = 2\nconst value3 = 3', state: 'streaming' }] }}
      isStreaming
    />))
    expect(container.querySelector('[data-streamdown="code-block-body"]')).toBe(body)
    expect(body.scrollTop).toBe(1200)

    act(() => root.render(<Message
      message={{ id: 'streaming-code', role: 'assistant', parts: [{ type: 'text', text: '```typescript\nconst value = 1\nconst value2 = 2\n```', state: 'streaming' }] }}
      isStreaming
    />))
    expect(container.querySelector('[data-chat-code-autoscroll]')).toBeNull()
  })

  test('keeps Markdown previews available without Streamdown code actions', async () => {
    rendersCodeActions = false
    const onOpenCodePreview = mock(() => {})
    const code = '  ~~~~markdown\n# Preview\n~~~~~\n'
    const container = render(<Message message={{ id: 'markdown-preview', role: 'assistant', parts: [{ type: 'text', text: code, state: 'done' }] }} onOpenCodePreview={onOpenCodePreview} />)

    await act(async () => {})
    const header = container.querySelector('[data-streamdown="code-block-header"]')
    expect(header?.querySelector('[data-chat-code-preview-fallback]')?.textContent).toContain('chat.message.openCodePreview')
    act(() => button(container, 'chat.message.openCodePreview').click())
    expect(onOpenCodePreview).toHaveBeenCalledWith({
      id: 'markdown:9:# Preview',
      language: 'markdown',
      code: '# Preview',
      kind: 'markdown',
    })
  })

  test('keeps empty Markdown fences previewable without Streamdown code actions', async () => {
    rendersCodeActions = false
    const onOpenCodePreview = mock(() => {})
    const code = '```markdown\n```'
    const container = render(<Message message={{ id: 'empty-markdown-preview', role: 'assistant', parts: [{ type: 'text', text: code, state: 'done' }] }} onOpenCodePreview={onOpenCodePreview} />)

    await act(async () => {})
    const header = container.querySelector('[data-streamdown="code-block-header"]')
    expect(header?.querySelector('[data-chat-code-preview-fallback]')).not.toBeNull()
    act(() => button(container, 'chat.message.openCodePreview').click())
    expect(onOpenCodePreview).toHaveBeenCalledWith({
      id: 'markdown:0:',
      language: 'markdown',
      code: '',
      kind: 'markdown',
    })
  })

  test('opens source previews without Streamdown code actions', async () => {
    rendersCodeActions = false
    const onOpenCodePreview = mock(() => {})
    const code = '```python\nprint(1)\n```'
    const container = render(<Message message={{ id: 'source-preview', role: 'assistant', parts: [{ type: 'text', text: code, state: 'done' }] }} onOpenCodePreview={onOpenCodePreview} />)

    await act(async () => {})
    act(() => button(container, 'chat.message.openCodePreview').click())
    expect(onOpenCodePreview).toHaveBeenCalledWith({
      id: 'python:8:print(1)',
      language: 'python',
      code: 'print(1)',
      kind: 'source',
    })
  })

  test('normalizes citations, strong markers, and math outside code', () => {
    const html = renderToStaticMarkup(<Message message={{
      id: 'normalized-text',
      role: 'assistant',
      parts: [
        { type: 'source-document', content: 'Only source' },
        { type: 'text', text: '**Bold**suffix [ref:1] (ref:9)\n\\[\\frac{1}{2}\\]\n`[ref:1]`' },
      ],
    }} />)

    expect(html).toContain('&lt;strong&gt;Bold&lt;/strong&gt;suffix')
    expect(html).toContain(' [1]')
    expect(html).not.toContain('(ref:9)')
    expect(html).toContain('$$')
    expect(html).toContain('` [1]`')
  })

  test('copies citation-free text and reports clipboard failures', async () => {
    const writeText = mock(async () => {})
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } })
    const container = render(<Message message={{ id: 'copy', role: 'assistant', parts: [{ type: 'text', text: 'Answer [[cite:1]]' }] }} />)

    await act(async () => button(container, 'chat.message.copy').click())
    expect(writeText).toHaveBeenCalledWith('Answer')
    expect(button(container, 'chat.message.copied')).not.toBeNull()

    const error = new Error('denied')
    const consoleError = mock(() => {})
    console.error = consoleError
    writeText.mockImplementationOnce(async () => { throw error })
    await act(async () => button(container, 'chat.message.copied').click())
    expect(consoleError).toHaveBeenCalledWith('Failed to copy:', error)
  })

  test('speaks normalized text, highlights sentence boundaries, and stops accessibly', async () => {
    type TestUtterance = {
      text: string
      lang: string
      voice?: SpeechSynthesisVoice
      onboundary?: (event: { charIndex: number }) => void
      onend?: () => void
      onerror?: () => void
    }
    class Utterance {
      text: string
      lang = ''
      constructor(text: string) { this.text = text }
    }
    const voice = { lang: 'en-GB' } as SpeechSynthesisVoice
    const speak = mock((value: TestUtterance) => { void value })
    const cancel = mock(() => {})
    const addEventListener = mock(() => {})
    const removeEventListener = mock(() => {})
    Object.assign(window, {
      SpeechSynthesisUtterance: Utterance,
      speechSynthesis: { speak, cancel, getVoices: () => [voice], addEventListener, removeEventListener },
    })
    ;(globalThis as typeof globalThis & { SpeechSynthesisUtterance: typeof Utterance }).SpeechSynthesisUtterance = Utterance
    const onRequestScrollIntoView = mock(() => {})
    const container = render(<Message
      message={{ id: 'speech', role: 'assistant', parts: [{ type: 'text', text: '# Dr. Smith has **one** item. Next item! `code` 🎉' }] }}
      onRequestScrollIntoView={onRequestScrollIntoView}
    />)
    await act(async () => {})

    expect(button(container, 'chat.message.listen').disabled).toBe(false)
    act(() => button(container, 'chat.message.listen').click())
    const utterance = speak.mock.calls[0][0]
    expect(utterance.text).toBe('Dr. Smith has one item. Next item! code')
    expect(utterance.lang).toBe('en-GB')
    expect(speak).toHaveBeenCalledTimes(1)
    expect(onRequestScrollIntoView).toHaveBeenCalledTimes(1)
    expect(button(container, 'chat.message.stopListening')).not.toBeNull()

    act(() => utterance.onboundary?.({ charIndex: 24 }))
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)) })
    expect(utterance.text.slice(24, 34)).toBe('Next item!')
    act(() => button(container, 'chat.message.stopListening').click())
    expect(cancel).toHaveBeenCalledTimes(2)
    expect(button(container, 'chat.message.listen')).not.toBeNull()

    act(() => button(container, 'chat.message.listen').click())
    act(() => utterance.onerror?.())
    expect(button(container, 'chat.message.listen')).not.toBeNull()
  })

  test('classifies every previewable fence and falls back to source', async () => {
    const onOpenCodePreview = mock(() => {})
    const cases = [
      ['mermaid', 'graph TD', 'mermaid'],
      ['html', '<main />', 'html'],
      ['css', 'body {}', 'css'],
      ['javascript', 'alert(1)', 'javascript'],
      ['markdown', '# title', 'markdown'],
      ['python', 'print(1)', 'source'],
      ['', 'plain', 'source'],
    ] as const

    for (const [language, code, kind] of cases) {
      const container = render(<Message
        message={{ id: `preview-${language}`, role: 'assistant', parts: [{ type: 'text', text: `\`\`\`${language}\n${code}\n\`\`\``, state: 'done' }] }}
        onOpenCodePreview={onOpenCodePreview}
      />)
      await act(async () => {})
      act(() => button(container, 'chat.message.openCodePreview').click())
      expect(onOpenCodePreview.mock.calls.at(-1)?.[0].kind).toBe(kind)
    }
  })

  test('loads authenticated markdown images and blocks unsafe sources', async () => {
    render(<Message message={{ id: 'image-renderer', role: 'assistant', parts: [{ type: 'text', text: 'image' }] }} />)
    const components = lastStreamdownProps.components as { img: React.ComponentType<React.ComponentProps<'img'>> }
    const createObjectURL = mock(() => 'blob:secured')
    const fetchMock = mock(async () => ({ ok: true, blob: async () => new Blob(['image']) }))
    Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: createObjectURL })
    Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: mock(() => {}) })
    globalThis.fetch = fetchMock as unknown as typeof fetch
    localStorage.setItem('access_token', 'secret')

    const secured = render(React.createElement(components.img, { src: '/api/v1/files/one', alt: 'Secured image' }))
    expect(secured.textContent).toContain('Secured image')
    await act(async () => { await Promise.resolve(); await Promise.resolve() })
    expect(secured.querySelector('img')?.getAttribute('src')).toBe('blob:secured')
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/files/one', { headers: { Authorization: 'Bearer secret' } })
    act(() => button(secured, 'chat.message.openCodePreview: Secured image').click())
    expect(openLightbox).toHaveBeenCalledWith('blob:secured', 'Secured image')

    const blocked = render(React.createElement(components.img, { src: 'javascript:alert(1)', alt: 'Blocked image' }))
    expect(blocked.textContent).toContain('Blocked image')
    const vbscript = render(React.createElement(components.img, { src: 'vbscript:alert(1)', alt: 'Blocked vbscript image' }))
    expect(vbscript.textContent).toContain('Blocked vbscript image')
    const external = render(React.createElement(components.img, { src: 'https://example.test/image.png', alt: 'External image' }))
    expect(external.querySelector('img')?.getAttribute('loading')).toBe('lazy')
  })

  test('checks same-origin links and exposes safety-modal decisions', () => {
    renderToStaticMarkup(<Message message={{ id: 'links', role: 'assistant', parts: [{ type: 'text', text: 'links' }] }} />)
    const linkSafety = lastStreamdownProps.linkSafety as {
      onLinkCheck: (url: string) => boolean
      renderModal: (props: { url: string; isOpen: boolean; onClose: () => void; onConfirm: () => void }) => React.ReactNode
    }
    expect(linkSafety.onLinkCheck('/safe')).toBe(true)
    expect(linkSafety.onLinkCheck('https://other.test/path')).toBe(false)
    expect(linkSafety.onLinkCheck('javascript:bad')).toBe(false)

    const onClose = mock(() => {})
    const onConfirm = mock(() => {})
    render(<>{linkSafety.renderModal({ url: 'https://other.test/path', isOpen: true, onClose, onConfirm })}</>)
    expect(document.body.textContent).toContain('https://other.test/path')
    act(() => button(document.body, 'chat.message.linkSafetyCancel').click())
    expect(onClose).toHaveBeenCalledTimes(1)
    act(() => button(document.body, 'chat.message.linkSafetyContinue').click())
    expect(onConfirm).toHaveBeenCalledTimes(1)
    expect(onClose).toHaveBeenCalledTimes(2)
  })

  test('renders remaining task, media-error, and math normalization branches', () => {
    const html = renderToStaticMarkup(<Message message={{
      id: 'remaining-branches',
      role: 'assistant',
      parts: [
        { type: 'task', taskType: 'rag', state: 'running' },
        { type: 'task', taskType: 'compression', state: 'running', info: { pressure_level: 'over_budget' } },
        { type: 'task', taskType: 'compression', state: 'running' },
        { type: 'task', taskType: 'generating', state: 'running' },
        { type: 'media-result', output: { kind: 'media.image', success: false, prompt: 'bad', images: [], error: 'image failed' } },
        { type: 'media-result', output: { kind: 'media.video', success: false, prompt: 'bad', error: 'video failed' } },
        { type: 'text', text: '\\frac{a}{b}=1\nplain [words]\ninline (\\sqrt{x})\n$$\n\\sum x\n$$' },
      ],
    }} />)
    expect(html).toContain('chat.task.searchingKnowledge')
    expect(html).toContain('chat.task.compressingContextBlocking')
    expect(html).toContain('chat.task.compressingContextProactive')
    expect(html).toContain('chat.task.generating')
    expect(html).toContain('image failed')
    expect(html).toContain('video failed')
    expect(html).toContain('$')
  })

  test('executes Streamdown safety, rendering, and highlighting integration hooks', async () => {
    const container = render(<Message message={{ id: 'hooks', role: 'assistant', parts: [{ type: 'text', text: 'hook text' }] }} />)
    const plugins = lastStreamdownProps.plugins as {
      code: {
        supportsLanguage: (language: string) => boolean
        getSupportedLanguages: () => string[]
        getThemes: () => string[]
        highlight: (options: { language: string; code: string; themes: string[] }, callback: (value: unknown) => void) => null
      }
    }
    expect(plugins.code.supportsLanguage('javascript')).toBe(true)
    expect(plugins.code.supportsLanguage('unknown')).toBe(false)
    expect(plugins.code.getSupportedLanguages()).toEqual(['javascript'])
    expect(plugins.code.getThemes()).toEqual(['github-light', 'github-dark'])
    expect(plugins.code.highlight({ language: 'unknown', code: '', themes: [] }, () => {})).toBeNull()
    const highlighted = mock(() => {})
    plugins.code.highlight({ language: 'javascript', code: 'const a = 1', themes: ['light', 'dark'] }, highlighted)
    await act(async () => { await Promise.resolve() })
    expect(codeToTokens).toHaveBeenCalledTimes(1)
    expect(highlighted).toHaveBeenCalledTimes(1)
    codeToTokens.mockImplementationOnce(async () => { throw new Error('highlight failed') })
    plugins.code.highlight({ language: 'javascript', code: 'bad code', themes: ['light', 'dark'] }, highlighted)
    await act(async () => { await Promise.resolve() })
    expect(highlighted).toHaveBeenCalledTimes(1)

    const components = lastStreamdownProps.components as {
      p: React.ComponentType<React.ComponentProps<'p'> & { node?: { children?: Array<{ tagName?: string; type?: string }> } }>
    }
    expect(renderToStaticMarkup(React.createElement(components.p, null, 'plain'))).toStartWith('<p')
    expect(renderToStaticMarkup(React.createElement(components.p, { node: { children: [{ type: 'element', tagName: 'img' }] } }, 'image'))).toStartWith('<div')
    expect(renderToStaticMarkup(React.createElement(components.p, null, <div>block</div>))).toStartWith('<div')

    const linkSafety = lastStreamdownProps.linkSafety as { renderModal: (props: { url: string; isOpen: boolean; onClose: () => void; onConfirm: () => void }) => React.ReactNode }
    expect(renderToStaticMarkup(<>{linkSafety.renderModal({ url: '/closed', isOpen: false, onClose: () => {}, onConfirm: () => {} })}</>)).toBe('')
    const onClose = mock(() => {})
    render(<>{linkSafety.renderModal({ url: '/open', isOpen: true, onClose, onConfirm: () => {} })}</>)
    act(() => (lastDialogProps.onOpenChange as (open: boolean) => void)(false))
    expect(onClose).toHaveBeenCalledTimes(1)
    expect(container.textContent).toContain('hook text')
  })

  test('shows authenticated image failures and reuses successful cached assets', async () => {
    render(<Message message={{ id: 'image-hooks', role: 'assistant', parts: [{ type: 'text', text: 'image' }] }} />)
    const components = lastStreamdownProps.components as { img: React.ComponentType<React.ComponentProps<'img'>> }
    globalThis.fetch = mock(async () => ({ ok: false })) as unknown as typeof fetch
    localStorage.removeItem('access_token')
    const failed = render(React.createElement(components.img, { src: '/api/v1/files/failure', alt: 'Unavailable image' }))
    await act(async () => { await Promise.resolve(); await Promise.resolve() })
    expect(failed.textContent).toContain('Unavailable image')

    const cached = render(React.createElement(components.img, { src: '/api/v1/files/one', alt: 'Cached image' }))
    expect(cached.querySelector('img')?.getAttribute('src')).toBe('blob:secured')
  })

  test('normalizes empty and invalid math while preserving code blocks', () => {
    const html = renderToStaticMarkup(<Message message={{ id: 'math-edges', role: 'assistant', parts: [{
      type: 'text',
      text: '`**code**suffix`\n[plain words]\n(plain words)\n\\(\\cos{x}\\)\n\n',
    }] }} />)
    expect(html).toContain('`**code**suffix`')
    expect(html).toContain('[plain words]')
    expect(html).toContain('(plain words)')
    expect(html).toContain('$\\cos{x}$')
  })

  test('highlights the actively spoken plain-text sentence and clears it on completion', async () => {
    type TestUtterance = { onboundary?: (event: { charIndex: number }) => void; onend?: () => void }
    class Utterance {}
    const speak = mock((value: TestUtterance) => { void value })
    Object.assign(window, {
      SpeechSynthesisUtterance: Utterance,
      speechSynthesis: {
        speak,
        cancel: mock(() => {}),
        getVoices: () => [],
        addEventListener: mock(() => {}),
        removeEventListener: mock(() => {}),
      },
    })
    ;(globalThis as typeof globalThis & { SpeechSynthesisUtterance: typeof Utterance }).SpeechSynthesisUtterance = Utterance
    const container = render(<Message message={{ id: 'speech-highlight', role: 'assistant', parts: [{ type: 'text', text: 'First sentence. Second sentence!' }] }} />)
    await act(async () => {})
    act(() => button(container, 'chat.message.listen').click())
    const utterance = speak.mock.calls[0][0]
    act(() => utterance.onboundary?.({ charIndex: 16 }))
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)) })
    expect(container.querySelector('mark[data-speech-highlight="true"]')?.textContent).toBe('Second sentence!')
    act(() => utterance.onend?.())
    expect(container.querySelector('mark[data-speech-highlight="true"]')).toBeNull()
  })

  test('rerenders when each memoized public prop changes', () => {
    const message = { id: 'memo', role: 'assistant' as const, parts: [{ type: 'text' as const, text: 'memo' }] }
    const container = document.body.appendChild(document.createElement('div'))
    const root = createRoot(container)
    roots.push(root)
    const base = { message }
    const variants = [
      { isStreaming: true }, { renderPart: () => <span>custom</span> }, { showCopy: false }, { showFeedback: true },
      { onRegenerate: () => {} }, { onEditMessage: async () => {} }, { onFeedback: () => {} }, { onSwitchVersion: () => {} },
      { onSelectOption: () => {} }, { onOpenCodePreview: () => {} }, { hideToolCalls: true }, { chainOfThoughtOpen: true },
      { onChainOfThoughtOpenChange: () => {} }, { onRequestScrollIntoView: () => {} }, { className: 'changed' },
    ]
    act(() => root.render(<Message {...base} />))
    for (const variant of variants) {
      act(() => root.render(<Message {...base} {...variant} />))
      act(() => root.render(<Message {...base} />))
    }
    expect(container.textContent).toContain('memo')
  })
})
