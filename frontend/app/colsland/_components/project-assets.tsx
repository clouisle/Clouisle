'use client'

import { useTranslations } from 'next-intl'
import { FolderOpen } from 'lucide-react'
import { FloatingCard, type FloatingCardProps } from './floating-card'

export function ProjectAssets(props: Omit<FloatingCardProps, 'title' | 'icon' | 'children'>) {
  const t = useTranslations('platform.colslandAssets')

  return (
    <FloatingCard {...props} title={t('title')} icon={<FolderOpen className="size-4 text-muted-foreground" aria-hidden="true" />}>
      {t('selectProject')}
    </FloatingCard>
  )
}
