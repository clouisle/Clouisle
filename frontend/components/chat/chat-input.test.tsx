import { afterEach, describe, expect, mock, test } from 'bun:test'
import React from 'react'
import TestRenderer, { act } from 'react-test-renderer'

import type { ChatInputFile } from './chat-input'

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

mock.module('next-intl', () => ({
  useTranslations: () => (key: string, values?: Record<string, unknown>) => (
    values ? `${key}:${JSON.stringify(values)}` : key
  ),
}))

mock.module('@/components/ui/tooltip', () => ({
  Tooltip: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  TooltipContent: ({ children }: { children: React.ReactNode }) => <span>{children}</span>,
  TooltipTrigger: ({ render }: { render: React.ReactNode }) => <>{render}</>,
}))

const createObjectURL = mock(() => 'blob:preview')
const revokeObjectURL = mock(() => undefined)
Object.defineProperty(URL, 'createObjectURL', { value: createObjectURL, configurable: true })
Object.defineProperty(URL, 'revokeObjectURL', { value: revokeObjectURL, configurable: true })

import { ChatInput } from './chat-input'

function renderChatInput(props: React.ComponentProps<typeof ChatInput>) {
  let tree!: TestRenderer.ReactTestRenderer
  act(() => {
    tree = TestRenderer.create(<ChatInput {...props} />)
  })
  return tree
}

function buttons(tree: TestRenderer.ReactTestRenderer) {
  return tree.root.findAllByType('button')
}

function chatInput(tree: TestRenderer.ReactTestRenderer) {
  return tree.root.findByProps({ 'data-testid': 'chat-input' })
}

function fileInput(tree: TestRenderer.ReactTestRenderer) {
  return tree.root.findByType('input')
}

function fileFixture(overrides: Partial<ChatInputFile> = {}): ChatInputFile {
  const file = new File(['hello'], overrides.name ?? 'notes.txt', { type: overrides.type ?? 'text/plain' })
  return {
    id: 'file-1',
    name: file.name,
    size: file.size,
    type: file.type,
    file,
    isDocument: true,
    ...overrides,
  }
}

afterEach(() => {
  createObjectURL.mockClear()
  revokeObjectURL.mockClear()
})

describe('ChatInput', () => {
  test('reports text changes and submits trimmed text with Enter', () => {
    const onChange = mock(() => undefined)
    const onSubmit = mock(() => undefined)
    const tree = renderChatInput({ value: '  hello  ', onChange, onSubmit })

    act(() => {
      chatInput(tree).props.onChange({ target: { value: 'draft' } })
    })
    expect(onChange).toHaveBeenCalledWith('draft')

    act(() => {
      chatInput(tree).props.onKeyDown({
        key: 'Enter',
        shiftKey: false,
        preventDefault: mock(() => undefined),
      })
    })

    expect(onSubmit).toHaveBeenCalledWith('hello', undefined)
    expect(onChange).toHaveBeenLastCalledWith('')
  })

  test('keeps Shift+Enter and IME Enter from submitting', () => {
    const onSubmit = mock(() => undefined)
    const tree = renderChatInput({ value: 'hello', onSubmit })

    act(() => {
      chatInput(tree).props.onKeyDown({ key: 'Enter', shiftKey: true, preventDefault: mock(() => undefined) })
    })
    act(() => {
      chatInput(tree).props.onCompositionStart()
    })
    act(() => {
      chatInput(tree).props.onKeyDown({ key: 'Enter', shiftKey: false, preventDefault: mock(() => undefined) })
    })

    expect(onSubmit).not.toHaveBeenCalled()
  })

  test('disables send for empty, disabled, loading, and uploading states', () => {
    expect(buttons(renderChatInput({ value: '' })).at(-1)?.props.disabled).toBe(true)
    expect(buttons(renderChatInput({ value: 'hello', disabled: true })).at(-1)?.props.disabled).toBe(true)
    expect(buttons(renderChatInput({ value: 'hello', isLoading: true })).at(-1)?.props.disabled).toBe(true)
    expect(buttons(renderChatInput({ value: 'hello', isUploading: true })).at(-1)?.props.disabled).toBe(true)
    expect(buttons(renderChatInput({ value: 'hello' })).at(-1)?.props.disabled).toBe(false)
  })

  test('shows stop action instead of send while streaming', () => {
    const onStop = mock(() => undefined)
    const onSubmit = mock(() => undefined)
    const tree = renderChatInput({ value: 'hello', isStreaming: true, onStop, onSubmit })

    act(() => {
      buttons(tree).at(-1)?.props.onClick()
    })

    expect(onStop).toHaveBeenCalledTimes(1)
    expect(onSubmit).not.toHaveBeenCalled()
  })

  test('submits controlled attachments, clears them, and revokes previews', () => {
    const file = fileFixture({ previewUrl: 'blob:old-preview' })
    const onSubmit = mock(() => undefined)
    const onFilesChange = mock(() => undefined)
    const tree = renderChatInput({ value: '', files: [file], onFilesChange, onSubmit })

    act(() => {
      buttons(tree).at(-1)?.props.onClick()
    })

    expect(onSubmit).toHaveBeenCalledWith('', [file])
    expect(onFilesChange).toHaveBeenCalledWith([])
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:old-preview')
  })

  test('adds only allowed dropped files and respects max file slots', () => {
    const existingFile = fileFixture({ id: 'existing', name: 'existing.txt' })
    const image = new File(['img'], 'image.png', { type: 'image/png' })
    const document = new File(['doc'], 'doc.pdf', { type: 'application/pdf' })
    const ignored = new File(['zip'], 'archive.zip', { type: 'application/zip' })
    const onFilesChange = mock(() => undefined)
    const tree = renderChatInput({
      files: [existingFile],
      onFilesChange,
      allowAttachments: true,
      enableFileUpload: true,
      maxFiles: 3,
    })

    act(() => {
      tree.root.children[0].props.onDrop({
        preventDefault: mock(() => undefined),
        stopPropagation: mock(() => undefined),
        dataTransfer: { files: [image, document, ignored] },
      })
    })

    const nextFiles = onFilesChange.mock.calls[0][0] as ChatInputFile[]
    expect(nextFiles.map((file) => file.name)).toEqual(['existing.txt', 'image.png', 'doc.pdf'])
    expect(nextFiles[1].previewUrl).toBe('blob:preview')
    expect(nextFiles[2].isDocument).toBe(true)
  })

  test('disables attachment control when max files is reached', () => {
    const tree = renderChatInput({ files: [fileFixture()], maxFiles: 1, onFilesChange: mock(() => undefined) })

    expect(fileInput(tree).props.disabled).toBe(true)
    expect(buttons(tree).find((button) => button.props.className.includes('h-9 w-9'))?.props.disabled).toBe(true)
  })
})
