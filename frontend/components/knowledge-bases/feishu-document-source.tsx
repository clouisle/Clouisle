'use client'

import { useTranslations } from 'next-intl'
import type { Document } from '@/lib/api/knowledge-bases'
import { Badge } from '@/components/ui/badge'

export function isFeishuManaged(document: Document | null) {
  return Boolean(document?.metadata?.feishu_source_id || document?.metadata?.feishu_read_only === true)
}

export function FeishuDocumentSource({ document }: { document: Document }) {
  const t = useTranslations('knowledgeBases')
  if (!isFeishuManaged(document)) return null
  return <span title={t('feishuReadOnly')}><Badge variant="secondary">{t('feishuImported')}</Badge></span>
}
