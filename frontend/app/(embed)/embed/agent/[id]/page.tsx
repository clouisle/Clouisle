'use client'

import * as React from 'react'
import { useSearchParams, useParams } from 'next/navigation'
import { Loader2 } from 'lucide-react'
import { createEmbedChatAdapter } from '@/lib/chat/embed-chat-adapter'
import PublicChatPage from '@/app/(chat)/chat/[id]/page'
import { Suspense } from 'react'

function EmbedAgentContent() {
  const params = useParams()
  const searchParams = useSearchParams()
  const agentId = params.id as string
  const token = searchParams.get('token') || ''
  const mode = (searchParams.get('mode') || 'fullscreen') as 'fullscreen' | 'bubble'

  const [apiKey, setApiKey] = React.useState(token)

  React.useEffect(() => {
    const handler = (event: MessageEvent) => {
      if (event.data?.type === 'clouisle:token' && event.data?.token) {
        setApiKey(event.data.token)
      }
    }
    window.addEventListener('message', handler)
    // Notify parent that the iframe is ready to receive a token
    window.parent.postMessage({ type: 'clouisle:ready' }, '*')
    return () => window.removeEventListener('message', handler)
  }, [])

  const adapter = React.useMemo(
    () => (apiKey ? createEmbedChatAdapter(agentId, apiKey) : null),
    [agentId, apiKey],
  )

  const handleConversationChange = React.useCallback((conversationId: string) => {
    window.parent.postMessage({ type: 'clouisle:conversation', conversationId }, '*')
  }, [])

  const handleClose = React.useCallback(() => {
    window.parent.postMessage({ type: 'clouisle:close' }, '*')
  }, [])

  if (!adapter) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    )
  }

  return (
    <PublicChatPage
      agentId={agentId}
      adapter={adapter}
      embedMode
      mode={mode}
      onConversationChange={handleConversationChange}
      onClose={handleClose}
    />
  )
}

export default function EmbedAgentPage() {
  return (
    <Suspense
      fallback={
        <div className="flex h-full items-center justify-center">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      }
    >
      <EmbedAgentContent />
    </Suspense>
  )
}
