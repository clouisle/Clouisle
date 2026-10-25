'use client'

import { useTranslations } from 'next-intl'

import { resolveProviderLabel } from '@/lib/model-provider'

export function useProviderLabel() {
  const t = useTranslations('models')
  return (provider: string, displayName?: string | null) => resolveProviderLabel(t, provider, displayName)
}
