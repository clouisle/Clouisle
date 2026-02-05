'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useTeam } from '@/contexts/team-context'

/**
 * Hook to require a team to be selected.
 * Redirects to /app if no team is available after loading.
 */
export function useRequireTeam() {
  const router = useRouter()
  const { currentTeam, isLoading } = useTeam()

  useEffect(() => {
    if (!isLoading && !currentTeam) {
      router.replace('/app')
    }
  }, [isLoading, currentTeam, router])

  return { currentTeam, isLoading, hasTeam: !!currentTeam }
}
