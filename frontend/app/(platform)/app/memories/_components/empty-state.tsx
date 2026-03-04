'use client'

import { Brain } from 'lucide-react'
import { useRouter } from 'next/navigation'
import { useTranslations } from 'next-intl'

import { Button } from '@/components/ui/button'

export function EmptyState() {
  const router = useRouter()
  const t = useTranslations('memories')

  return (
    <div className="flex h-full items-center justify-center">
      <div className="text-center space-y-4 max-w-md">
        <Brain className="h-16 w-16 mx-auto text-muted-foreground" />
        <h3 className="text-lg font-semibold">{t('noMemories')}</h3>
        <p className="text-sm text-muted-foreground">
          {t('noMemoriesDescription')}
        </p>
        <Button onClick={() => router.push('/app')}>
          {t('startConversation')}
        </Button>
      </div>
    </div>
  )
}
