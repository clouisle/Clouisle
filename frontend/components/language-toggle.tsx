'use client'

import * as React from 'react'
import { Languages } from 'lucide-react'
import { useLocale, useTranslations } from 'next-intl'

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { locales, localeNames } from '@/i18n/config'
import { useLocaleChange } from '@/hooks/use-locale-change'

export function LanguageToggle() {
  const locale = useLocale()
  const t = useTranslations('common')
  const { changeLocale } = useLocaleChange()

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        className="rounded-md hover:bg-muted text-muted-foreground hover:text-foreground size-8 inline-flex items-center justify-center transition-colors outline-none"
      >
        <Languages className="h-4 w-4" />
        <span className="sr-only">{t('changeLanguage')}</span>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        {locales.map((l) => (
          <DropdownMenuItem
            key={l}
            onClick={() => changeLocale(l)}
            className={locale === l ? 'bg-accent' : ''}
          >
            {localeNames[l]}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
