import { afterEach, describe, expect, mock, spyOn, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from 'react-test-renderer'

const toast = { error: mock(() => {}), success: mock(() => {}) }

mock.module('next-intl', () => ({
  useTranslations: () => (key: string, values?: { allowed?: string }) =>
    values?.allowed ? `${key}:${values.allowed}` : key,
}))
mock.module('next/image', () => ({
  default: (props: React.ImgHTMLAttributes<HTMLImageElement>) => <img alt="" {...props} />,
}))
mock.module('sonner', () => ({ toast }))

import { ApiError, uploadApi } from '@/lib/api'
import { ImageUpload } from './image-upload'

globalThis.IS_REACT_ACT_ENVIRONMENT = true

const renderers: ReactTestRenderer[] = []

function file(name: string, type: string, size = 100) {
  return { name, type, size } as File
}

function render(props: React.ComponentProps<typeof ImageUpload>) {
  const input = { value: '' }
  let renderer: ReactTestRenderer
  act(() => {
    renderer = create(<ImageUpload {...props} />, {
      createNodeMock: element => element.type === 'input' ? input : {},
    })
  })
  renderers.push(renderer!)
  return { input, renderer: renderer! }
}

function input(renderer: ReactTestRenderer) {
  return renderer.root.findByType('input')
}

afterEach(() => {
  for (const renderer of renderers) act(() => renderer.unmount())
  renderers.length = 0
  mock.restore()
  toast.error.mockClear()
  toast.success.mockClear()
})

describe('ImageUpload semantic behavior', () => {
  test('rejects non-images and oversized images without uploading', async () => {
    const upload = spyOn(uploadApi, 'uploadImage')
    const { renderer } = render({})

    await act(async () => input(renderer).props.onChange({ target: { files: [file('notes.txt', 'text/plain')] } }))
    await act(async () => input(renderer).props.onChange({ target: { files: [file('large.png', 'image/png', 10 * 1024 * 1024 + 1)] } }))

    expect(input(renderer).props.accept).toBe('image/*')
    expect(toast.error).toHaveBeenCalledWith('invalidFileType')
    expect(toast.error).toHaveBeenCalledWith('fileTooLarge')
    expect(upload).not.toHaveBeenCalled()
  })

  test('uploads an accepted image, exposes loading state, and cleans up the replaced upload', async () => {
    let complete!: (result: { url: string; filename: string; original_name: string; size: number; content_type: string }) => void
    const upload = spyOn(uploadApi, 'uploadImage').mockReturnValue(new Promise(resolve => { complete = resolve }))
    spyOn(uploadApi, 'getFullUrl').mockReturnValue('https://files.example/new.png')
    const removeOld = spyOn(uploadApi, 'deleteFile').mockResolvedValue()
    const onChange = mock(() => {})
    const oldUrl = '/api/v1/upload/files/general/2026/07/old.png'
    const { input: inputNode, renderer } = render({ value: oldUrl, category: 'avatars', onChange })

    await act(async () => {
      input(renderer).props.onChange({ target: { files: [file('new.png', 'image/png')] } })
      await Promise.resolve()
    })
    expect(input(renderer).props.disabled).toBe(true)

    await act(async () => complete({ url: '/api/v1/upload/files/avatars/2026/07/new.png', filename: 'new.png', original_name: 'new.png', size: 100, content_type: 'image/png' }))

    expect(upload).toHaveBeenCalledWith(expect.anything(), 'avatars')
    expect(onChange).toHaveBeenCalledWith('https://files.example/new.png')
    expect(toast.success).toHaveBeenCalledWith('uploadSuccess')
    expect(removeOld).toHaveBeenCalledWith(oldUrl)
    expect(inputNode.value).toBe('')
    expect(input(renderer).props.disabled).toBe(false)
  })

  test('reports allowed image types and removes only managed files', async () => {
    spyOn(uploadApi, 'uploadImage').mockRejectedValue(new ApiError(1001, 'invalid', { allowed: ['image/png', 'image/jpeg'] }))
    const onChange = mock(() => {})
    const deleteFile = spyOn(uploadApi, 'deleteFile').mockResolvedValue()
    const managed = '/api/v1/upload/files/general/2026/07/image.png'
    const { renderer } = render({ value: managed, onChange })

    await act(async () => input(renderer).props.onChange({ target: { files: [file('bad.gif', 'image/gif')] } }))
    expect(toast.error).toHaveBeenCalledWith('invalidImageFileTypeWithAllowed:image/png, image/jpeg')

    const remove = renderer.root.findByType('button').props.onClick
    await act(async () => remove({ stopPropagation() {} }))
    expect(onChange).toHaveBeenCalledWith('')
    expect(deleteFile).toHaveBeenCalledWith(managed)
  })
})
