'use client'

import { useTranslations } from 'next-intl'
import { FolderKanban } from 'lucide-react'

export function ProjectSelector() {
  const t = useTranslations('platform.colslandProjects')

  return (
    <section aria-labelledby="colsland-projects-title" className="w-full rounded-2xl border bg-card p-4 text-card-foreground shadow-lg shadow-black/5">
      <div className="flex items-center gap-2 text-sm font-medium">
        <FolderKanban className="size-4 text-muted-foreground" aria-hidden="true" />
        <h2 id="colsland-projects-title">{t('title')}</h2>
      </div>
      <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{t('empty')}</p>
    </section>
  )
}
