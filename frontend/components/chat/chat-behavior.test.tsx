import { afterEach, beforeEach, describe, expect, mock, test } from 'bun:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'

mock.module('next-intl', () => ({
  useTranslations: (namespace?: string) => (key: string, values?: Record<string, unknown>) => {
    if (namespace === 'chat.input' && key === 'maxFilesReached') return `Max ${values?.max} files`
    return key
  },
}))

mock.module('@/components/ui/tooltip', () => ({
  Tooltip: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  TooltipContent: ({ children }: { children: React.ReactNode }) => <span>{children}</span>,
  TooltipTrigger: ({ render }: { render: React.ReactNode }) => <>{render}</>,
}))

mock.module('@/components/ui/button', () => ({
  Button: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => <button {...props}>{children}</button>,
}))

mock.module('./message', () => ({
  Message: ({ message, isStreaming }: { message: { id: string; role: string; parts: Array<{ text?: string }> }; isStreaming: boolean }) => (
    <article data-message-id={message.id} data-role={message.role} data-streaming={String(isStreaming)}>
      {message.parts.map((part, index) => <span key={index}>{part.text}</span>)}
    </article>
  ),
}))

import { ChatContainer } from './chat-container'
import { ChatInput, type ChatInputFile } from './chat-input'
import type { ChatMessage } from './types'

const submitButtonHtml = (markup: string) => markup.match(/<button type="button"[^>]*>.*?(?:send|stop)/s)?.[0] ?? ''

function renderInput(props: React.ComponentProps<typeof ChatInput> = {}) {
  return renderToStaticMarkup(<ChatInput {...props} />)
}

function file(name: string, overrides: Partial<ChatInputFile> = {}): ChatInputFile {
  const blob = new File(['x'], name, { type: overrides.type ?? 'text/plain' })
  return {
    id: name,
    name,
    size: blob.size,
    type: blob.type,
    file: blob,
    isDocument: true,
    ...overrides,
  }
}

function message(id: string, role: ChatMessage['role'], text: string): ChatMessage {
  return { id, role, parts: [{ type: 'text', text }], createdAt: new Date('2026-01-01') }
}

describe('ChatInput behavior', () => {
  let revoked: string[]

  beforeEach(() => {
    revoked = []
    URL.revokeObjectURL = ((url: string) => revoked.push(url)) as typeof URL.revokeObjectURL
  })

  afterEach(() => {
    mock.restore()
  })

  test('renders attachment controls only when uploads are enabled and respects max files', () => {
    expect(renderInput({ allowAttachments: false, enableFileUpload: false })).not.toContain('type="file"')

    const markup = renderInput({
      allowAttachments: false,
      enableFileUpload: true,
      maxFiles: 1,
      files: [file('notes.pdf')],
    })

    expect(markup).toContain('type="file"')
    expect(markup).toContain('disabled=""')
    expect(markup).toContain('Max 1 files')
  })

  test('blocks submit while disabled/loading/uploading and shows stop during streaming', () => {
    const disabledMarkup = renderInput({ value: 'hello', disabled: true })
    expect(submitButtonHtml(disabledMarkup)).toContain('disabled=""')

    const loadingMarkup = renderInput({ value: 'hello', isLoading: true })
    expect(submitButtonHtml(loadingMarkup)).toContain('disabled=""')

    const uploadingMarkup = renderInput({ value: 'hello', isUploading: true })
    expect(submitButtonHtml(uploadingMarkup)).toContain('disabled=""')

    const streamingMarkup = renderInput({ value: 'hello', isStreaming: true, onStop: () => {} })
    expect(streamingMarkup).toContain('stop')
    expect(streamingMarkup).not.toContain('send')
  })

  test('submits files without text and omits remove controls while uploading', () => {
    const uploading = file('notes.pdf', { isUploading: true, uploadProgress: 42 })
    const markup = renderInput({ value: '', files: [uploading], onSubmit: () => {} })

    expect(markup).toContain('notes.pdf')
    expect(markup).toContain('42%')
    expect(markup).not.toContain('ml-0.5 p-0.5 rounded hover:bg-muted z-10')
    expect(submitButtonHtml(markup)).not.toContain('disabled=""')
  })
})

describe('ChatContainer behavior', () => {
  test('renders empty state instead of scroll chrome when there are no messages', () => {
    const markup = renderToStaticMarkup(<ChatContainer messages={[]} emptyState={<p>No messages yet</p>} />)

    expect(markup).toContain('No messages yet')
    expect(markup).not.toContain('overflow-y-auto')
  })

  test('only marks the last visible assistant message as streaming', () => {
    const markup = renderToStaticMarkup(
      <ChatContainer
        messages={[message('user-1', 'user', 'Hi'), message('assistant-1', 'assistant', 'Hello')]}
        isStreaming
      />
    )

    expect(markup).toContain('data-message-id="user-1" data-role="user" data-streaming="false"')
    expect(markup).toContain('data-message-id="assistant-1" data-role="assistant" data-streaming="true"')
  })
})
