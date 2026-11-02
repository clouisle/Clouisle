'use client'

import { ThemeProvider } from './theme-provider'
import { SettingsProvider } from '@/hooks/use-settings'
import { SiteSettingsProvider } from '@/contexts/site-settings-context'
import { DynamicFavicon } from '@/components/dynamic-favicon'
import { XieyuTransitionProvider } from '@/components/layout/xieyu-transition'

interface ProvidersProps {
  children: React.ReactNode
}

export function Providers({ children }: ProvidersProps) {
  return (
    <ThemeProvider>
      <SettingsProvider>
        <SiteSettingsProvider>
          <DynamicFavicon />
          <XieyuTransitionProvider>{children}</XieyuTransitionProvider>
        </SiteSettingsProvider>
      </SettingsProvider>
    </ThemeProvider>
  )
}
