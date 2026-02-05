'use client'

import * as React from 'react'
import { useTranslations, useLocale } from 'next-intl'
import { Clock, Zap, Loader2 } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from '@/components/ui/sheet'
import { Message as ChatMessageItem, type ChatMessage } from '@/components/chat'
import { convertBackendMessages, type BackendMessage } from '@/lib/utils/message-converter'
import type { ConversationWithMessages } from '@/lib/api'

interface ConversationDrawerProps {
  conversation: ConversationWithMessages | null
  isLoading: boolean
  open: boolean
  onOpenChange: (open: boolean) => void
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

export function ConversationDrawer({
  conversation,
  isLoading,
  open,
  onOpenChange,
}: ConversationDrawerProps) {
  const t = useTranslations('agents.logs')
  const locale = useLocale()

  const totalTokens =
    conversation?.messages.reduce((sum, msg) => {
      if (msg.token_usage) {
        return sum + (msg.token_usage.prompt || 0) + (msg.token_usage.completion || 0)
      }
      return sum
    }, 0) ?? 0

  const chatMessages = React.useMemo<ChatMessage[]>(() => {
    if (!conversation) return []
    return convertBackendMessages(conversation.messages as BackendMessage[])
  }, [conversation])

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-[60%]! max-w-none! p-0 flex flex-col" showCloseButton={false}>
        {isLoading ? (
          <div className="flex-1 flex items-center justify-center">
            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          </div>
        ) : conversation ? (
          <>
            <SheetHeader className="px-6 py-4 border-b shrink-0">
              <SheetTitle className="text-lg">
                {conversation.title || t('untitledConversation')}
              </SheetTitle>
              <SheetDescription className="flex items-center gap-4 text-sm">
                <span className="flex items-center gap-1">
                  <Clock className="h-3.5 w-3.5" />
                  {formatDateTime(conversation.created_at, locale)}
                </span>
                <span className="flex items-center gap-1">
                  <Zap className="h-3.5 w-3.5" />
                  {totalTokens.toLocaleString()} tokens
                </span>
              </SheetDescription>

              {conversation.variables && Object.keys(conversation.variables).length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {Object.entries(conversation.variables).map(([key, value]) => (
                    <Badge key={key} variant="secondary" className="text-xs">
                      {key}: {String(value)}
                    </Badge>
                  ))}
                </div>
              )}
            </SheetHeader>

            <div className="flex-1 overflow-y-auto">
              <div className="p-6 space-y-6">
                {chatMessages.map((message) => (
                  <ChatMessageItem key={message.id} message={message} />
                ))}
              </div>
            </div>
          </>
        ) : null}
      </SheetContent>
    </Sheet>
  )
}
