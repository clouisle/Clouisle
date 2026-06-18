'use client'

import { useLocale, useTranslations } from 'next-intl'
import { Clock, User, Zap } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'

interface ConversationDrawerHeaderProps {
  title?: string | null
  createdAt: string
  totalTokens: number
  variables?: Record<string, unknown> | null
  agentName?: string | null
  agentIcon?: string | null
  userName?: string | null
  action?: React.ReactNode
}

function formatDateTime(dateString: string, locale: string): string {
  const date = new Date(dateString)
  if (locale === 'zh') {
    return date.toLocaleString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    })
  }
  return date.toLocaleString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function ConversationDrawerHeader({
  title,
  createdAt,
  totalTokens,
  variables,
  agentName,
  agentIcon,
  userName,
  action,
}: ConversationDrawerHeaderProps) {
  const t = useTranslations('conversations')
  const locale = useLocale()
  const variableEntries = variables ? Object.entries(variables) : []

  return (
    <SheetHeader className="px-6 py-4 border-b shrink-0">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <SheetTitle className="text-lg truncate">
            {title || t('untitled')}
          </SheetTitle>
          <SheetDescription className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
            <span className="flex items-center gap-1" suppressHydrationWarning>
              <Clock className="h-3.5 w-3.5" />
              {formatDateTime(createdAt, locale)}
            </span>
            <span className="flex items-center gap-1">
              <Zap className="h-3.5 w-3.5" />
              {t('drawer.tokenCount', { count: totalTokens.toLocaleString() })}
            </span>
            {userName && (
              <span className="flex items-center gap-1">
                <User className="h-3.5 w-3.5" />
                {userName}
              </span>
            )}
          </SheetDescription>
        </div>
        {action}
      </div>

      {agentName && (
        <div className="mt-2">
          <Badge variant="secondary" className="text-xs">
            {agentIcon && (
              <img src={agentIcon} alt="" className="mr-1 h-4 w-4 rounded object-cover" />
            )}
            {agentName}
          </Badge>
        </div>
      )}

      {variableEntries.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {variableEntries.map(([key, value]) => (
            <Badge key={key} variant="secondary" className="text-xs">
              {key}: {String(value)}
            </Badge>
          ))}
        </div>
      )}
    </SheetHeader>
  )
}
