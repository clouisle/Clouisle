'use client'

import * as React from 'react'
import { useSearchParams, useParams } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { createEmbedWorkflowRunAdapter } from '@/lib/workflow/embed-run-adapter'
import { WorkflowRunPage } from '@/app/(chat)/run/[id]/_components/workflow-run-page'
import { Suspense } from 'react'

function EmbedWorkflowContent() {
  const params = useParams()
  const searchParams = useSearchParams()
  const t = useTranslations('embed.page')
  const workflowId = params.id as string
  const token = searchParams.get('token') || ''
  const [apiKey, setApiKey] = React.useState(token)

  // Listen for a token via postMessage (more secure alternative to the URL).
  React.useEffect(() => {
    const handler = (event: MessageEvent) => {
      if (event.data?.type === 'clouisle:token' && event.data?.token) {
        setApiKey(event.data.token)
      }
    }
    window.addEventListener('message', handler)
    window.parent.postMessage({ type: 'clouisle:ready' }, '*')
    return () => window.removeEventListener('message', handler)
  }, [])

  const adapter = React.useMemo(() => createEmbedWorkflowRunAdapter(apiKey), [apiKey])

  if (!apiKey) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 p-4">
        <p className="text-sm text-muted-foreground">{t('invalidToken')}</p>
      </div>
    )
  }

  return <WorkflowRunPage id={workflowId} adapter={adapter} embedMode />
}

export default function EmbedWorkflowPage() {
  return (
    <Suspense>
      <EmbedWorkflowContent />
    </Suspense>
  )
}
