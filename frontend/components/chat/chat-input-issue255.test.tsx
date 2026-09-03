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

function render(props: React.ComponentProps<typeof ChatInput>) {
  let tree!: TestRenderer.ReactTestRenderer
  act(() => { tree = TestRenderer.create(<ChatInput {...props} />) })
  return tree
}

function textarea(tree: TestRenderer.ReactTestRenderer) {
  return tree.root.findByProps({ 'data-testid': 'chat-input' })
}

function attachment(name: string, type: string, size = 1) {
  return new File([new Uint8Array(size)], name, { type })
}

function item(file: File | null, kind = 'file') {
  return { kind, getAsFile: () => file }
}

function controlledFile(overrides: Partial<ChatInputFile> = {}): ChatInputFile {
  const file = attachment('photo.png', 'image/png')
  return { id: 'photo', name: file.name, size: file.size, type: file.type, file, previewUrl: 'blob:old', ...overrides }
}

afterEach(() => {
  createObjectURL.mockClear()
  revokeObjectURL.mockClear()
})

describe('ChatInput attachment interactions', () => {
  test('selects valid files, rejects oversized documents, and clears the picker', () => {
    const onFilesChange = mock(() => undefined)
    const tree = render({
      files: [],
      onFilesChange,
      enableFileUpload: true,
      fileUploadConfig: { max_file_size: 2, max_files: 5, max_content_length: 100, truncate_strategy: 'end', allowed_extensions: ['.txt'] },
    })
    const input = tree.root.findByType('input')
    act(() => { input.props.onChange({ target: { files: [attachment('large.txt', 'text/plain', 3)] } }) })
    expect(onFilesChange).not.toHaveBeenCalled()
    expect(tree.root.findByProps({ className: 'mb-2 text-xs text-destructive' }).children.join('')).toContain('fileTooLarge')

    act(() => { input.props.onChange({ target: { files: [attachment('photo.png', 'image/png')] } }) })
    const added = onFilesChange.mock.calls[0][0] as ChatInputFile[]
    expect(added).toHaveLength(1)
    expect(added[0]).toMatchObject({ name: 'photo.png', previewUrl: 'blob:preview', isDocument: false })
  })

  test('pastes enabled image and document types while ignoring other clipboard items', () => {
    const onFilesChange = mock(() => undefined)
    const preventDefault = mock(() => undefined)
    const tree = render({ files: [], onFilesChange, allowAttachments: true, enableFileUpload: true, maxFiles: 2 })

    act(() => {
      textarea(tree).props.onPaste({
        preventDefault,
        clipboardData: { items: [item(null), item(attachment('note.txt', 'text/plain')), item(attachment('photo.png', 'image/png')), item(attachment('archive.zip', 'application/zip')), item(attachment('ignored.png', 'image/png'), 'string')] },
      })
    })

    const added = onFilesChange.mock.calls[0][0] as ChatInputFile[]
    expect(preventDefault).toHaveBeenCalledTimes(1)
    expect(added.map((file) => file.name)).toEqual(['note.txt', 'photo.png'])
    expect(added.map((file) => file.isDocument)).toEqual([true, false])
  })

  test('handles drag state and drops only enabled file types into remaining slots', () => {
    const existing = controlledFile({ id: 'existing', name: 'existing.png' })
    const onFilesChange = mock(() => undefined)
    const event = { preventDefault: mock(() => undefined), stopPropagation: mock(() => undefined) }
    const tree = render({ files: [existing], onFilesChange, allowAttachments: true, enableFileUpload: true, maxFiles: 3 })
    const zone = tree.root.children[0] as TestRenderer.ReactTestInstance

    act(() => { zone.props.onDragEnter(event) })
    expect(tree.root.findAllByType('p').some((node) => node.children.includes('dropFiles'))).toBe(true)
    act(() => { zone.props.onDragOver(event) })
    expect(event.preventDefault).toHaveBeenCalled()

    act(() => {
      zone.props.onDrop({ ...event, dataTransfer: { files: [attachment('photo.png', 'image/png'), attachment('notes.pdf', 'application/pdf'), attachment('archive.zip', 'application/zip')] } })
    })
    expect((onFilesChange.mock.calls[0][0] as ChatInputFile[]).map((file) => file.name)).toEqual(['existing.png', 'photo.png', 'notes.pdf'])
  })

  test('renders upload progress and removes completed previews with URL cleanup', () => {
    const image = controlledFile({ isUploading: true, uploadProgress: 42.4 })
    const document = controlledFile({ id: 'doc', name: 'guide.pdf', type: 'application/pdf', previewUrl: undefined, isDocument: true, size: 2048 })
    const onFilesChange = mock(() => undefined)
    const tree = render({ files: [image, document], onFilesChange })

    expect(tree.root.findAllByType('span').some((node) => node.children.join('') === '42%')).toBe(true)
    expect(tree.root.findAllByType('span').some((node) => node.children.join('') === '2KB')).toBe(true)
    const remove = tree.root.findAllByType('button').find((button) => button.props.className?.includes('ml-0.5'))
    act(() => { remove?.props.onClick() })

    expect(onFilesChange).toHaveBeenCalledWith([image])
    expect(revokeObjectURL).not.toHaveBeenCalled()

    act(() => { tree.update(<ChatInput files={[controlledFile()]} onFilesChange={onFilesChange} />) })
    const imageRemove = tree.root.findAllByType('button').find((button) => button.props.className?.includes('-top-1.5'))
    act(() => { imageRemove?.props.onClick() })
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:old')
  })
  test('blocks attachment selection, paste, and drop while disabled', () => {
    const onFilesChange = mock(() => undefined)
    const preventDefault = mock(() => undefined)
    const stopPropagation = mock(() => undefined)
    const image = attachment('photo.png', 'image/png')
    const tree = render({
      disabled: true,
      files: [],
      onFilesChange,
      allowAttachments: true,
      enableFileUpload: true,
    })
    const fileInput = tree.root.findAllByType('input').find((node) => node.props.type === 'file')
    expect(fileInput?.props.disabled).toBe(true)

    act(() => { fileInput?.props.onChange({ target: { files: [image] } }) })
    act(() => {
      textarea(tree).props.onPaste({
        preventDefault,
        clipboardData: { items: [item(image)] },
      })
    })
    act(() => {
      const zone = tree.root.children[0] as TestRenderer.ReactTestInstance
      zone.props.onDrop({
        preventDefault,
        stopPropagation,
        dataTransfer: { files: [image] },
      })
    })

    expect(onFilesChange).not.toHaveBeenCalled()
  })
})
