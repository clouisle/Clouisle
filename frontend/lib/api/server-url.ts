import 'server-only'

import { API_BASE_URL } from '@/lib/constants'

export function getServerApiBaseUrl(): string {
  if (API_BASE_URL.startsWith('http://') || API_BASE_URL.startsWith('https://')) {
    return API_BASE_URL
  }

  const backendUrl = process.env.BACKEND_INTERNAL_URL || 'http://localhost:8000'
  return `${backendUrl}${API_BASE_URL}`
}

export function getServerBackendOrigin(): string {
  return getServerApiBaseUrl().replace(/\/api\/v1\/?$/, '')
}
