'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { Clock, Zap, Loader2, User, Trash2 } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from '@/components/ui/sheet'
import { Message as ChatMessageItem, type ChatMessage } from '@/components/chat'
import { convertBackendMessages, type BackendMessage } from '@/lib/utils/message-converter'
import type { AdminConversationWithMessages } from '@/lib/api/admin/conversations'
import { useCanPerform } from '@/components/permission-guard'

interface ConversationDrawerProps {
  conversation: AdminConversationWithMessages | null
  isLoading: boolean
  open: boolean
  onOpenChange: (open: boolean) => void
  onDelete?: (id: string) => void
}

function formatDateTime(dateString: string): string {
  const d = new Date(dateString)
  const year = d.getFullYear()
  const month = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  const hour = String(d.getHours()).padStart(2, '0')
  const minute = String(d.getMinutes()).padStart(2, '0')
  return `${year}/${month}/${day} ${hour}:${minute}`
}

export function ConversationDrawer({
  conversation,
  isLoading,
  open,
  onOpenChange,
  onDelete,
}: ConversationDrawerProps) {
  const t = useTranslations('conversations')
  const { canPerform } = useCanPerform()
  const canDeleteConversation = canPerform('conversation:delete')

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
              <div className="flex items-start justify-between">
                <div className="flex-1 min-w-0">
                  <SheetTitle className="text-lg truncate pr-4">
                    {conversation.title || t('untitled')}
                  </SheetTitle>
                  <SheetDescription className="flex flex-col gap-1 text-sm mt-1">
                    <span className="flex items-center gap-4">
                      <span className="flex items-center gap-1">
                        <Clock className="h-3.5 w-3.5" />
                        {formatDateTime(conversation.created_at)}
                      </span>
                      <span className="flex items-center gap-1">
                        <Zap className="h-3.5 w-3.5" />
                        {totalTokens.toLocaleString()} tokens
                      </span>
                    </span>
                    {conversation.user_name && (
                      <span className="flex items-center gap-1">
                        <User className="h-3.5 w-3.5" />
                        {conversation.user_name}
                      </span>
                    )}
                  </SheetDescription>
                </div>
                {onDelete && canDeleteConversation && (
                  <Button
                    variant="ghost"
                    size="icon"
                    className="text-destructive hover:text-destructive hover:bg-destructive/10 shrink-0"
                    onClick={() => onDelete(conversation.id)}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                )}
              </div>

              {conversation.agent_name && (
                <div className="mt-2">
                  <Badge variant="secondary" className="text-xs">
                    {conversation.agent_icon && (
                      <img src={conversation.agent_icon} alt="" className="mr-1 h-4 w-4 rounded object-cover" />
                    )}
                    {conversation.agent_name}
                  </Badge>
                </div>
              )}

              {conversation.variables && Object.keys(conversation.variables).length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {Object.entries(conversation.variables).map(([key, value]) => (
                    <Badge key={key} variant="outline" className="text-xs">
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
