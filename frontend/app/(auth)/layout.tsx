import { API_BASE_URL } from '@/lib/constants'
import type { AuthPageLayout, PublicSiteSettings } from '@/lib/api/site-settings'
import { AuthLayoutShell } from './_components/auth-layout-shell'
import { getTranslations } from 'next-intl/server'

function normalizeAuthPageLayout(value: string | undefined): AuthPageLayout {
  return value === 'split' ? 'split' : 'centered'
}

async function getPublicSettings(): Promise<Pick<PublicSiteSettings, 'site_name' | 'auth_page_layout'>> {
  const response = await fetch(`${API_BASE_URL}/site-settings/public`, {
    next: { revalidate: 300 } // Cache for 5 minutes
  })

  if (!response.ok) {
    throw new Error('Failed to load public site settings')
  }

  const body = await response.json() as { data?: Partial<PublicSiteSettings> }

  return {
    site_name: body.data?.site_name || 'Clouisle',
    auth_page_layout: normalizeAuthPageLayout(body.data?.auth_page_layout),
  }
}

export default async function AuthLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const t = await getTranslations('auth')

  let settings = {
    site_name: 'Clouisle',
    auth_page_layout: 'centered' as AuthPageLayout,
  }

  try {
    settings = await getPublicSettings()
  } catch (error) {
    console.error('Failed to load public settings for auth layout:', error)
    // Keep all defaults on error
    settings = {
      site_name: 'Clouisle',
      auth_page_layout: 'centered',
    }
  }

  return (
    <AuthLayoutShell
      layout={settings.auth_page_layout}
      previewImageAlt={t('previewImageAlt', { siteName: settings.site_name })}
    >
      {children}
    </AuthLayoutShell>
  )
}
