'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { siteSettingsApi, type PublicSiteSettings } from '@/lib/api'
import { KNOWLEDGE_BASE_DOCUMENT_DEFAULT_MAX_UPLOAD_SIZE_MB } from '@/lib/constants'

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
  sso_enabled: false,
  sso_allow_password_login: true,
  kb_document_max_upload_size_mb: KNOWLEDGE_BASE_DOCUMENT_DEFAULT_MAX_UPLOAD_SIZE_MB,
  auth_page_layout: 'centered',
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
  const tPlatform = useTranslations('platform')
  const [settings, setSettings] = React.useState<PublicSiteSettings>(defaultSettings)
  const [loading, setLoading] = React.useState(true)

  const loadSettings = React.useCallback(async () => {
    try {
      const data = await siteSettingsApi.getPublic()
      setSettings(data)
      
      // 更新页面标题
      if (data.site_name && !skipTitleUpdate) {
        document.title = `${data.site_name} - ${tPlatform('admin')}`
      }
      
      // 更新 favicon - 有自定义图标用自定义的，否则用默认的 light icon
      if (!skipFaviconUpdate) {
        const iconHref = data.site_icon || '/clouisle-light.svg'
        const link = document.querySelector("link[rel*='icon']") as HTMLLinkElement
        if (link) {
          link.href = iconHref
        } else {
          const newLink = document.createElement('link')
          newLink.rel = 'icon'
          newLink.href = iconHref
          document.head.appendChild(newLink)
        }
      }
    } catch (error) {
      console.error('Failed to load site settings:', error)
    } finally {
      setLoading(false)
    }
  }, [skipTitleUpdate, skipFaviconUpdate, tPlatform])

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
