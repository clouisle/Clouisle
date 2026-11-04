'use client'

import { useTranslations } from 'next-intl'
import { ChevronDown, FolderKanban } from 'lucide-react'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'

export function ProjectSelector() {
  const t = useTranslations('platform.colslandProjects')

  return (
    <div className="fixed left-4 top-4 z-40 sm:left-6 sm:top-6">
      <Popover>
        <PopoverTrigger className="flex h-9 max-w-[calc(100vw-2rem)] items-center gap-1.5 rounded-lg border bg-card px-2 text-sm font-medium text-card-foreground shadow-sm transition-colors hover:bg-accent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring">
          <span className="flex size-6 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary"><FolderKanban className="size-3.5" aria-hidden="true" /></span>
          <span className="truncate">{t('select')}</span>
          <ChevronDown className="size-3.5 shrink-0 text-muted-foreground" aria-hidden="true" />
        </PopoverTrigger>
        <PopoverContent align="start" className="w-48 max-w-[calc(100vw-2rem)] rounded-lg p-3">
          <p className="text-sm text-muted-foreground">{t('empty')}</p>
        </PopoverContent>
      </Popover>
    </div>
  )
}
