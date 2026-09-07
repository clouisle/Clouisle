'use client'
import * as React from 'react'

type AuthenticatedAssetCacheEntry = {
  objectUrl?: string
  promise?: Promise<string>
}

const MAX_AUTHENTICATED_ASSET_CACHE_SIZE = 100
const authenticatedAssetCache = new Map<string, AuthenticatedAssetCacheEntry>()

let authenticatedAssetToken: string | null = null

export function setAuthenticatedAssetToken(token: string | null): void {
  authenticatedAssetToken = token
}

export function useAuthenticatedAssetToken(): string | null {
  if (authenticatedAssetToken) return authenticatedAssetToken
  return getDefaultAssetToken()
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
export function getAuthenticatedApiAssetUrl(src: string): string | null {
  if (src.startsWith('/api/v1/')) return src
  try {
    const parsed = new URL(src, typeof window !== 'undefined' ? window.location.origin : 'http://localhost')
    if (parsed.pathname.startsWith('/api/v1/')) {
      return `${parsed.pathname}${parsed.search}`
    }
  } catch {
    return null
  }
  return null
}

export function getCachedAuthenticatedAssetUrl(
  src: string,
  token: string | null = getDefaultAssetToken(),
): string | null {
  return authenticatedAssetCache.get(getAssetCacheKey(src, token))?.objectUrl ?? null
}

function setAuthenticatedAssetCache(
  cacheKey: string,
  entry: AuthenticatedAssetCacheEntry,
) {
  if (entry.objectUrl && authenticatedAssetCache.size >= MAX_AUTHENTICATED_ASSET_CACHE_SIZE) {
    const oldestKey = authenticatedAssetCache.keys().next().value
    if (oldestKey !== undefined) {
      const oldestEntry = authenticatedAssetCache.get(oldestKey)
      if (oldestEntry?.objectUrl) URL.revokeObjectURL(oldestEntry.objectUrl)
      authenticatedAssetCache.delete(oldestKey)
    }
  }

  authenticatedAssetCache.set(cacheKey, entry)
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
      setAuthenticatedAssetCache(cacheKey, { objectUrl })
      return objectUrl
    })
    .catch((error) => {
      authenticatedAssetCache.delete(cacheKey)
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
