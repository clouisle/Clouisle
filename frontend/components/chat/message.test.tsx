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
})
;(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true

const Icon = (props: React.ComponentProps<'svg'>) => <svg {...props} />
const openLightbox = mock(() => {})

mock.module('next-intl', () => ({
  useLocale: () => 'en-US',
  useTranslations: (namespace?: string) => (key: string) => (namespace ? `${namespace}.${key}` : key),
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
mock.module('@/components/ui/dialog', () => ({ Dialog: ({ children }: { children: React.ReactNode }) => <>{children}</>, DialogContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>, DialogHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>, DialogTitle: ({ children }: { children: React.ReactNode }) => <h2>{children}</h2> }))
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
mock.module('@/components/ai-elements/chain-of-thought', () => ({ ChainOfThought: ({ children }: { children: React.ReactNode }) => <div>{children}</div>, ChainOfThoughtContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>, ChainOfThoughtHeader: ({ title }: { title: string }) => <h3>{title}</h3>, ChainOfThoughtStep: ({ children, label }: { children?: React.ReactNode; label: React.ReactNode }) => <div>{label}{children}</div> }))
mock.module('@/components/ai-elements/tool', () => ({ Tool: ({ children }: { children: React.ReactNode }) => <div>{children}</div>, ToolContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>, ToolHeader: ({ title }: { title: string }) => <h4>{title}</h4>, ToolInput: ({ input }: { input: unknown }) => <pre>{JSON.stringify(input)}</pre>, ToolOutput: ({ output, errorText }: { output?: unknown; errorText?: string }) => <pre>{errorText ?? JSON.stringify(output)}</pre> }))
mock.module('./image-lightbox', () => ({ ImageLightbox: ({ src, alt, isOpen }: { src: string; alt: string; isOpen: boolean }) => isOpen ? <div role="dialog" aria-label={alt}>{src}</div> : null, useLightbox: () => ({ isOpen: false, imageSrc: '', imageAlt: '', openLightbox, closeLightbox: mock(() => {}) }) }))
mock.module('./message-parts', () => ({ SourceContent: ({ sources }: { sources: unknown[] }) => <aside>sources:{sources.length}</aside>, FileListContent: ({ files }: { files: Array<{ filename: string }> }) => <div>artifacts:{files.map((file) => file.filename).join(',')}</div> }))
mock.module('./user-input-request-card', () => ({ UserInputRequestCard: ({ question, options, onSelectOption }: { question: string; options: string[]; onSelectOption?: (option: string) => void }) => <fieldset><legend>{question}</legend>{options.map((option) => <button key={option} onClick={() => onSelectOption?.(option)}>{option}</button>)}</fieldset> }))
mock.module('streamdown', () => ({ Block: ({ content }: { content: string }) => <pre>{content}</pre>, Streamdown: ({ children }: { children: React.ReactNode }) => <div>{children}</div>, defaultRehypePlugins: { sanitize: 'sanitize', harden: 'harden' } }))
mock.module('shiki', () => ({ bundledLanguages: {}, codeToTokens: mock(() => Promise.resolve({})) }))
mock.module('@streamdown/math', () => ({ createMathPlugin: () => ({}) }))

const { Message } = await import('./message')

const roots: Root[] = []
afterEach(() => {
  for (const root of roots.splice(0)) act(() => root.unmount())
  document.body.replaceChildren()
  openLightbox.mockClear()
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
          usage: { prompt_tokens: 1200, completion_tokens: 34, total_tokens: 1234 },
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

  test('renders tool errors, artifacts, MCP results, and media failures', () => {
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
    expect(html).toContain('artifacts:report.csv')
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

    act(() => container.querySelector('img[alt="Uploaded chart"]')!.parentElement!.click())
    act(() => container.querySelector('img[alt="Generated chart"]')!.parentElement!.click())
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
})
