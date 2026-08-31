import { beforeEach, describe, expect, mock, test } from 'bun:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'

const uploadedUrls: string[] = []

mock.module('next-intl', () => ({
  useLocale: () => 'en-US',
  useTranslations: (namespace?: string) => (key: string, values?: Record<string, unknown>) => {
    if (key === 'maxFilesReached') return `max ${values?.max}`
    if (key === 'fileTooLarge') return `too large ${values?.maxSize}`
    if (key === 'loadOlderMessages' || key === 'message.loadOlderMessages') return `load ${values?.count}`
    return namespace ? `${namespace}.${key}` : key
  },
}))
const Icon = (props: React.ComponentProps<'svg'>) => <svg {...props} />
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
  FileAudio: Icon,
  FileCode: Icon,
  FileImage: Icon,
  FileText: Icon,
  FileType: Icon,
  FileVideo: Icon,
  Link: Icon,
  ChevronDown: Icon,
  ChevronUp: Icon,
  Download: Icon,
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
mock.module('@/lib/constants', () => ({
  BYTES_PER_MB: 1024 * 1024,
  GENERAL_UPLOAD_MAX_FILE_SIZE_BYTES: 10 * 1024 * 1024,
  GENERAL_UPLOAD_MAX_FILE_SIZE_MB: 10,
}))
mock.module('@/lib/validation', () => ({
  clearValidationError: (errors: Record<string, string>, field: string) => Object.fromEntries(Object.entries(errors).filter(([key]) => key !== field)),
  getValidationSummaryEntries: (errors: Record<string, string>, fields: string[]) => fields.filter((field) => errors[field]).map((field) => [field, errors[field]]),
  formatValidationSummaryMessage: (field: string, message: string) => `${field}: ${message}`,
}))
mock.module('@/lib/api', () => ({ ApiError: class ApiError extends Error { code?: number; data?: unknown } }))
mock.module('@/lib/api/upload', () => ({ uploadApi: { uploadFile: mock(() => Promise.resolve({ url: uploadedUrls.shift() ?? '/files/uploaded.txt' })) } }))
mock.module('@/lib/utils/tool-result', () => ({
  getImageAssetUrl: (value: unknown) => typeof value === 'string' ? value : null,
  getVideoAssetUrl: (value: unknown) => typeof value === 'string' ? value : null,
  isMediaImageToolResult: (value: unknown) => Boolean((value as { images?: unknown }).images),
  isMediaVideoToolResult: (value: unknown) => Boolean((value as { video?: unknown }).video),
  parseToolResultOutput: (value: unknown) => value,
  shouldDisplayMediaResultInBody: () => false,
}))

mock.module('@/components/ui/button', () => ({ Button: ({ children, ...props }: React.ComponentProps<'button'>) => <button {...props}>{children}</button> }))
mock.module('@/components/ui/input', () => ({ Input: (props: React.ComponentProps<'input'>) => <input {...props} /> }))
const Textarea = React.forwardRef<HTMLTextAreaElement, React.ComponentProps<'textarea'>>(function Textarea(props, ref) {
  return <textarea ref={ref} {...props} />
})
mock.module('@/components/ui/textarea', () => ({ Textarea }))
mock.module('@/components/ui/label', () => ({ Label: ({ children, ...props }: React.ComponentProps<'label'>) => <label {...props}>{children}</label> }))
mock.module('@/components/ui/checkbox', () => ({ Checkbox: ({ checked, ...props }: { checked?: boolean } & React.ComponentProps<'input'>) => <input type="checkbox" checked={checked} readOnly {...props} /> }))
mock.module('@/components/ui/field', () => ({ FieldError: ({ children }: { children?: React.ReactNode }) => children ? <p role="alert">{children}</p> : null }))
mock.module('@/components/ui/select', () => ({
  Select: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectItem: ({ children, value }: { children: React.ReactNode; value: string }) => <div data-value={value}>{children}</div>,
  SelectTrigger: ({ children, ...props }: { children: React.ReactNode }) => <button type="button" {...props}>{children}</button>,
  SelectValue: ({ children }: { children?: React.ReactNode }) => <span>{children}</span>,
}))
mock.module('@/components/ui/tooltip', () => ({
  Tooltip: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  TooltipContent: ({ children }: { children: React.ReactNode }) => <span>{children}</span>,
  TooltipTrigger: ({ render }: { render: React.ReactNode }) => <>{render}</>,
}))
mock.module('@/components/ui/popover', () => ({
  Popover: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  PopoverContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  PopoverTrigger: ({ render }: { render: React.ReactNode }) => <>{render}</>,
}))
mock.module('@/components/ui/dialog', () => ({
  Dialog: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  DialogContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogTitle: ({ children }: { children: React.ReactNode }) => <h2>{children}</h2>,
}))
mock.module('@/components/ai-elements/message', () => ({
  Message: ({ children, from }: { children: React.ReactNode; from: string }) => <article data-from={from}>{children}</article>,
  MessageAction: ({ children, tooltip, disabled }: { children: React.ReactNode; tooltip: string; disabled?: boolean }) => <button type="button" disabled={disabled} aria-label={tooltip}>{children}</button>,
  MessageActions: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  MessageAttachment: ({ data }: { data: { filename?: string } }) => <span>{data.filename}</span>,
  MessageAttachments: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  MessageContent: ({ children }: { children: React.ReactNode }) => <section>{children}</section>,
}))
mock.module('@/components/ai-elements/chain-of-thought', () => ({
  ChainOfThought: ({ children, open, isStreaming }: { children: React.ReactNode; open?: boolean; isStreaming?: boolean }) => <div data-open={open} data-streaming={isStreaming}>{children}</div>,
  ChainOfThoughtContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  ChainOfThoughtHeader: ({ title }: { title: string }) => <h3>{title}</h3>,
  ChainOfThoughtStep: ({ children, label, status }: { children?: React.ReactNode; label: React.ReactNode; status: string }) => <div data-status={status}><span>{label}</span>{children}</div>,
}))
mock.module('@/components/ai-elements/tool', () => ({
  Tool: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  ToolContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  ToolHeader: ({ title, state }: { title: string; state: string }) => <h4 data-state={state}>{title}</h4>,
  ToolInput: ({ input }: { input: unknown }) => <pre>{JSON.stringify(input)}</pre>,
  ToolOutput: ({ output, errorText }: { output?: unknown; errorText?: string }) => <pre>{errorText ?? JSON.stringify(output)}</pre>,
}))
mock.module('./image-lightbox', () => ({ ImageLightbox: () => null, useLightbox: () => ({ isOpen: false, imageSrc: '', imageAlt: '', openLightbox: mock(() => {}), closeLightbox: mock(() => {}) }) }))
mock.module('./message-parts', () => ({ SourceContent: ({ sources }: { sources: unknown[] }) => <aside>sources:{sources.length}</aside>, FileListContent: ({ files }: { files: Array<{ filename?: string }> }) => <div>{files.map((file) => file.filename).join(',')}</div> }))
mock.module('./user-input-request-card', () => ({ UserInputRequestCard: ({ question, options }: { question: string; options?: string[] }) => <div>{question}{options?.join(',')}</div> }))
mock.module('streamdown', () => ({
  Block: ({ content }: { content: string }) => <pre>{content}</pre>,
  Streamdown: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  defaultRehypePlugins: { sanitize: 'sanitize', harden: 'harden' },
}))
mock.module('shiki', () => ({ bundledLanguages: {}, codeToTokens: mock(() => Promise.resolve({})) }))
mock.module('@streamdown/math', () => ({ createMathPlugin: () => ({}) }))
mock.module('./message', () => ({
  Message: ({ message, isStreaming, onRegenerate, onEditMessage, onSwitchVersion, chainOfThoughtOpen, hideToolCalls }: {
    message: { id: string; role: string; parts: Array<{ text?: string }> }
    isStreaming?: boolean
    onRegenerate?: () => void
    onEditMessage?: (content: string) => Promise<void>
    onSwitchVersion?: (index: number) => void
    chainOfThoughtOpen?: boolean
    hideToolCalls?: boolean
  }) => <div data-message-id={message.id} data-streaming={isStreaming} data-editable={!!onEditMessage} data-regenerable={!!onRegenerate} data-switchable={!!onSwitchVersion} data-chain-open={chainOfThoughtOpen} data-hide-tools={hideToolCalls}>{message.parts.map((part) => part.text).join('')}</div>,
}))

const { ChatInput } = await import('./chat-input')
const { VariableForm, useVariableForm } = await import('./variable-form')
const { ChatContainer } = await import('./chat-container')

beforeEach(() => {
  uploadedUrls.length = 0
})

describe('chat input rendering', () => {
  test('shows document previews, upload progress, and disables submit while uploading', () => {
    const html = renderToStaticMarkup(<ChatInput
      value="Ship it"
      isUploading
      enableFileUpload
      allowAttachments={false}
      files={[{ id: 'doc', name: 'plan.pdf', size: 1536, type: 'application/pdf', file: new File(['x'], 'plan.pdf'), isDocument: true, isUploading: true, uploadProgress: 42 }]}
    />)

    expect(html).toContain('plan.pdf')
    expect(html).toContain('42%')
    expect(html).toContain('disabled=""')
    expect(html).toContain('.pdf')
  })

  test('hides attachment controls when uploads and vision are disabled', () => {
    const html = renderToStaticMarkup(<ChatInput value="Hello" allowAttachments={false} enableFileUpload={false} />)

    expect(html).toContain('data-testid="chat-input"')
    expect(html).not.toContain('type="file"')
    expect(html).not.toContain('chat.input.attachFile')
  })
})

describe('variable form rendering', () => {
  test('renders only visible fields and blocks submit when required data is missing', () => {
    const html = renderToStaticMarkup(<VariableForm
      values={{ tone: 'short' }}
      onChange={() => {}}
      onSubmit={() => {}}
      fieldErrors={{ tone: 'Pick a different tone' }}
      variables={[
        { name: 'prompt', label: 'Prompt', type: 'paragraph', required: true },
        { name: 'tone', label: 'Tone', type: 'select', options: ['short', 'long'], required: false },
        { name: 'secret', label: 'Secret', type: 'text', hidden: true },
      ]}
    />)

    expect(html).toContain('Prompt')
    expect(html).toContain('Tone')
    expect(html).toContain('tone: Pick a different tone')
    expect(html).toContain('disabled=""')
    expect(html).not.toContain('Secret')
  })

  test('initializes hook values and derived errors from definitions', () => {
    function Probe() {
      const form = useVariableForm([
        { name: 'enabled', type: 'checkbox', default: 'true' },
        { name: 'count', type: 'number', default: '3' },
        { name: 'payload', type: 'object', required: true },
      ])
      return <pre>{JSON.stringify({ values: form.values, needsInput: form.needsInput, isValid: form.isValid, fieldErrors: form.fieldErrors })}</pre>
    }

    const html = renderToStaticMarkup(<Probe />)

    expect(html).toContain('&quot;enabled&quot;:true')
    expect(html).toContain('&quot;count&quot;:3')
    expect(html).toContain('&quot;needsInput&quot;:true')
    expect(html).toContain('&quot;payload&quot;:&quot;common.required&quot;')
  })
})

describe('chat container rendering', () => {
  test('renders empty state instead of message rows', () => {
    expect(renderToStaticMarkup(<ChatContainer messages={[]} emptyState={<p>No messages</p>} />)).toContain('No messages')
  })

  test('virtualizes older messages and wires role-specific actions to rows', () => {
    const messages = Array.from({ length: 25 }, (_, index) => ({
      id: `m${index}`,
      role: index === 24 ? 'assistant' : 'user',
      parts: [{ type: 'text', text: `message ${index}` }],
    }))
    const idleHtml = renderToStaticMarkup(<ChatContainer
      messages={messages}
      onRegenerate={() => {}}
      onEditMessage={async () => {}}
      onSwitchVersion={() => {}}
      hideToolCalls
    />)

    expect(idleHtml).toContain('load 5')
    expect(idleHtml).not.toContain('message 0')
    expect(idleHtml).toContain('message 24')
    expect(idleHtml).toContain('data-regenerable="true"')
    expect(idleHtml).toContain('data-editable="true"')
    expect(idleHtml).toContain('data-streaming="false"')
    expect(idleHtml).toContain('data-hide-tools="true"')

    const streamingHtml = renderToStaticMarkup(<ChatContainer
      messages={messages}
      isStreaming
      onRegenerate={() => {}}
      onEditMessage={async () => {}}
      onSwitchVersion={() => {}}
      hideToolCalls
    />)
    expect(streamingHtml).toContain('data-streaming="true"')
    expect(streamingHtml).toContain('data-editable="false"')
  })
})

