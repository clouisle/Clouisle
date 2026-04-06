'use client'

import { ThemeProvider } from 'next-themes'
import { useSearchParams } from 'next/navigation'
import { Suspense } from 'react'

function EmbedThemeWrapper({ children }: { children: React.ReactNode }) {
  const searchParams = useSearchParams()
  const theme = searchParams.get('theme') || 'auto'
  const forcedTheme = theme === 'light' || theme === 'dark' ? theme : undefined

  return (
    <ThemeProvider
      attribute="class"
      defaultTheme={forcedTheme || 'system'}
      forcedTheme={forcedTheme}
      enableSystem={!forcedTheme}
      disableTransitionOnChange
    >
      {children}
    </ThemeProvider>
  )
}

export default function EmbedLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <Suspense fallback={null}>
      <EmbedThemeWrapper>
        <div className="fixed inset-0 bg-background">
          {children}
        </div>
      </EmbedThemeWrapper>
    </Suspense>
  )
}
