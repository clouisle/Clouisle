'use client'

import { PlatformHeader } from '@/components/layout/platform-header'
import { TeamProvider } from '@/contexts/team-context'

export default function PlatformLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <TeamProvider>
      <div className="h-screen flex flex-col overflow-hidden">
        <PlatformHeader />
        <main className="flex-1 relative overflow-hidden">
          {children}
        </main>
      </div>
    </TeamProvider>
  )
}
