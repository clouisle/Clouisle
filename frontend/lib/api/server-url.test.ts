import { afterEach, describe, expect, it, mock, spyOn } from 'bun:test'

mock.module('server-only', () => ({}))

const { getServerApiBaseUrl, getPublicSiteOrigin } = await import('./server-url')
const originalBackendInternalUrl = process.env.BACKEND_INTERNAL_URL

afterEach(() => {
  if (originalBackendInternalUrl === undefined) delete process.env.BACKEND_INTERNAL_URL
  else process.env.BACKEND_INTERNAL_URL = originalBackendInternalUrl
})

describe('server URL helpers', () => {
  it('uses the local backend by default', () => {
    delete process.env.BACKEND_INTERNAL_URL
    expect(getServerApiBaseUrl()).toBe('http://localhost:8000/api/v1')
  })

  it('appends the fixed API prefix to the configured internal backend origin', () => {
    process.env.BACKEND_INTERNAL_URL = 'http://backend:8000/'
    expect(getServerApiBaseUrl()).toBe('http://backend:8000/api/v1')
  })

  it('loads the public origin through the internal API', async () => {
    process.env.BACKEND_INTERNAL_URL = 'http://backend:8000'
    const fetchMock = spyOn(globalThis, 'fetch').mockResolvedValue(
      Response.json({ data: { site_url: 'https://app.example.test/' } }),
    )
    try {
      await expect(getPublicSiteOrigin()).resolves.toBe('https://app.example.test')
      expect(fetchMock).toHaveBeenCalledWith('http://backend:8000/api/v1/site-settings/public', { cache: 'no-store' })
    } finally {
      fetchMock.mockRestore()
    }
  })

  it.each([
    ['non-success status', () => Promise.resolve(new Response(null, { status: 503 }))],
    ['missing URL', () => Promise.resolve(Response.json({ data: null }))],
    ['unsupported protocol', () => Promise.resolve(Response.json({ data: { site_url: 'ftp://app.example.test' } }))],
    ['network failure', () => Promise.reject(new Error('offline'))],
  ] as const)('omits the public origin on %s', async (_, respond) => {
    const fetchMock = spyOn(globalThis, 'fetch').mockImplementation(respond)
    try {
      await expect(getPublicSiteOrigin()).resolves.toBeUndefined()
    } finally {
      fetchMock.mockRestore()
    }
  })
})
