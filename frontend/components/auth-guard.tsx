'use client'

import * as React from 'react'
import { usePathname, useRouter, useSearchParams } from 'next/navigation'
import { authApi } from '@/lib/api'

function getLoginUrl(pathname: string | null, searchParams: URLSearchParams): string {
  const path = pathname || '/'
  const query = searchParams.toString()
  const current = query ? `${path}?${query}` : path
  return `/login?redirect=${encodeURIComponent(current)}`
}

export function AuthGuard({ children }: { children: React.ReactNode }) {
  const router = useRouter()
  const pathname = usePathname()
  const searchParams = useSearchParams()
  const [isVerified, setIsVerified] = React.useState(false)

  React.useEffect(() => {
    if (isVerified) return

    let cancelled = false
    const loginUrl = getLoginUrl(pathname, searchParams)

    async function verifyAuth() {
      if (!localStorage.getItem('access_token')) {
        router.replace(loginUrl)
        return
      }

      try {
        await authApi.getCurrentUser()
        if (!cancelled) setIsVerified(true)
      } catch {
        if (!cancelled) router.replace(loginUrl)
      }
    }

    verifyAuth()

    return () => {
      cancelled = true
    }
  }, [isVerified, pathname, router, searchParams])

  if (!isVerified) return null

  return <>{children}</>
}
