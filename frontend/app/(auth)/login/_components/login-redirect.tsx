'use client'

import { useEffect } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { authApi } from '@/lib/api'

export function LoginRedirect() {
  const router = useRouter()
  const searchParams = useSearchParams()

  useEffect(() => {
    let cancelled = false

    async function redirectIfAuthenticated() {
      const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null
      if (!token) return

      try {
        await authApi.getCurrentUser({ skipAuthRedirect: true, silent: true })
        if (cancelled) return

        const redirect = searchParams?.get('redirect')
        router.replace(redirect || '/app')
      } catch {
        if (typeof window !== 'undefined') {
          localStorage.removeItem('access_token')
        }
      }
    }

    redirectIfAuthenticated()

    return () => {
      cancelled = true
    }
  }, [router, searchParams])

  return null
}
