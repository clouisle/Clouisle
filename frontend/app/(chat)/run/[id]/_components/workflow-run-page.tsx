'use client'

import * as React from 'react'
import { useRouter } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { AlertCircle, GitBranch, History, Loader2, Menu, Play, Plus, RotateCcw, Square } from 'lucide-react'
import { ApiError, workflowsApi, type NodeExecution, type Workflow, type WorkflowRun, type WorkflowRunListItem } from '@/lib/api'
import { ExecutionTimeline, VariableForm, useVariableForm } from '@/components/chat'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { useWorkflowRun } from '@/hooks/use-workflow-run'
import { extractVariables } from '@/lib/utils/extract-variables'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from '@/components/ui/sheet'
import { cn } from '@/lib/utils'

type WorkflowWorkspaceView = 'form' | 'live' | 'history'

interface WorkflowRunPageProps {
  id: string
}

export function WorkflowRunPage({ id }: WorkflowRunPageProps) {
  const router = useRouter()
  const t = useTranslations('run')
  const [workflow, setWorkflow] = React.useState<Workflow | null>(null)
  const [isLoading, setIsLoading] = React.useState(true)
  const [error, setError] = React.useState<Error | null>(null)
  const [history, setHistory] = React.useState<WorkflowRunListItem[]>([])
  const [historyLoading, setHistoryLoading] = React.useState(true)
  const [isUploading, setIsUploading] = React.useState(false)
  const [workspaceView, setWorkspaceView] = React.useState<WorkflowWorkspaceView>('form')
  const [historyOpen, setHistoryOpen] = React.useState(false)
  const [historyDetailLoading, setHistoryDetailLoading] = React.useState(false)
  const [historyDetailError, setHistoryDetailError] = React.useState<string | null>(null)
  const [selectedRun, setSelectedRun] = React.useState<WorkflowRun | null>(null)
  const [selectedNodes, setSelectedNodes] = React.useState<NodeExecution[]>([])

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

  const loadHistory = React.useCallback(async () => {
    try {
      setHistoryLoading(true)
      const data = await workflowsApi.getMyWorkflowRuns(id, { pageSize: 10 })
      setHistory(data.items)
    } catch {
      setHistory([])
    } finally {
      setHistoryLoading(false)
    }
  }, [id])

  React.useEffect(() => {
    void loadHistory()
  }, [loadHistory])

  const variables = React.useMemo(() => extractVariables(workflow, 'workflow'), [workflow])
  const variableForm = useVariableForm(variables)
  const run = useWorkflowRun({ workflowId: id, onComplete: loadHistory })
  const isRunning = run.status === 'pending' || run.status === 'running'
  const presentationMode = workflow?.run_page_config?.presentation_mode ?? 'simple'

  React.useEffect(() => {
    if (isRunning) {
      setWorkspaceView('live')
    }
  }, [isRunning])

  const handleRun = async () => {
    if (isUploading || !variableForm.validate()) return
    setWorkspaceView('live')
    await run.start(variableForm.values)
  }

  const handleNewRun = React.useCallback(() => {
    run.reset()
    variableForm.reset()
    setSelectedRun(null)
    setSelectedNodes([])
    setHistoryDetailError(null)
    setWorkspaceView('form')
  }, [run, variableForm])

  const handleRunAgain = React.useCallback(() => {
    run.reset()
    setSelectedRun(null)
    setSelectedNodes([])
    setHistoryDetailError(null)
    setWorkspaceView('form')
  }, [run])

  const handleRerunFromHistory = React.useCallback(() => {
    if (selectedRun?.inputs) {
      variableForm.setValues(selectedRun.inputs)
    }
    run.reset()
    setSelectedRun(null)
    setSelectedNodes([])
    setHistoryDetailError(null)
    setWorkspaceView('form')
  }, [run, selectedRun, variableForm])

  const handleSelectHistory = React.useCallback(async (runId: string) => {
    if (isRunning) return
    setWorkspaceView('history')
    setHistoryDetailLoading(true)
    setHistoryDetailError(null)
    try {
      const [detail, nodes] = await Promise.all([
        workflowsApi.getMyWorkflowRun(id, runId),
        presentationMode === 'result_first'
          ? workflowsApi.getMyRunNodeExecutions(id, runId)
          : Promise.resolve([]),
      ])
      setSelectedRun(detail)
      setSelectedNodes(nodes)
    } catch {
      setHistoryDetailError(t('historyDetailError'))
    } finally {
      setHistoryDetailLoading(false)
    }
  }, [id, isRunning, presentationMode, t])

  const historyResult = selectedRun?.outputs
    ? JSON.stringify(selectedRun.outputs, null, 2)
    : ''
  const selectedHistoryId = workspaceView === 'history' ? selectedRun?.id : null

  const historyPanel = (
    <div className="flex h-full min-h-0 flex-col">
      <div className="border-b p-4">
        <div className="flex items-center gap-2">
          <History className="h-4 w-4 text-muted-foreground" />
          <h2 id="workflow-history-heading" className="font-medium">{t('history')}</h2>
        </div>
        <Button className="mt-4 w-full" variant="outline" onClick={handleNewRun} disabled={isRunning}>
          <Plus className="mr-2 h-4 w-4" />
          {t('newRun')}
        </Button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-3">
        {historyLoading ? (
          <Loader2 className="mx-auto mt-6 h-5 w-5 animate-spin text-muted-foreground" />
        ) : history.length === 0 ? (
          <p className="px-2 py-6 text-sm text-muted-foreground">{t('noHistory')}</p>
        ) : (
          <ol className="space-y-1">
            {history.map((item) => (
              <li key={item.id}>
                <button
                  type="button"
                  onClick={() => {
                    setHistoryOpen(false)
                    void handleSelectHistory(item.id)
                  }}
                  disabled={isRunning}
                  aria-current={selectedHistoryId === item.id ? 'true' : undefined}
                  className={cn(
                    'min-h-11 w-full rounded-md px-3 py-2.5 text-left transition-colors hover:bg-muted/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50',
                    selectedHistoryId === item.id && 'bg-muted'
                  )}
                >
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-sm font-medium">{t(`status.${item.status}`)}</span>
                    <time className="shrink-0 text-xs text-muted-foreground">
                      {new Date(item.created_at).toLocaleString()}
                    </time>
                  </div>
                  <code className="mt-1 block truncate text-xs text-muted-foreground" title={item.id}>
                    {item.id}
                  </code>
                </button>
              </li>
            ))}
          </ol>
        )}
      </div>
    </div>
  )

  const result = React.useMemo(() => {
    const answer = run.messages
      .flatMap((message) => message.role === 'assistant' ? message.parts : [])
      .filter((part) => part.type === 'text')
      .map((part) => part.text)
      .join('')
    if (answer) return answer
    if (run.outputs) return JSON.stringify(run.outputs, null, 2)
    const completed = Array.from(run.executionState.nodes.values()).reverse().find((node) => node.output)
    return completed?.output ? JSON.stringify(completed.output, null, 2) : ''
  }, [run.messages, run.outputs, run.executionState])
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
    <div className="flex h-dvh overflow-hidden bg-background">
      <aside
        aria-labelledby="workflow-history-heading"
        className="hidden h-full w-80 shrink-0 border-r bg-muted/15 lg:block"
      >
        {historyPanel}
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex min-h-14 shrink-0 items-center gap-3 border-b px-4 py-3 sm:px-6">
          <Sheet open={historyOpen} onOpenChange={setHistoryOpen}>
            <SheetTrigger className="lg:hidden">
              <span className="flex h-9 w-9 items-center justify-center rounded-md hover:bg-muted">
                <Menu className="h-4 w-4" />
                <span className="sr-only">{t('openHistory')}</span>
              </span>
            </SheetTrigger>
            <SheetContent side="left" className="gap-0 p-0">
              <SheetHeader className="sr-only">
                <SheetTitle>{t('history')}</SheetTitle>
              </SheetHeader>
              {historyPanel}
            </SheetContent>
          </Sheet>
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
        </header>

        <main className="min-h-0 flex-1 overflow-y-auto">
          <div className="mx-auto w-full max-w-4xl px-4 py-8 sm:px-8 lg:py-12">
            {workspaceView === 'form' && (
              <section aria-labelledby="workflow-inputs-heading">
                <div className="mb-8">
                  <p className="text-xs font-medium uppercase tracking-widest text-muted-foreground">
                    {t('inputs')}
                  </p>
                  <h2 id="workflow-inputs-heading" className="mt-2 text-2xl font-semibold tracking-tight">
                    {t('configureWorkflow')}
                  </h2>
                  <p className="mt-2 max-w-prose text-sm text-muted-foreground">
                    {variables.length ? t('fillParameters') : t('noInputs')}
                  </p>
                </div>
                <VariableForm
                  variables={variables}
                  values={variableForm.values}
                  onChange={variableForm.setValues}
                  fieldErrors={variableForm.fieldErrors}
                  compact={false}
                  disabled={isRunning}
                  onUploadingChange={setIsUploading}
                />
                <Button className="mt-8" onClick={() => void handleRun()} disabled={isUploading}>
                  <Play className="mr-2 h-4 w-4" />
                  {t('startRun')}
                </Button>
              </section>
            )}

            {workspaceView === 'live' && (
              <section aria-labelledby="workflow-result-heading" aria-live="polite">
                <div className="flex flex-wrap items-start justify-between gap-4 border-b pb-6">
                  <div>
                    <p className="text-xs font-medium uppercase tracking-widest text-muted-foreground">
                      {t('result')}
                    </p>
                    <h2 id="workflow-result-heading" className="mt-2 text-2xl font-semibold tracking-tight">
                      {t(`status.${run.status}`)}
                    </h2>
                    {run.runId && (
                      <code className="mt-2 block max-w-full truncate text-xs text-muted-foreground" title={run.runId}>
                        {run.runId}
                      </code>
                    )}
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {isRunning ? (
                      <Button variant="outline" onClick={() => void run.stop()} disabled={run.isCancelling}>
                        <Square className="mr-2 h-4 w-4" />
                        {run.isCancelling ? t('cancelling') : t('cancel')}
                      </Button>
                    ) : (
                      <>
                        <Button variant="outline" onClick={handleRunAgain}>
                          <RotateCcw className="mr-2 h-4 w-4" />
                          {t('runAgain')}
                        </Button>
                        <Button variant="ghost" onClick={handleNewRun}>
                          <Plus className="mr-2 h-4 w-4" />
                          {t('newRun')}
                        </Button>
                      </>
                    )}
                  </div>
                </div>

                {run.error ? (
                  <Alert variant="destructive" className="mt-6">
                    <AlertCircle className="h-4 w-4" />
                    <AlertTitle>{t('runFailed')}</AlertTitle>
                    <AlertDescription>{run.error}</AlertDescription>
                  </Alert>
                ) : result ? (
                  <pre className="mt-6 max-h-[calc(100dvh-16rem)] overflow-auto whitespace-pre-wrap break-words rounded-lg bg-muted/50 p-5 text-sm leading-6">
                    {result}
                  </pre>
                ) : (
                  <div className="mt-12 flex flex-col items-center justify-center py-16 text-center">
                    {isRunning && <Loader2 className="mb-4 h-6 w-6 animate-spin text-muted-foreground" />}
                    <p className="text-sm text-muted-foreground">
                      {isRunning ? t('running') : t('noResult')}
                    </p>
                  </div>
                )}

                {presentationMode === 'result_first' && run.executionState.nodes.size > 0 && (
                  <Collapsible className="mt-8 border-t pt-5">
                    <CollapsibleTrigger className="min-h-11 text-sm font-medium underline-offset-4 hover:underline">
                      {t('showTrace')}
                    </CollapsibleTrigger>
                    <CollapsibleContent className="pt-4">
                      <ExecutionTimeline executionState={run.executionState} />
                    </CollapsibleContent>
                  </Collapsible>
                )}
              </section>
            )}

            {workspaceView === 'history' && (
              <section aria-labelledby="workflow-history-result-heading">
                {historyDetailLoading ? (
                  <div className="flex min-h-64 items-center justify-center">
                    <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                  </div>
                ) : historyDetailError ? (
                  <Alert variant="destructive">
                    <AlertCircle className="h-4 w-4" />
                    <AlertTitle>{t('error')}</AlertTitle>
                    <AlertDescription>{historyDetailError}</AlertDescription>
                  </Alert>
                ) : selectedRun ? (
                  <>
                    <div className="flex flex-wrap items-start justify-between gap-4 border-b pb-6">
                      <div>
                        <p className="text-xs font-medium uppercase tracking-widest text-muted-foreground">
                          {t('historyResult')}
                        </p>
                        <h2 id="workflow-history-result-heading" className="mt-2 text-2xl font-semibold tracking-tight">
                          {t(`status.${selectedRun.status}`)}
                        </h2>
                        <time className="mt-2 block text-xs text-muted-foreground">
                          {new Date(selectedRun.created_at).toLocaleString()}
                        </time>
                        <code className="mt-1 block max-w-full truncate text-xs text-muted-foreground" title={selectedRun.id}>
                          {selectedRun.id}
                        </code>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        <Button variant="outline" onClick={handleRerunFromHistory}>
                          <RotateCcw className="mr-2 h-4 w-4" />
                          {t('runAgain')}
                        </Button>
                        <Button variant="ghost" onClick={handleNewRun}>
                          <Plus className="mr-2 h-4 w-4" />
                          {t('newRun')}
                        </Button>
                      </div>
                    </div>
                    {selectedRun.error_message && (
                      <Alert variant="destructive" className="mt-6">
                        <AlertCircle className="h-4 w-4" />
                        <AlertTitle>{t('runFailed')}</AlertTitle>
                        <AlertDescription>{selectedRun.error_message}</AlertDescription>
                      </Alert>
                    )}
                    {historyResult ? (
                      <pre className="mt-6 max-h-[calc(100dvh-18rem)] overflow-auto whitespace-pre-wrap break-words rounded-lg bg-muted/50 p-5 text-sm leading-6">
                        {historyResult}
                      </pre>
                    ) : !selectedRun.error_message ? (
                      <p className="mt-6 text-sm text-muted-foreground">{t('noResult')}</p>
                    ) : null}
                    {selectedNodes.length > 0 && (
                      <details className="mt-8 border-t pt-5">
                        <summary className="min-h-11 cursor-pointer text-sm font-medium">
                          {t('showTrace')}
                        </summary>
                        <ol className="mt-3 divide-y">
                          {selectedNodes.map((node) => (
                            <li key={node.id} className="py-3 text-sm">
                              <span className="font-medium">{node.node_name}</span>
                              <span className="ml-2 text-muted-foreground">{node.status}</span>
                            </li>
                          ))}
                        </ol>
                      </details>
                    )}
                  </>
                ) : null}
              </section>
            )}
          </div>
        </main>
      </div>
    </div>
  )
}
