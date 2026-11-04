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
      <div className="mt-4 space-y-4 border-t pt-4">
        <section aria-labelledby="project-outputs-title">
          <h3 id="project-outputs-title" className="text-sm font-medium text-muted-foreground">{t('outputs')}</h3>
          <p className="mt-2 text-sm text-muted-foreground">{t('noOutputs')}</p>
        </section>
        <section aria-labelledby="project-sources-title" className="border-t pt-4">
          <h3 id="project-sources-title" className="text-sm font-medium text-muted-foreground">{t('sources')}</h3>
          <p className="mt-2 text-sm text-muted-foreground">{t('noSources')}</p>
        </section>
      </div>
    </aside>
  )
}
