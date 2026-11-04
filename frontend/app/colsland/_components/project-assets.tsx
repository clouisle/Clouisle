'use client'

import { useTranslations } from 'next-intl'
import { FolderOpen } from 'lucide-react'

export function ProjectAssets() {
  const t = useTranslations('platform.colslandAssets')

  return (
    <aside aria-labelledby="project-assets-title" className="w-full rounded-2xl border bg-card p-4 text-card-foreground shadow-lg shadow-black/5">
      <div className="flex items-center gap-2 text-sm font-medium">
        <FolderOpen className="size-4 text-muted-foreground" aria-hidden="true" />
        <h2 id="project-assets-title">{t('title')}</h2>
      </div>
      <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{t('selectProject')}</p>
    </aside>
  )
}
