'use client'

import * as React from 'react'
import { useLocale } from 'next-intl'
import { useRouter } from 'next/navigation'
import { Globe } from 'lucide-react'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { locales, localeNames, type Locale } from '@/i18n/config'
import { usersApi } from '@/lib/api'

interface LocaleSwitcherProps {
  showLabel?: boolean
}

export function LocaleSwitcher({ showLabel = false }: LocaleSwitcherProps) {
  const locale = useLocale()
  const router = useRouter()

  const handleLocaleChange = React.useCallback(async (newLocale: Locale) => {
    // 设置 cookie
    document.cookie = `locale=${newLocale};path=/;max-age=31536000`

    // 如果用户已登录（有 token），同步到后端
    const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null
    if (token) {
      try {
        await usersApi.updateProfile({ locale: newLocale })
      } catch {
        // 静默失败，不影响前端切换
      }
    }

    router.refresh()
  }, [router])

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={(props) => (
          <button
            {...props}
            className="inline-flex items-center justify-center gap-2 rounded-md px-3 py-2 text-sm font-medium hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring cursor-pointer"
          >
            <Globe className="h-4 w-4" />
            {showLabel && <span>{localeNames[locale as Locale]}</span>}
            <span className="sr-only">Switch language</span>
          </button>
        )}
      />
      <DropdownMenuContent align="end">
        {locales.map((l) => (
          <DropdownMenuItem
            key={l}
            onClick={() => handleLocaleChange(l)}
            className={locale === l ? 'bg-accent' : ''}
          >
            <span className="mr-2">{l === 'en' ? '🇺🇸' : '🇨🇳'}</span>
            {localeNames[l]}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
