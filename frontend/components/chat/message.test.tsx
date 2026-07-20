import { describe, expect, mock, test } from 'bun:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'

const Icon = (props: React.ComponentProps<'svg'>) => <svg {...props} />

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
const Textarea = React.forwardRef<HTMLTextAreaElement, React.ComponentProps<'textarea'>>(function Textarea(props, ref) {
  return <textarea ref={ref} {...props} />
})
mock.module('@/components/ui/textarea', () => ({ Textarea }))
mock.module('@/components/ai-elements/message', () => ({
  Message: ({ children }: { children: React.ReactNode }) => <article>{children}</article>,
  MessageAction: ({ children, tooltip }: { children: React.ReactNode; tooltip: string }) => <button type="button" aria-label={tooltip}>{children}</button>,
  MessageActions: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  MessageAttachment: ({ data }: { data: { filename?: string } }) => <span>{data.filename}</span>,
  MessageAttachments: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  MessageContent: ({ children }: { children: React.ReactNode }) => <section>{children}</section>,
}))
mock.module('@/components/ai-elements/chain-of-thought', () => ({ ChainOfThought: ({ children }: { children: React.ReactNode }) => <div>{children}</div>, ChainOfThoughtContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>, ChainOfThoughtHeader: ({ title }: { title: string }) => <h3>{title}</h3>, ChainOfThoughtStep: ({ children, label }: { children?: React.ReactNode; label: React.ReactNode }) => <div>{label}{children}</div> }))
mock.module('@/components/ai-elements/tool', () => ({ Tool: ({ children }: { children: React.ReactNode }) => <div>{children}</div>, ToolContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>, ToolHeader: ({ title }: { title: string }) => <h4>{title}</h4>, ToolInput: ({ input }: { input: unknown }) => <pre>{JSON.stringify(input)}</pre>, ToolOutput: ({ output, errorText }: { output?: unknown; errorText?: string }) => <pre>{errorText ?? JSON.stringify(output)}</pre> }))
mock.module('./image-lightbox', () => ({ ImageLightbox: () => null, useLightbox: () => ({ isOpen: false, imageSrc: '', imageAlt: '', openLightbox: mock(() => {}), closeLightbox: mock(() => {}) }) }))
mock.module('./message-parts', () => ({ SourceContent: ({ sources }: { sources: unknown[] }) => <aside>sources:{sources.length}</aside>, FileListContent: () => null }))
mock.module('./user-input-request-card', () => ({ UserInputRequestCard: () => null }))
mock.module('streamdown', () => ({ Block: ({ content }: { content: string }) => <pre>{content}</pre>, Streamdown: ({ children }: { children: React.ReactNode }) => <div>{children}</div>, defaultRehypePlugins: { sanitize: 'sanitize', harden: 'harden' } }))
mock.module('shiki', () => ({ bundledLanguages: {}, codeToTokens: mock(() => Promise.resolve({})) }))
mock.module('@streamdown/math', () => ({ createMathPlugin: () => ({}) }))

const { Message } = await import('./message')

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
