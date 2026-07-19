import { afterEach, describe, expect, it, mock, spyOn } from 'bun:test'
import { api, axiosInstance } from './client'
import { adminPackagesApi, downloadBlob, packagesApi, type PackagesApi } from './packages'

const routes: Array<{ api: PackagesApi; prefix: string }> = [
  { api: packagesApi, prefix: '/packages' },
  { api: adminPackagesApi, prefix: '/admin/packages' },
]

let postSpy: ReturnType<typeof spyOn> | undefined
let getSpy: ReturnType<typeof spyOn> | undefined
let createObjectUrlSpy: ReturnType<typeof spyOn> | undefined
let revokeObjectUrlSpy: ReturnType<typeof spyOn> | undefined
const originalDocument = Object.getOwnPropertyDescriptor(globalThis, 'document')

afterEach(() => {
  postSpy?.mockRestore()
  getSpy?.mockRestore()
  createObjectUrlSpy?.mockRestore()
  revokeObjectUrlSpy?.mockRestore()
  postSpy = undefined
  getSpy = undefined
  createObjectUrlSpy = undefined
  revokeObjectUrlSpy = undefined

  if (originalDocument) Object.defineProperty(globalThis, 'document', originalDocument)
  else Reflect.deleteProperty(globalThis, 'document')
})

describe('package request routes', () => {
  for (const { api: packages, prefix } of routes) {
    it(`posts preview FormData to ${prefix}`, async () => {
      const response = { session_id: 'session-1' }
      const file = new File(['package'], 'sample.clouisle')
      postSpy = spyOn(api, 'post').mockResolvedValue(response)

      expect(await packages.preview('team-1', file)).toBe(response)
      expect(postSpy).toHaveBeenCalledTimes(1)

      const [url, payload, config] = postSpy.mock.calls[0]
      expect(url).toBe(`${prefix}/import/preview`)
      expect(payload).toBeInstanceOf(FormData)
      expect((payload as FormData).get('team_id')).toBe('team-1')
      const uploadedFile = (payload as FormData).get('file') as File
      expect(uploadedFile.name).toBe('sample.clouisle')
      expect(await uploadedFile.text()).toBe('package')
      expect(config).toEqual({
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: 120000,
      })
    })

    it(`posts the install payload to ${prefix}`, async () => {
      const input = {
        action: 'rename' as const,
        target_name: 'Imported package',
        dependency_mapping: { source: 'target' },
      }
      const response = { installed: 'resource-1', skipped: false, errors: [], warnings: [] }
      postSpy = spyOn(api, 'post').mockResolvedValue(response)

      expect(await packages.install('session/1', input)).toBe(response)
      expect(postSpy).toHaveBeenCalledWith(`${prefix}/import/session/1/install`, input)
    })
  }

  it('propagates request errors unchanged', async () => {
    const error = new Error('preview failed')
    postSpy = spyOn(api, 'post').mockRejectedValue(error)

    await expect(packagesApi.preview('team-1', new File([], 'bad.clouisle'))).rejects.toBe(error)
    await expect(adminPackagesApi.install('session-1', { action: 'skip' })).rejects.toBe(error)
  })
})

describe('package exports', () => {
  const cases = [
    {
      packages: packagesApi,
      prefix: '/packages',
      disposition: "attachment; filename*=UTF-8''My%20Package.clouisle",
      filename: 'My Package.clouisle',
    },
    {
      packages: adminPackagesApi,
      prefix: '/admin/packages',
      disposition: 'attachment; filename="admin-package.clouisle"',
      filename: 'admin-package.clouisle',
    },
    {
      packages: packagesApi,
      prefix: '/packages',
      disposition: "attachment; filename*=UTF-8''bad%ZZ.clouisle",
      filename: 'bad%ZZ.clouisle',
    },
    {
      packages: adminPackagesApi,
      prefix: '/admin/packages',
      disposition: undefined,
      filename: 'workflow-resource-1.clouisle',
    },
  ]

  for (const { packages, prefix, disposition, filename } of cases) {
    it(`downloads from ${prefix} as ${filename}`, async () => {
      const blob = new Blob(['package'])
      getSpy = spyOn(axiosInstance, 'get').mockResolvedValue({
        data: blob,
        headers: disposition ? { 'content-disposition': disposition } : {},
      })

      expect(await packages.export('workflow', 'resource-1')).toEqual({ blob, filename })
      expect(getSpy).toHaveBeenCalledWith(`${prefix}/workflow/resource-1/export`, {
        responseType: 'blob',
      })
    })
  }

  it('propagates download errors unchanged', async () => {
    const error = new Error('download failed')
    getSpy = spyOn(axiosInstance, 'get').mockRejectedValue(error)

    await expect(packagesApi.export('agent', 'agent-1')).rejects.toBe(error)
  })
})

describe('downloadBlob', () => {
  it('clicks a temporary link and always releases the object URL', () => {
    const click = mock(() => {})
    const remove = mock(() => {})
    const appendChild = mock(() => {})
    const link = { href: '', download: '', click, remove }
    Object.defineProperty(globalThis, 'document', {
      configurable: true,
      value: {
        createElement: mock(() => link),
        body: { appendChild },
      },
    })
    createObjectUrlSpy = spyOn(URL, 'createObjectURL').mockReturnValue('blob:package')
    revokeObjectUrlSpy = spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
    const blob = new Blob(['package'])

    downloadBlob(blob, 'package.clouisle')

    expect(createObjectUrlSpy).toHaveBeenCalledWith(blob)
    expect(link).toMatchObject({ href: 'blob:package', download: 'package.clouisle' })
    expect(appendChild).toHaveBeenCalledWith(link)
    expect(click).toHaveBeenCalledTimes(1)
    expect(remove).toHaveBeenCalledTimes(1)
    expect(revokeObjectUrlSpy).toHaveBeenCalledWith('blob:package')
  })
})
