'use client'

import { ThemeProvider } from './theme-provider'
import { SettingsProvider } from '@/hooks/use-settings'
import { SiteSettingsProvider } from '@/contexts/site-settings-context'
import { DynamicFavicon } from '@/components/dynamic-favicon'

interface ProvidersProps {
  children: React.ReactNode
}

export function Providers({ children }: ProvidersProps) {
  return (
    <ThemeProvider>
      <SettingsProvider>
        <SiteSettingsProvider>
          <DynamicFavicon />
          {children}
        </SiteSettingsProvider>
      </SettingsProvider>
    </ThemeProvider>
  )
}
