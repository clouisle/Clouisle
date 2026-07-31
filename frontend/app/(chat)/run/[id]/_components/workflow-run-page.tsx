'use client'

import * as React from 'react'
import { useRouter } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { AlertCircle, GitBranch, Loader2 } from 'lucide-react'
import { ApiError, workflowsApi, type Workflow } from '@/lib/api'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'

interface WorkflowRunPageProps {
  id: string
}

export function WorkflowRunPage({ id }: WorkflowRunPageProps) {
  const router = useRouter()
  const t = useTranslations('run')
  const [workflow, setWorkflow] = React.useState<Workflow | null>(null)
  const [isLoading, setIsLoading] = React.useState(true)
  const [error, setError] = React.useState<Error | null>(null)

  React.useEffect(() => {
    const fetchWorkflow = async () => {
      try {
        setIsLoading(true)
        setError(null)
        setWorkflow(await workflowsApi.getWorkflow(id))
      } catch (err) {
        const isNotFound =
          err instanceof ApiError &&
          (err.code === 404 || (err.code >= 4000 && err.code < 5000))
        setError(new Error(isNotFound ? t('notFound') : t('loadError')))
      } finally {
        setIsLoading(false)
      }
    }

    void fetchWorkflow()
  }, [id, t])

  if (isLoading) {
    return (
      <div className="flex h-screen items-center justify-center bg-background">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (error || !workflow) {
    return (
      <div className="flex h-screen flex-col items-center justify-center bg-background p-4">
        <Alert variant="destructive" className="max-w-md">
          <AlertCircle className="h-4 w-4" />
          <AlertTitle>{t('error')}</AlertTitle>
          <AlertDescription>{error?.message ?? t('notFound')}</AlertDescription>
        </Alert>
        <Button variant="ghost" className="mt-4" onClick={() => router.push('/')}>
          {t('backToHome')}
        </Button>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b">
        <div className="mx-auto flex min-h-14 max-w-6xl items-center gap-3 px-4 py-3 sm:px-6">
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-muted text-lg">
            {workflow.icon || <GitBranch className="h-4 w-4 text-muted-foreground" />}
          </span>
          <div className="min-w-0">
            <h1 className="truncate text-sm font-medium">{workflow.name}</h1>
            {workflow.description && (
              <p className="line-clamp-1 text-xs text-muted-foreground">
                {workflow.description}
              </p>
            )}
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-4 py-10 sm:px-6">
        <section aria-labelledby="workflow-run-heading" className="max-w-2xl">
          <h2 id="workflow-run-heading" className="text-2xl font-semibold tracking-tight">
            {t('configureWorkflow')}
          </h2>
          <p className="mt-2 max-w-prose text-sm text-muted-foreground">
            {t('fillParameters')}
          </p>
        </section>
      </main>
    </div>
  )
}
