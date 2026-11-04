'use client'

import { useTranslations } from 'next-intl'
import { FolderOpen } from 'lucide-react'
import { FloatingCard } from './floating-card'

export function ProjectAssets() {
  const t = useTranslations('platform.colslandAssets')

  return (
    <FloatingCard title={t('title')} icon={<FolderOpen className="size-4 text-muted-foreground" aria-hidden="true" />}>
      {t('selectProject')}
    </FloatingCard>
  )
}
