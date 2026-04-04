'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { RoutePermissionGuard } from '@/components/auth/permission-guard'
import { Header } from '@/components/layout/header'
import { usePermissions } from '@/hooks/use-permissions'
import { SITE_SETTINGS_NAV_ITEMS, ROUTE_PERMISSION_MAP } from '@/lib/route-permissions'
import { cn } from '@/lib/utils'

export default function SiteSettingsLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const t = useTranslations('siteSettings')
  const pathname = usePathname()
  const { hasPermission } = usePermissions()

  const settingsNav = SITE_SETTINGS_NAV_ITEMS
    .map((item) => ({
      title: t(item.translationKey),
      href: item.path,
      description: t(item.descriptionKey),
      permission: ROUTE_PERMISSION_MAP[item.path],
    }))
    .filter((item) => !item.permission || hasPermission(item.permission))

  return (
    <RoutePermissionGuard>
      <div className="flex h-full flex-col">
        <Header />
        <div className="flex flex-1 flex-col overflow-hidden p-4">
          <div className="mb-4">
            <h1 className="text-2xl font-bold">{t('title')}</h1>
            <p className="text-muted-foreground">{t('description')}</p>
          </div>

          <div className="flex flex-1 flex-col md:flex-row gap-8 min-h-0">
            {/* Settings Navigation */}
            <div className="md:w-48 shrink-0">
              <nav className="flex md:flex-col gap-2 overflow-x-auto md:sticky md:top-4">
                {settingsNav.map((item) => (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={cn(
                      "px-4 py-2 text-sm rounded-md whitespace-nowrap transition-colors",
                      pathname === item.href
                        ? "bg-muted font-medium"
                        : "hover:bg-muted/50 text-muted-foreground"
                    )}
                  >
                    {item.title}
                  </Link>
                ))}
              </nav>
            </div>

            {/* Settings Content */}
            <div className="flex-1 min-h-0 overflow-auto p-1">
              <div className="max-w-2xl">
                {children}
              </div>
            </div>
          </div>
        </div>
      </div>
    </RoutePermissionGuard>
  )
}
