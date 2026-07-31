'use client'

import * as React from 'react'
import { useSearchParams } from 'next/navigation'
import { Loader2 } from 'lucide-react'
import { AgentRunPage } from './_components/agent-run-page'
import { WorkflowRunPage } from './_components/workflow-run-page'

interface UnifiedRunPageProps {
  params: Promise<{ id: string }>
}

export default function UnifiedRunPage({ params }: UnifiedRunPageProps) {
  const searchParams = useSearchParams()
  const [resolvedParams, setResolvedParams] = React.useState<{ id: string } | null>(null)

  React.useEffect(() => {
    void params.then(setResolvedParams)
  }, [params])

  if (!resolvedParams) {
    return (
      <div className="h-screen flex items-center justify-center bg-background">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  const type = searchParams.get('type') === 'workflow' ? 'workflow' : 'agent'

  return type === 'workflow' ? (
    <WorkflowRunPage id={resolvedParams.id} />
  ) : (
    <AgentRunPage id={resolvedParams.id} />
  )
}
