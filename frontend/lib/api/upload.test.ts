import { afterEach, beforeEach, describe, expect, mock, spyOn, test } from 'bun:test'
import type { AxiosProgressEvent, AxiosRequestConfig } from 'axios'

import { api, axiosInstance } from './client'
import { uploadApi, type UploadResult } from './upload'

const uploadResult: UploadResult = {
  url: '/api/v1/upload/files/general/2026/07/report.txt',
  filename: 'report.txt',
  original_name: 'report.txt',
  size: 7,
  content_type: 'text/plain',
}

let post: ReturnType<typeof spyOn>
let remove: ReturnType<typeof spyOn>

beforeEach(() => {
  post = spyOn(axiosInstance, 'post').mockResolvedValue({ data: { data: uploadResult } })
  remove = spyOn(api, 'delete').mockResolvedValue(undefined)
})

afterEach(() => {
  post.mockRestore()
  remove.mockRestore()
})

describe('upload API', () => {
  test('uploads image and file FormData to category-encoded routes', async () => {
    const file = new File(['content'], 'report.txt', { type: 'text/plain' })

    expect(await uploadApi.uploadImage(file, 'team docs')).toBe(uploadResult)
    expect(await uploadApi.uploadFile(file, 'legal/review')).toBe(uploadResult)

    expect(post).toHaveBeenNthCalledWith(
      1,
      '/upload/image?category=team%20docs',
      expect.any(FormData),
      { headers: { 'Content-Type': 'multipart/form-data' } }
    )
    expect(post).toHaveBeenNthCalledWith(
      2,
      '/upload/file?category=legal%2Freview',
      expect.any(FormData),
      { headers: { 'Content-Type': 'multipart/form-data' } }
    )
    const imageFile = (post.mock.calls[0][1] as FormData).get('file') as File
    const uploadedFile = (post.mock.calls[1][1] as FormData).get('file') as File
    expect([imageFile.name, await imageFile.text()]).toEqual(['report.txt', 'content'])
    expect([uploadedFile.name, await uploadedFile.text()]).toEqual(['report.txt', 'content'])
  })

  test('reports upload progress only when total is available', async () => {
    const onProgress = mock(() => undefined)
    await uploadApi.uploadFileWithProgress(new File(['content'], 'report.txt'), undefined, onProgress)
    const config = post.mock.calls[0][2] as AxiosRequestConfig

    config.onUploadProgress?.({ loaded: 5, total: 8 } as AxiosProgressEvent)
    config.onUploadProgress?.({ loaded: 6 } as AxiosProgressEvent)

    expect(post.mock.calls[0][0]).toBe('/upload/file?category=general')
    expect(onProgress).toHaveBeenCalledTimes(1)
    expect(onProgress).toHaveBeenCalledWith({ loaded: 5, total: 8, percent: 63 })
  })

  test('builds parse routes and multipart bodies from query options', async () => {
    const first = new File(['one'], 'one.txt')
    const second = new File(['two'], 'two.txt')
    post
      .mockResolvedValueOnce({ data: { data: { filename: 'one.txt' } } })
      .mockResolvedValueOnce({ data: { data: [{ filename: 'one.txt' }, { filename: 'two.txt' }] } })
      .mockResolvedValueOnce({ data: { data: { filename: 'one.txt' } } })

    await uploadApi.parseFile(first, { maxContentLength: 120, truncateStrategy: 'middle' })
    await uploadApi.parseFiles([first, second], { maxContentLength: 5, truncateStrategy: 'start' })
    await uploadApi.parseFile(first)

    expect(post.mock.calls[0][0]).toBe('/upload/parse?max_content_length=120&truncate_strategy=middle')
    expect(((post.mock.calls[0][1] as FormData).get('file') as File).name).toBe('one.txt')
    expect(post.mock.calls[1][0]).toBe('/upload/parse/batch?max_content_length=5&truncate_strategy=start')
    expect((post.mock.calls[1][1] as FormData).getAll('files').map((file) => (file as File).name)).toEqual([
      'one.txt',
      'two.txt',
    ])
    expect(post.mock.calls[2][0]).toBe('/upload/parse')
    expect(post.mock.calls[0][2]).toEqual({ headers: { 'Content-Type': 'multipart/form-data' } })
  })

  test('normalizes full and relative delete paths', async () => {
    await uploadApi.deleteFile('https://files.test/api/v1/upload/files/team/2026/07/report.txt')
    await uploadApi.deleteFile('/api/v1/upload/files/general/2026/07/report.txt')

    expect(remove).toHaveBeenNthCalledWith(1, '/upload/files/team/2026/07/report.txt')
    expect(remove).toHaveBeenNthCalledWith(2, '/upload/files/general/2026/07/report.txt')
  })

  test('returns full URLs for empty, absolute, configured, and default paths', () => {
    const originalBaseUrl = process.env.NEXT_PUBLIC_API_URL

    try {
      expect(uploadApi.getFullUrl('')).toBe('')
      expect(uploadApi.getFullUrl('http://files.test/a.txt')).toBe('http://files.test/a.txt')
      expect(uploadApi.getFullUrl('https://files.test/a.txt')).toBe('https://files.test/a.txt')
      process.env.NEXT_PUBLIC_API_URL = 'https://api.test/api/v1'
      expect(uploadApi.getFullUrl('/api/v1/upload/files/a.txt')).toBe('https://api.test/api/v1/upload/files/a.txt')
      delete process.env.NEXT_PUBLIC_API_URL
      expect(uploadApi.getFullUrl('/api/v1/upload/files/a.txt')).toBe('http://localhost:8000/api/v1/upload/files/a.txt')
    } finally {
      if (originalBaseUrl === undefined) delete process.env.NEXT_PUBLIC_API_URL
      else process.env.NEXT_PUBLIC_API_URL = originalBaseUrl
    }
  })

  test('propagates upload and delete rejections', async () => {
    const uploadError = new Error('upload unavailable')
    const deleteError = new Error('delete unavailable')
    post.mockRejectedValueOnce(uploadError)
    remove.mockRejectedValueOnce(deleteError)

    await expect(uploadApi.uploadFile(new File(['content'], 'report.txt'))).rejects.toBe(uploadError)
    await expect(uploadApi.deleteFile('/api/v1/upload/files/general/report.txt')).rejects.toBe(deleteError)
  })
})
