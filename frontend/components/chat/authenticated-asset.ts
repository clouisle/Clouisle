'use client'
import * as React from 'react'

type AuthenticatedAssetCacheEntry = {
  objectUrl?: string
  promise?: Promise<string>
}

const MAX_AUTHENTICATED_ASSET_CACHE_SIZE = 100
const authenticatedAssetCache = new Map<string, AuthenticatedAssetCacheEntry>()
const authenticatedAssetTokenListeners = new Set<() => void>()

let authenticatedAssetToken: string | null = null

export function setAuthenticatedAssetToken(token: string | null): void {
  if (authenticatedAssetToken === token) return
  authenticatedAssetToken = token
  for (const listener of authenticatedAssetTokenListeners) listener()
}

function subscribeAuthenticatedAssetToken(listener: () => void): () => void {
  authenticatedAssetTokenListeners.add(listener)
  return () => authenticatedAssetTokenListeners.delete(listener)
}

function getAuthenticatedAssetToken(): string | null {
  return authenticatedAssetToken || getDefaultAssetToken()
}

export function useAuthenticatedAssetToken(): string | null {
  return React.useSyncExternalStore(
    subscribeAuthenticatedAssetToken,
    getAuthenticatedAssetToken,
    getAuthenticatedAssetToken,
  )
}

function getDefaultAssetToken(): string | null {
  return typeof localStorage !== 'undefined'
    ? localStorage.getItem('access_token')
    : null
}
function getAssetCacheKey(src: string, token: string | null): string {
  return `${token ?? ''}\u0000${src}`
}

export function useAuthenticatedAssetUrl(src: string): {
  src: string | null
  loading: boolean
  error: boolean
} {
  const token = useAuthenticatedAssetToken()
  const apiUrl = getAuthenticatedApiAssetUrl(src)
  const blocked = isBlockedAssetSrc(src)
  const initialSrc = blocked ? null : apiUrl ? getCachedAuthenticatedAssetUrl(apiUrl, token) : src
  const [resolvedSrc, setResolvedSrc] = React.useState<string | null>(initialSrc)
  const [loading, setLoading] = React.useState(Boolean(apiUrl && !initialSrc))
  const [error, setError] = React.useState(false)

  React.useEffect(() => {
    let cancelled = false
    if (blocked) {
      setResolvedSrc(null)
      setLoading(false)
      setError(true)
    } else if (!apiUrl) {
      setResolvedSrc(src)
      setLoading(false)
      setError(false)
    } else {
      const cachedUrl = getCachedAuthenticatedAssetUrl(apiUrl, token)
      if (cachedUrl) {
        setResolvedSrc(cachedUrl)
        setLoading(false)
        setError(false)
      } else {
        setResolvedSrc(null)
        setLoading(true)
        setError(false)
        void loadAuthenticatedAssetUrl(apiUrl, token)
          .then((url) => {
            if (!cancelled) setResolvedSrc(url)
          })
          .catch(() => {
            if (!cancelled) setError(true)
          })
          .finally(() => {
            if (!cancelled) setLoading(false)
          })
      }
    }

    return () => {
      cancelled = true
    }
  }, [apiUrl, blocked, src, token])

  return { src: resolvedSrc, loading, error }
}

export function isBlockedAssetSrc(src: string): boolean {
  const normalized = src.trim().toLowerCase()
  if (normalized.startsWith('javascript:') || normalized.startsWith('vbscript:')) {
    return true
  }
  return normalized.startsWith('data:')
    && !normalized.startsWith('data:image/')
    && !normalized.startsWith('data:video/')
}
export function isAllowedAssetDownloadUrl(src: string): boolean {
  if (isBlockedAssetSrc(src)) return false
  try {
    const parsed = new URL(src, window.location.href)
    return parsed.protocol === 'http:' || parsed.protocol === 'https:' || parsed.protocol === 'blob:'
  } catch {
    return false
  }
}

export function getAuthenticatedApiAssetUrl(src: string): string | null {
  if (src.startsWith('/api/v1/')) return src

  try {
    const parsed = new URL(
      src,
      typeof window !== 'undefined' ? window.location.origin : 'http://localhost',
    )
    if (!parsed.pathname.startsWith('/api/v1/')) return null

    const browserOrigin = typeof window !== 'undefined' ? window.location.origin : null
    if (parsed.origin === browserOrigin || parsed.origin === getConfiguredApiOrigin()) {
      return `${parsed.pathname}${parsed.search}`
    }
  } catch {
    return null
  }
  return null
}

function getConfiguredApiOrigin(): string | null {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL
  if (!apiUrl) return null
  try {
    return new URL(apiUrl).origin
  } catch {
    return null
  }
}

export function getCachedAuthenticatedAssetUrl(
  src: string,
  token: string | null = getDefaultAssetToken(),
): string | null {
  return authenticatedAssetCache.get(getAssetCacheKey(src, token))?.objectUrl ?? null
}

function deleteAuthenticatedAssetCache(cacheKey: string): void {
  const entry = authenticatedAssetCache.get(cacheKey)
  if (entry?.objectUrl) URL.revokeObjectURL(entry.objectUrl)
  authenticatedAssetCache.delete(cacheKey)
}

function setAuthenticatedAssetCache(
  cacheKey: string,
  entry: AuthenticatedAssetCacheEntry,
): void {
  const previous = authenticatedAssetCache.get(cacheKey)
  if (previous?.objectUrl && previous.objectUrl !== entry.objectUrl) {
    URL.revokeObjectURL(previous.objectUrl)
  }
  authenticatedAssetCache.set(cacheKey, entry)

  while (authenticatedAssetCache.size > MAX_AUTHENTICATED_ASSET_CACHE_SIZE) {
    const oldestKey = authenticatedAssetCache.keys().next().value
    if (oldestKey === undefined) return
    deleteAuthenticatedAssetCache(oldestKey)
  }
}

export function clearAuthenticatedAssetCache(): void {
  for (const entry of authenticatedAssetCache.values()) {
    if (entry.objectUrl) URL.revokeObjectURL(entry.objectUrl)
  }
  authenticatedAssetCache.clear()
}

export async function fetchAuthenticatedAssetBlob(
  src: string,
  token: string | null = getDefaultAssetToken(),
): Promise<Blob> {
  const response = await fetch(src, {
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
  })
  if (!response.ok) {
    throw new Error(`asset_load_failed:${response.status}`)
  }
  return response.blob()
}

export function loadAuthenticatedAssetUrl(
  src: string,
  token: string | null = getDefaultAssetToken(),
): Promise<string> {
  const cacheKey = getAssetCacheKey(src, token)
  const cached = authenticatedAssetCache.get(cacheKey)
  if (cached?.objectUrl) return Promise.resolve(cached.objectUrl)
  if (cached?.promise) return cached.promise

  const promise = fetchAuthenticatedAssetBlob(src, token)
    .then((blob) => {
      const objectUrl = URL.createObjectURL(blob)
      if (authenticatedAssetCache.get(cacheKey)?.promise !== promise) {
        URL.revokeObjectURL(objectUrl)
        throw new Error('asset_load_evicted')
      }
      setAuthenticatedAssetCache(cacheKey, { objectUrl })
      return objectUrl
    })
    .catch((error) => {
      if (authenticatedAssetCache.get(cacheKey)?.promise === promise) {
        authenticatedAssetCache.delete(cacheKey)
      }
      throw error
    })

  setAuthenticatedAssetCache(cacheKey, { promise })
  return promise
}

export async function downloadAuthenticatedAsset(
  url: string,
  filename: string,
  token: string | null = getDefaultAssetToken(),
): Promise<void> {
  let objectUrl: string | null = null
  let shouldRevoke = false

  try {
    const authenticatedUrl = getAuthenticatedApiAssetUrl(url)
    if (authenticatedUrl) {
      const blob = await fetchAuthenticatedAssetBlob(authenticatedUrl, token)
      objectUrl = URL.createObjectURL(blob)
      shouldRevoke = true
    } else {
      if (!isAllowedAssetDownloadUrl(url)) {
        throw new Error('asset_download_not_allowed')
      }
      objectUrl = url
    }

    const link = document.createElement('a')
    link.href = objectUrl
    link.download = filename
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
  } finally {
    if (shouldRevoke && objectUrl) URL.revokeObjectURL(objectUrl)
  }
}
