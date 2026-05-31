'use client'

import { TeamProvider } from '@/contexts/team-context'

export function AdminAppEditProviders({ children }: { children: React.ReactNode }) {
  return <TeamProvider>{children}</TeamProvider>
}
