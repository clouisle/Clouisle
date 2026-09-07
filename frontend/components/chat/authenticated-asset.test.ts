import { afterEach, describe, expect, mock, test } from 'bun:test'
import {
  clearAuthenticatedAssetCache,
  fetchAuthenticatedAssetBlob,
  getAuthenticatedApiAssetUrl,
  loadAuthenticatedAssetUrl,
} from './authenticated-asset'

const originalFetch = globalThis.fetch
const originalCreateObjectURL = URL.createObjectURL
const originalRevokeObjectURL = URL.revokeObjectURL

afterEach(() => {
  clearAuthenticatedAssetCache()
  globalThis.fetch = originalFetch
  URL.createObjectURL = originalCreateObjectURL
  URL.revokeObjectURL = originalRevokeObjectURL
})

describe('authenticated assets', () => {
  test('recognizes same-origin API paths and absolute API paths as authenticated assets', () => {
    expect(getAuthenticatedApiAssetUrl('/api/v1/upload/files/sandbox-artifacts/2026/09/a.txt')).toBe(
      '/api/v1/upload/files/sandbox-artifacts/2026/09/a.txt',
    )
    expect(
      getAuthenticatedApiAssetUrl('http://localhost:8000/api/v1/upload/files/sandbox-artifacts/2026/09/a.txt'),
    ).toBe('/api/v1/upload/files/sandbox-artifacts/2026/09/a.txt')
    expect(getAuthenticatedApiAssetUrl('https://cdn.example.test/a.txt')).toBeNull()
  })

  test('sends the provided bearer credential when loading a protected blob', async () => {
    const fetchMock = mock(async () => new Response('secret', { status: 200 }))
    globalThis.fetch = fetchMock as unknown as typeof fetch

    const blob = await fetchAuthenticatedAssetBlob(
      '/api/v1/upload/files/generated-images/2026/09/a.png',
      'embed-key',
    )

    expect(await blob.text()).toBe('secret')
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/upload/files/generated-images/2026/09/a.png',
      { headers: { Authorization: 'Bearer embed-key' } },
    )
  })

  test('deduplicates loads per credential without sharing blobs across credentials', async () => {
    const fetchMock = mock(async () => new Response('secret', { status: 200 }))
    let objectUrlSequence = 0
    globalThis.fetch = fetchMock as unknown as typeof fetch
    URL.createObjectURL = mock(() => `blob:asset-${++objectUrlSequence}`)
    URL.revokeObjectURL = mock(() => undefined)
    const src = '/api/v1/upload/files/sandbox-artifacts/2026/09/a.txt'

    const [first, duplicate] = await Promise.all([
      loadAuthenticatedAssetUrl(src, 'token-a'),
      loadAuthenticatedAssetUrl(src, 'token-a'),
    ])
    const secondCredential = await loadAuthenticatedAssetUrl(src, 'token-b')

    expect(first).toBe('blob:asset-1')
    expect(duplicate).toBe(first)
    expect(secondCredential).toBe('blob:asset-2')
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  test('rejects a protected asset response instead of exposing its URL', async () => {
    globalThis.fetch = mock(async () => new Response('', { status: 403 })) as unknown as typeof fetch

    await expect(
      fetchAuthenticatedAssetBlob(
        '/api/v1/upload/files/generated-videos/2026/09/a.mp4',
        'wrong-key',
      ),
    ).rejects.toThrow('asset_load_failed:403')
  })
})
