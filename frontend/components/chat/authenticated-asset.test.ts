import { afterEach, describe, expect, mock, test } from 'bun:test'
import { Window } from 'happy-dom'
import React, { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import {
  clearAuthenticatedAssetCache,
  downloadAuthenticatedAsset,
  fetchAuthenticatedAssetBlob,
  getAuthenticatedApiAssetUrl,
  isAllowedAssetDownloadUrl,
  loadAuthenticatedAssetUrl,
  setAuthenticatedAssetToken,
  useAuthenticatedAssetToken,
} from './authenticated-asset'

const originalFetch = globalThis.fetch
const originalCreateObjectURL = URL.createObjectURL
const originalRevokeObjectURL = URL.revokeObjectURL
const window = new Window({ url: 'http://localhost' })
Object.assign(globalThis, {
  window,
  document: window.document,
  navigator: window.navigator,
  Element: window.Element,
  HTMLElement: window.HTMLElement,
  Node: window.Node,
})
;(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true

const roots: Root[] = []

afterEach(() => {
  for (const root of roots.splice(0)) act(() => root.unmount())
  document.body.replaceChildren()
  setAuthenticatedAssetToken(null)
  clearAuthenticatedAssetCache()
  globalThis.fetch = originalFetch
  URL.createObjectURL = originalCreateObjectURL
  URL.revokeObjectURL = originalRevokeObjectURL
})

describe('authenticated assets', () => {
  test('recognizes relative and same-origin API paths as authenticated assets', () => {
    expect(getAuthenticatedApiAssetUrl('/api/v1/upload/files/sandbox-artifacts/2026/09/a.txt')).toBe(
      '/api/v1/upload/files/sandbox-artifacts/2026/09/a.txt',
    )
    expect(
      getAuthenticatedApiAssetUrl('http://localhost/api/v1/upload/files/sandbox-artifacts/2026/09/a.txt'),
    ).toBe('/api/v1/upload/files/sandbox-artifacts/2026/09/a.txt')
    expect(
      getAuthenticatedApiAssetUrl('http://localhost:8000/api/v1/upload/files/sandbox-artifacts/2026/09/a.txt'),
    ).toBeNull()
    expect(getAuthenticatedApiAssetUrl('https://cdn.example.test/a.txt')).toBeNull()
  })

  test('updates mounted token consumers when the embedded token changes', () => {
    function TokenValue() {
      return React.createElement('output', null, useAuthenticatedAssetToken() ?? 'none')
    }

    const container = document.body.appendChild(document.createElement('div'))
    const root = createRoot(container)
    roots.push(root)
    act(() => root.render(React.createElement(TokenValue)))
    expect(container.textContent).toBe('none')

    act(() => setAuthenticatedAssetToken('embed-token'))
    expect(container.textContent).toBe('embed-token')
  })

  test('allows only safe non-API download URLs', () => {
    expect(isAllowedAssetDownloadUrl('https://cdn.example.test/file.txt')).toBe(true)
    expect(isAllowedAssetDownloadUrl('blob:asset')).toBe(true)
    expect(isAllowedAssetDownloadUrl('javascript:alert(1)')).toBe(false)
    expect(isAllowedAssetDownloadUrl('data:text/html;base64,PHNjcmlwdD4=')).toBe(false)
  })

  test('rejects blocked non-API download URLs before creating an anchor', async () => {
    await expect(downloadAuthenticatedAsset('javascript:alert(1)', 'unsafe.txt')).rejects.toThrow(
      'asset_download_not_allowed',
    )
    expect(document.querySelector('a')).toBeNull()
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
