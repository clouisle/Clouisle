import { beforeEach, describe, expect, mock, test } from 'bun:test'

const deleteMock = mock(() => Promise.resolve())
const postMock = mock(() => Promise.resolve({ data: { data: undefined } }))

mock.module('./client', () => ({
  api: { delete: deleteMock },
  axiosInstance: { post: postMock },
}))

const { uploadApi } = await import('./upload')

const uploadResult = {
  url: '/api/v1/upload/files/docs/2026/07/file.txt',
  filename: 'file.txt',
  original_name: 'original.txt',
  size: 12,
  content_type: 'text/plain',
}

beforeEach(() => {
  deleteMock.mockClear()
  postMock.mockClear()
  postMock.mockResolvedValue({ data: { data: uploadResult } })
})

describe('uploadApi', () => {
  test('uploads images and files with encoded categories', async () => {
    const file = new File(['content'], 'file.txt', { type: 'text/plain' })

    expect(await uploadApi.uploadImage(file, 'team files')).toEqual(uploadResult)
    expect(await uploadApi.uploadFile(file)).toEqual(uploadResult)

    expect(postMock.mock.calls[0][0]).toBe('/upload/image?category=team%20files')
    expect(postMock.mock.calls[1][0]).toBe('/upload/file?category=general')
    for (const call of postMock.mock.calls) {
      expect(call[1]).toBeInstanceOf(FormData)
      expect(call[2]).toEqual({ headers: { 'Content-Type': 'multipart/form-data' } })
    }
  })

  test('reports upload progress only when total and callback are available', async () => {
    const progress = mock(() => undefined)
    const file = new File(['content'], 'file.txt')

    await uploadApi.uploadFileWithProgress(file, 'docs', progress)
    const config = postMock.mock.calls[0][2] as { onUploadProgress: (event: { loaded: number; total?: number }) => void }
    config.onUploadProgress({ loaded: 2, total: 3 })
    config.onUploadProgress({ loaded: 2 })

    expect(progress).toHaveBeenCalledTimes(1)
    expect(progress).toHaveBeenCalledWith({ loaded: 2, total: 3, percent: 67 })

    await uploadApi.uploadFileWithProgress(file)
    const noCallbackConfig = postMock.mock.calls[1][2] as typeof config
    noCallbackConfig.onUploadProgress({ loaded: 1, total: 2 })
  })

  test('parses one or many files with optional query parameters', async () => {
    const first = new File(['one'], 'one.txt')
    const second = new File(['two'], 'two.txt')

    await uploadApi.parseFile(first)
    await uploadApi.parseFile(first, { maxContentLength: 40, truncateStrategy: 'middle' })
    await uploadApi.parseFiles([first, second], { maxContentLength: 20, truncateStrategy: 'start' })

    expect(postMock.mock.calls.map((call) => call[0])).toEqual([
      '/upload/parse',
      '/upload/parse?max_content_length=40&truncate_strategy=middle',
      '/upload/parse/batch?max_content_length=20&truncate_strategy=start',
    ])
    const batchForm = postMock.mock.calls[2][1] as FormData
    expect(batchForm.getAll('files')).toEqual([first, second])
  })

  test('normalizes stored file URLs before deletion', async () => {
    await uploadApi.deleteFile('https://files.test/api/v1/upload/files/docs/2026/07/file.txt')
    await uploadApi.deleteFile('/api/v1/upload/files/images/picture.png')

    expect(deleteMock.mock.calls).toEqual([
      ['/upload/files/docs/2026/07/file.txt'],
      ['/upload/files/images/picture.png'],
    ])
  })

  test('builds full URLs while preserving absolute and empty values', () => {
    const previous = process.env.NEXT_PUBLIC_API_URL
    process.env.NEXT_PUBLIC_API_URL = 'https://api.test/api/v1'

    expect(uploadApi.getFullUrl('')).toBe('')
    expect(uploadApi.getFullUrl('https://cdn.test/file.txt')).toBe('https://cdn.test/file.txt')
    expect(uploadApi.getFullUrl('http://cdn.test/file.txt')).toBe('http://cdn.test/file.txt')
    expect(uploadApi.getFullUrl('/api/v1/upload/files/file.txt')).toBe('https://api.test/api/v1/upload/files/file.txt')

    if (previous === undefined) delete process.env.NEXT_PUBLIC_API_URL
    else process.env.NEXT_PUBLIC_API_URL = previous
  })
})
