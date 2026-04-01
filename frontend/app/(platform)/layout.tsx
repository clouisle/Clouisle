'use client'

import { usePathname } from 'next/navigation'
import { PlatformHeader } from '@/components/layout/platform-header'
import { TeamProvider } from '@/contexts/team-context'
import { PasswordExpirationBanner } from '@/components/password-expiration-banner'

export default function PlatformLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const pathname = usePathname()

  // 工作流编辑页面不显示顶部导航
  const isWorkflowEditor = pathname?.match(/^\/app\/apps\/workflow\/[^/]+$/)
  // 代理编排页使用内部滚动，避免 main 被撑高
  const isAgentConfig = pathname?.match(/^\/app\/apps\/[^/]+$/)

  if (isWorkflowEditor) {
    return (
      <TeamProvider>
        <div className="h-screen flex flex-col overflow-hidden">
          <main className="flex-1 relative overflow-hidden">
            {children}
          </main>
        </div>
      </TeamProvider>
    )
  }

  return (
    <TeamProvider>
      <div className="h-screen flex flex-col overflow-hidden">
        <PlatformHeader />
        <PasswordExpirationBanner />
        <main className={`flex-1 relative ${isAgentConfig ? 'overflow-hidden' : 'overflow-y-auto'}`}>
          {children}
        </main>
      </div>
    </TeamProvider>
  )
}
