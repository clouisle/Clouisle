'use client'

import { useTranslations } from 'next-intl'
import { ChevronDown, FolderKanban } from 'lucide-react'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'

export function ProjectSelector() {
  const t = useTranslations('platform.colslandProjects')

  return (
    <div className="fixed left-4 top-4 z-40 sm:left-6 sm:top-6">
      <Popover>
        <PopoverTrigger className="flex h-11 max-w-[calc(100vw-2rem)] items-center gap-2 rounded-xl border bg-card px-3 text-sm font-medium text-card-foreground shadow-md transition-colors hover:bg-accent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring">
          <FolderKanban className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
          <span className="truncate">{t('select')}</span>
          <ChevronDown className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
        </PopoverTrigger>
        <PopoverContent align="start" className="w-64 max-w-[calc(100vw-2rem)] p-4">
          <p className="text-sm text-muted-foreground">{t('empty')}</p>
        </PopoverContent>
      </Popover>
    </div>
  )
}
