'use client'

import { ThemeProvider } from './theme-provider'
import { SettingsProvider } from '@/hooks/use-settings'
import { SiteSettingsProvider } from '@/contexts/site-settings-context'
import { DynamicFavicon } from '@/components/dynamic-favicon'
import { ColslandTransitionProvider } from '@/components/layout/colsland-transition'

interface ProvidersProps {
  children: React.ReactNode
}

export function Providers({ children }: ProvidersProps) {
  return (
    <ThemeProvider>
      <SettingsProvider>
        <SiteSettingsProvider>
          <DynamicFavicon />
          <ColslandTransitionProvider>{children}</ColslandTransitionProvider>
        </SiteSettingsProvider>
      </SettingsProvider>
    </ThemeProvider>
  )
}
