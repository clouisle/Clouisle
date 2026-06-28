import type { AuthPageLayout, PublicSiteSettings } from '@/lib/api/site-settings'
import { getServerApiBaseUrl } from '@/lib/api/server-url'
import { AuthLayoutShell } from './_components/auth-layout-shell'
import { getTranslations } from 'next-intl/server'

function normalizeAuthPageLayout(value: string | undefined): AuthPageLayout {
  return value === 'split' ? 'split' : 'centered'
}

async function getPublicSettings(): Promise<Pick<PublicSiteSettings,
  | 'site_name'
  | 'site_description'
  | 'site_icon'
  | 'auth_page_layout'
  | 'theme_branding_display'
  | 'icp_record_number'
  | 'icp_record_url'
  | 'terms_enabled'
  | 'terms_url'
  | 'terms_text'
  | 'privacy_enabled'
  | 'privacy_url'
  | 'privacy_text'
>> {
  const fallback = {
    site_name: 'Clouisle',
    site_description: '',
    site_icon: '',
    auth_page_layout: 'centered' as AuthPageLayout,
    theme_branding_display: 'full' as const,
    icp_record_number: '',
    icp_record_url: '',
    terms_enabled: false,
    terms_url: '',
    terms_text: '',
    privacy_enabled: false,
    privacy_url: '',
    privacy_text: '',
  }

  try {
    const response = await fetch(`${getServerApiBaseUrl()}/site-settings/public`, {
      next: { revalidate: 300 }, // Cache for 5 minutes
      headers: {
        'Cache-Control': 'no-cache',
      },
    })

    if (!response.ok) {
      console.warn(`Failed to fetch public settings: ${response.status}`)
      return fallback
    }

    const body = await response.json() as { data?: Partial<PublicSiteSettings> }

    return {
      site_name: body.data?.site_name || 'Clouisle',
      site_description: body.data?.site_description || '',
      site_icon: body.data?.site_icon || '',
      auth_page_layout: normalizeAuthPageLayout(body.data?.auth_page_layout),
      theme_branding_display: body.data?.theme_branding_display || 'full',
      icp_record_number: body.data?.icp_record_number || '',
      icp_record_url: body.data?.icp_record_url || '',
      terms_enabled: body.data?.terms_enabled ?? false,
      terms_url: body.data?.terms_url || '',
      terms_text: body.data?.terms_text || '',
      privacy_enabled: body.data?.privacy_enabled ?? false,
      privacy_url: body.data?.privacy_url || '',
      privacy_text: body.data?.privacy_text || '',
    }
  } catch (error) {
    console.error('Error fetching public settings:', error)
    return fallback
  }
}

export default async function AuthLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const t = await getTranslations('auth')

  const settings = await getPublicSettings()

  return (
    <AuthLayoutShell
      layout={settings.auth_page_layout}
      previewImageAlt={t('previewImageAlt', { siteName: settings.site_name })}
      brandingSettings={settings}
      legalSettings={settings}
    >
      {children}
    </AuthLayoutShell>
  )
}
