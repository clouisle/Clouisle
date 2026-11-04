'use client'

import { useTranslations } from 'next-intl'
import { FolderKanban } from 'lucide-react'
import { FloatingCard } from './floating-card'

export function ProjectSelector({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const t = useTranslations('platform.colslandProjects')

  return (
    <FloatingCard open={open} onOpenChange={onOpenChange} title={t('title')} icon={<FolderKanban className="size-4 text-muted-foreground" aria-hidden="true" />}>
      {t('empty')}
    </FloatingCard>
  )
}
