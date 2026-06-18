'use client'

import * as React from 'react'
import { Loader2 } from 'lucide-react'
import {
  Sheet,
  SheetContent,
} from '@/components/ui/sheet'
import { Message as ChatMessageItem, type ChatMessage } from '@/components/chat'
import { ConversationDrawerHeader } from '@/components/chat/conversation-drawer-header'
import { convertBackendMessages, type BackendMessage } from '@/lib/utils/message-converter'
import type { ConversationWithMessages } from '@/lib/api'

interface ConversationDrawerProps {
  conversation: ConversationWithMessages | null
  isLoading: boolean
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function ConversationDrawer({
  conversation,
  isLoading,
  open,
  onOpenChange,
}: ConversationDrawerProps) {
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
            <ConversationDrawerHeader
              title={conversation.title}
              createdAt={conversation.created_at}
              totalTokens={totalTokens}
              variables={conversation.variables}
              agentName={conversation.agent_name}
              agentIcon={conversation.agent_icon}
            />

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
