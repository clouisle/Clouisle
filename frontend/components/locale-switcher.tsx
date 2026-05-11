'use client'

import * as React from 'react'
import { useLocale, useTranslations } from 'next-intl'
import { Globe } from 'lucide-react'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { locales, localeNames, type Locale } from '@/i18n/config'
import { useLocaleChange } from '@/hooks/use-locale-change'

interface LocaleSwitcherProps {
  showLabel?: boolean
}

export function LocaleSwitcher({ showLabel = false }: LocaleSwitcherProps) {
  const locale = useLocale()
  const t = useTranslations('common')
  const { changeLocale } = useLocaleChange()

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
            <span className="sr-only">{t('changeLanguage')}</span>
          </button>
        )}
      />
      <DropdownMenuContent align="end">
        {locales.map((l) => (
          <DropdownMenuItem
            key={l}
            onClick={() => changeLocale(l)}
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
