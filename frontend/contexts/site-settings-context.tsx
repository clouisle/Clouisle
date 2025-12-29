'use client'

import * as React from 'react'
import { siteSettingsApi, type PublicSiteSettings } from '@/lib/api'

interface SiteSettingsContextType {
  settings: PublicSiteSettings
  loading: boolean
  refresh: () => Promise<void>
}

const defaultSettings: PublicSiteSettings = {
  site_name: 'Clouisle',
  site_description: '',
  site_url: '',
  site_icon: '',
  allow_registration: true,
  require_approval: false,
  email_verification: true,
  enable_captcha: false,
  allow_account_deletion: true,
}

const SiteSettingsContext = React.createContext<SiteSettingsContextType>({
  settings: defaultSettings,
  loading: true,
  refresh: async () => {},
})

interface SiteSettingsProviderProps {
  children: React.ReactNode
  /** Skip updating document title (for pages with dynamic metadata) */
  skipTitleUpdate?: boolean
  /** Skip updating favicon (for pages with dynamic icon) */
  skipFaviconUpdate?: boolean
}

export function SiteSettingsProvider({ 
  children, 
  skipTitleUpdate = false,
  skipFaviconUpdate = false,
}: SiteSettingsProviderProps) {
  const [settings, setSettings] = React.useState<PublicSiteSettings>(defaultSettings)
  const [loading, setLoading] = React.useState(true)

  const loadSettings = React.useCallback(async () => {
    try {
      const data = await siteSettingsApi.getPublic()
      setSettings(data)
      
      // 更新页面标题
      if (data.site_name && !skipTitleUpdate) {
        document.title = `${data.site_name} - Admin Panel`
      }
      
      // 更新 favicon
      if (data.site_icon && !skipFaviconUpdate) {
        const link = document.querySelector("link[rel*='icon']") as HTMLLinkElement
        if (link) {
          link.href = data.site_icon
        } else {
          const newLink = document.createElement('link')
          newLink.rel = 'icon'
          newLink.href = data.site_icon
          document.head.appendChild(newLink)
        }
      }
    } catch (error) {
      console.error('Failed to load site settings:', error)
    } finally {
      setLoading(false)
    }
  }, [skipTitleUpdate, skipFaviconUpdate])

  React.useEffect(() => {
    loadSettings()
  }, [loadSettings])

  return (
    <SiteSettingsContext.Provider value={{ settings, loading, refresh: loadSettings }}>
      {children}
    </SiteSettingsContext.Provider>
  )
}

export function useSiteSettings() {
  const context = React.useContext(SiteSettingsContext)
  if (!context) {
    throw new Error('useSiteSettings must be used within a SiteSettingsProvider')
  }
  return context
}
