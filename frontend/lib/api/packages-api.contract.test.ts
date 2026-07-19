import { beforeEach, describe, expect, mock, test } from 'bun:test'

const post = mock()
const get = mock()

mock.module('./client', () => ({
  api: { post },
  axiosInstance: { get },
}))

const { adminPackagesApi, packagesApi } = await import('./packages')

describe('packages API contracts', () => {
  beforeEach(() => {
    post.mockReset()
    get.mockReset()
  })

  test('uploads preview files and installs through user and admin routes', async () => {
    const file = new File(['package'], 'tool.clouisle')
    const input = { action: 'rename' as const, target_name: 'Imported tool' }
    post.mockResolvedValueOnce({ session_id: 'session-1' }).mockResolvedValueOnce({ skipped: false })

    await packagesApi.preview('team-1', file)
    await adminPackagesApi.install('session-1', input)

    const [previewPath, formData, previewConfig] = post.mock.calls[0]
    expect(previewPath).toBe('/packages/import/preview')
    expect(formData).toBeInstanceOf(FormData)
    expect(formData.get('team_id')).toBe('team-1')
    const uploadedFile = formData.get('file') as File
    expect(uploadedFile.name).toBe('tool.clouisle')
    expect(await uploadedFile.text()).toBe('package')
    expect(previewConfig).toEqual({
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 120000,
    })
    expect(post).toHaveBeenLastCalledWith('/admin/packages/import/session-1/install', input)
  })

  test('exports the blob using the endpoint and server filename', async () => {
    const blob = new Blob(['package'])
    get.mockResolvedValue({
      data: blob,
      headers: { 'content-disposition': "attachment; filename*=UTF-8''tool%20export.clouisle" },
    })

    await expect(packagesApi.export('tool', 'tool-1')).resolves.toEqual({
      blob,
      filename: 'tool export.clouisle',
    })
    expect(get).toHaveBeenCalledWith('/packages/tool/tool-1/export', { responseType: 'blob' })
  })

  test('propagates export failures', async () => {
    const error = new Error('network failure')
    get.mockRejectedValue(error)

    await expect(adminPackagesApi.export('workflow', 'workflow-1')).rejects.toBe(error)
  })
})
