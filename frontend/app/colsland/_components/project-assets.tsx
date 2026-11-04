'use client'

import { useTranslations } from 'next-intl'
import { FolderOpen } from 'lucide-react'
import { FloatingCard } from './floating-card'

export function ProjectAssets({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const t = useTranslations('platform.colslandAssets')

  return (
    <FloatingCard open={open} onOpenChange={onOpenChange} title={t('title')} icon={<FolderOpen className="size-4 text-muted-foreground" aria-hidden="true" />}>
      {t('selectProject')}
    </FloatingCard>
  )
}
