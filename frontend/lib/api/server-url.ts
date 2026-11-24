import 'server-only'

import { API_BASE_URL } from '@/lib/constants'

export function getServerApiBaseUrl(): string {
  const backendUrl = process.env.BACKEND_INTERNAL_URL || 'http://localhost:8000'
  return `${backendUrl.replace(/\/+$/, '')}${API_BASE_URL}`
}

export async function getPublicSiteOrigin(): Promise<string | undefined> {
  try {
    const response = await fetch(`${getServerApiBaseUrl()}/site-settings/public`, { cache: 'no-store' })
    if (!response.ok) return undefined
    const { data } = await response.json()
    const url = new URL(data?.site_url)
    if (url.protocol === 'https:' || url.protocol === 'http:') return url.origin
  } catch {
    // Metadata can be rendered without a share image before the site is configured.
  }
  return undefined
}
