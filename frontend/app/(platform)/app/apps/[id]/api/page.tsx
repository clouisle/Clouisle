'use client'

import * as React from 'react'
import { useRouter } from 'next/navigation'
import { agentsApi, type Agent } from '@/lib/api'
import { Skeleton } from '@/components/ui/skeleton'
import { AgentSidebar } from '../_components/agent-sidebar'
import { ApiAccessContent } from './_components/api-access-content'

interface ApiAccessPageProps {
  params: Promise<{ id: string }>
}

export default function ApiAccessPage({ params }: ApiAccessPageProps) {
  const router = useRouter()

  const [agent, setAgent] = React.useState<Agent | null>(null)
  const [isLoading, setIsLoading] = React.useState(true)

  // Unwrap params
  const [resolvedParams, setResolvedParams] = React.useState<{ id: string } | null>(null)

  React.useEffect(() => {
    params.then(setResolvedParams)
  }, [params])

  // Fetch agent data
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
      <div className="h-screen flex">
        <div className="w-52 border-r p-4">
          <Skeleton className="h-10 w-full mb-4" />
          <Skeleton className="h-8 w-full mb-2" />
          <Skeleton className="h-8 w-full mb-2" />
          <Skeleton className="h-8 w-full mb-2" />
        </div>
        <div className="flex-1 p-6">
          <Skeleton className="h-10 w-64 mb-6" />
          <Skeleton className="h-96 rounded-lg" />
        </div>
      </div>
    )
  }

  return (
    <div className="h-full flex overflow-hidden">
      {/* Left Sidebar - Agent Info & Navigation */}
      <AgentSidebar agent={agent} />

      {/* Main Content Area */}
      <ApiAccessContent agent={agent} />
    </div>
  )
}
