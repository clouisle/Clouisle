import { API_BASE_URL } from '@/lib/constants'
import type { AuthPageLayout, PublicSiteSettings } from '@/lib/api/site-settings'
import { AuthLayoutShell } from './_components/auth-layout-shell'

function normalizeAuthPageLayout(value: string | undefined): AuthPageLayout {
  return value === 'split' ? 'split' : 'centered'
}

async function getPublicSettings(): Promise<Pick<PublicSiteSettings, 'site_name' | 'site_description' | 'auth_page_layout'>> {
  const response = await fetch(`${API_BASE_URL}/site-settings/public`, { cache: 'no-store' })

  if (!response.ok) {
    throw new Error('Failed to load public site settings')
  }

  const body = await response.json() as { data?: Partial<PublicSiteSettings> }

  return {
    site_name: body.data?.site_name || 'Clouisle',
    site_description: body.data?.site_description || '',
    auth_page_layout: normalizeAuthPageLayout(body.data?.auth_page_layout),
  }
}

export default async function AuthLayout({
  children,
}: {
  children: React.ReactNode
}) {
  let settings = {
    site_name: 'Clouisle',
    site_description: '',
    auth_page_layout: 'centered' as AuthPageLayout,
  }

  try {
    settings = await getPublicSettings()
  } catch {
    settings.auth_page_layout = 'centered'
  }

  return (
    <AuthLayoutShell
      layout={settings.auth_page_layout}
      siteName={settings.site_name}
    >
      {children}
    </AuthLayoutShell>
  )
}
