'use client'

import { usePathname } from 'next/navigation'
import { PlatformHeader } from '@/components/layout/platform-header'
import { TeamProvider } from '@/contexts/team-context'
import { PasswordExpirationBanner } from '@/components/password-expiration-banner'
import { AuthGuard } from '@/components/auth-guard'
import { OnboardingProvider } from '@/components/onboarding/onboarding-provider'
import { OnboardingTour, allTourIds } from '@/components/onboarding/onboarding-tour'

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

  // Render all onboarding tours
  const renderTours = () => (
    <>
      {allTourIds.map(tourId => (
        <OnboardingTour key={tourId} tourId={tourId} />
      ))}
    </>
  )

  if (isWorkflowEditor) {
    return (
      <AuthGuard>
        <TeamProvider>
          <OnboardingProvider>
            <div className="h-screen flex flex-col overflow-hidden">
              <main className="flex-1 relative overflow-hidden">
                {children}
              </main>
              {renderTours()}
            </div>
          </OnboardingProvider>
        </TeamProvider>
      </AuthGuard>
    )
  }

  return (
    <AuthGuard>
      <TeamProvider>
        <OnboardingProvider>
          <div className="h-screen flex flex-col overflow-hidden">
            <PlatformHeader />
            <PasswordExpirationBanner />
            <main className={`flex-1 relative ${isAgentConfig ? 'overflow-hidden' : 'overflow-y-auto'}`}>
              {children}
            </main>
            {renderTours()}
          </div>
        </OnboardingProvider>
      </TeamProvider>
    </AuthGuard>
  )
}
