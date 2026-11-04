'use client'

import { useTranslations } from 'next-intl'
import { FolderKanban } from 'lucide-react'
import { FloatingCard, type FloatingCardProps } from './floating-card'

export function ProjectSelector(props: Omit<FloatingCardProps, 'title' | 'icon' | 'children'>) {
  const t = useTranslations('platform.colslandProjects')

  return (
    <FloatingCard {...props} title={t('title')} icon={<FolderKanban className="size-4 text-muted-foreground" aria-hidden="true" />}>
      {t('empty')}
    </FloatingCard>
  )
}
