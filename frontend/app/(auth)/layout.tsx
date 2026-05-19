import type { AuthPageLayout, PublicSiteSettings } from '@/lib/api/site-settings'
import { getServerApiBaseUrl } from '@/lib/api/server-url'
import { AuthLayoutShell } from './_components/auth-layout-shell'
import { getTranslations } from 'next-intl/server'

function normalizeAuthPageLayout(value: string | undefined): AuthPageLayout {
  return value === 'split' ? 'split' : 'centered'
}

async function getPublicSettings(): Promise<Pick<PublicSiteSettings, 'site_name' | 'auth_page_layout'>> {
  try {
    const response = await fetch(`${getServerApiBaseUrl()}/site-settings/public`, {
      next: { revalidate: 300 }, // Cache for 5 minutes
      headers: {
        'Cache-Control': 'no-cache',
      },
    })

    if (!response.ok) {
      console.warn(`Failed to fetch public settings: ${response.status}`)
      return {
        site_name: 'Clouisle',
        auth_page_layout: 'centered',
      }
    }

    const body = await response.json() as { data?: Partial<PublicSiteSettings> }

    return {
    site_name: body.data?.site_name || 'Clouisle',
      auth_page_layout: normalizeAuthPageLayout(body.data?.auth_page_layout),
    }
  } catch (error) {
    console.error('Error fetching public settings:', error)
    return {
      site_name: 'Clouisle',
      auth_page_layout: 'centered',
    }
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
    >
      {children}
    </AuthLayoutShell>
  )
}
