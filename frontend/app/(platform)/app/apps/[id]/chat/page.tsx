'use client'

import * as React from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import {
  ArrowLeft,
  Bot,
  Settings,
} from 'lucide-react'
import { agentsApi, type Agent } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { ChatInterface } from './_components/chat-interface'

interface AgentChatPageProps {
  params: Promise<{ id: string }>
}

export default function AgentChatPage({ params }: AgentChatPageProps) {
  const router = useRouter()
  
  const [agent, setAgent] = React.useState<Agent | null>(null)
  const [isLoading, setIsLoading] = React.useState(true)
  
  // Unwrap params
  const [resolvedParams, setResolvedParams] = React.useState<{ id: string } | null>(null)
  
  React.useEffect(() => {
    params.then(setResolvedParams)
  }, [params])
  
  const fetchAgent = React.useCallback(async () => {
    if (!resolvedParams) return
    
    try {
      setIsLoading(true)
      const data = await agentsApi.getAgent(resolvedParams.id)
      setAgent(data)
    } catch {
      router.push('/app/apps')
    } finally {
      setIsLoading(false)
    }
  }, [resolvedParams, router])
  
  React.useEffect(() => {
    fetchAgent()
  }, [fetchAgent])
  
  if (isLoading || !agent) {
    return (
      <div className="h-[calc(100vh-theme(spacing.14))] flex flex-col">
        <div className="flex items-center gap-4 p-4 border-b">
          <Skeleton className="h-8 w-8" />
          <Skeleton className="h-6 w-32" />
        </div>
        <div className="flex-1 flex items-center justify-center">
          <Skeleton className="h-12 w-64" />
        </div>
      </div>
    )
  }
  
  return (
    <div className="h-[calc(100vh-theme(spacing.14))] flex flex-col -mx-8 -my-6">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b bg-background/95 backdrop-blur">
        <div className="flex items-center gap-3">
          <Link href="/app/apps">
            <Button variant="ghost" size="icon" className="h-8 w-8">
              <ArrowLeft className="h-4 w-4" />
            </Button>
          </Link>
          <div className="flex items-center gap-2">
            <div className="rounded-lg bg-primary/10 p-1.5">
              {agent.icon ? (
                <span className="text-lg">{agent.icon}</span>
              ) : (
                <Bot className="h-4 w-4 text-primary" />
              )}
            </div>
            <div>
              <h1 className="text-base font-semibold">{agent.name}</h1>
              {agent.model && (
                <p className="text-xs text-muted-foreground">{agent.model.name}</p>
              )}
            </div>
          </div>
        </div>
        
        <Link href={`/app/apps/${agent.id}`}>
          <Button variant="ghost" size="icon" className="h-8 w-8">
            <Settings className="h-4 w-4" />
          </Button>
        </Link>
      </div>
      
      {/* Chat Interface */}
      <ChatInterface agent={agent} />
    </div>
  )
}
