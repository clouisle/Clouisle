'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { Header } from '@/components/layout/header'
import { cn } from '@/lib/utils'

export default function SettingsLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const t = useTranslations('settings')
  const pathname = usePathname()

  const settingsNav = [
    { title: t('profile'), href: '/settings/profile', description: t('profileDescription') },
    { title: t('account'), href: '/settings/account', description: t('accountDescription') },
    { title: t('apiKeys'), href: '/settings/api-keys', description: t('apiKeysDescription') },
  ]

  return (
    <div className="flex h-full flex-col">
      <Header />
      <div className="flex flex-1 flex-col gap-4 overflow-auto p-4">
        <h1 className="text-2xl font-bold">{t('title')}</h1>
        <p className="text-muted-foreground">{t('profileDescription')}</p>
        
        <div className="flex flex-col md:flex-row gap-8 mt-4">
          {/* Settings Navigation */}
          <nav className="flex md:flex-col gap-2 md:w-48 overflow-x-auto">
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

          {/* Settings Content */}
          <div className="flex-1 min-w-0">
            {children}
          </div>
        </div>
      </div>
    </div>
  )
}
