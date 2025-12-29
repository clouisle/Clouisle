'use client'

import { SiteSettingsProvider } from '@/contexts/site-settings-context'

export default function ChatLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <SiteSettingsProvider skipTitleUpdate skipFaviconUpdate>
      <div className="min-h-screen bg-background">
        {children}
      </div>
    </SiteSettingsProvider>
  )
}
