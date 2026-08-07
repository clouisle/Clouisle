'use client'

import * as React from 'react'
import { useRouter } from 'next/navigation'
import Image from 'next/image'
import { useLocale, useTranslations } from 'next-intl'
import { AlertCircle, GitBranch, Loader2, PanelLeft, PanelLeftClose, Play, RotateCcw, Square, SquarePlay } from 'lucide-react'
import { ApiError, type NodeExecution, type Workflow, type WorkflowRun, type WorkflowRunListItem } from '@/lib/api'
import { ExecutionTimeline, VariableForm, useVariableForm } from '@/components/chat'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { useWorkflowRun } from '@/hooks/use-workflow-run'
import { jwtWorkflowRunAdapter, type WorkflowRunAdapter } from '@/lib/workflow/run-adapter'
import { extractVariables } from '@/lib/utils/extract-variables'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { cn, formatDateTime } from '@/lib/utils'
import { WorkflowResultRenderer, type WorkflowResultNode } from './workflow-result-renderer'

type WorkflowWorkspaceView = 'form' | 'live' | 'history'

interface WorkflowRunPageProps {
  id: string
  adapter?: WorkflowRunAdapter
  embedMode?: boolean
}

export function WorkflowRunPage({ id, adapter = jwtWorkflowRunAdapter, embedMode }: WorkflowRunPageProps) {
  const router = useRouter()
  const locale = useLocale()
  const t = useTranslations('run')
  const [workflow, setWorkflow] = React.useState<Workflow | null>(null)
  const [isLoading, setIsLoading] = React.useState(true)
  const [error, setError] = React.useState<Error | null>(null)
  const [history, setHistory] = React.useState<WorkflowRunListItem[]>([])
  const [historyLoading, setHistoryLoading] = React.useState(true)
  const [isUploading, setIsUploading] = React.useState(false)
  const [workspaceView, setWorkspaceView] = React.useState<WorkflowWorkspaceView>('form')
  const [sidebarOpen, setSidebarOpen] = React.useState(false)
  const [historyDetailLoading, setHistoryDetailLoading] = React.useState(false)
  const [historyDetailError, setHistoryDetailError] = React.useState<string | null>(null)
  const [selectedRun, setSelectedRun] = React.useState<WorkflowRun | null>(null)
  const [selectedNodes, setSelectedNodes] = React.useState<NodeExecution[]>([])

  React.useEffect(() => {
    const fetchWorkflow = async () => {
      try {
        setIsLoading(true)
        setError(null)
        setWorkflow(await adapter.getWorkflow(id))
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
  }, [id, t, adapter])

  const loadHistory = React.useCallback(async () => {
    try {
      setHistoryLoading(true)
      setHistory(await adapter.loadHistory(id))
    } catch {
      setHistory([])
    } finally {
      setHistoryLoading(false)
    }
  }, [id, adapter])

  React.useEffect(() => {
    void loadHistory()
  }, [loadHistory])

  const variables = React.useMemo(() => extractVariables(workflow, 'workflow'), [workflow])
  const variableForm = useVariableForm(variables)
  const runApi = React.useMemo(() => adapter.createRunApi(), [adapter])
  const run = useWorkflowRun({ workflowId: id, api: runApi, onComplete: loadHistory })
  const isRunning = run.status === 'pending' || run.status === 'running'
  const embedCfg = (embedMode ? workflow?.embed_config : undefined) as Record<string, unknown> | undefined
  const showHeader = !embedMode || embedCfg?.show_header !== false
  const showHistory = !embedMode || embedCfg?.show_history !== false
  const allowNew = !embedMode || embedCfg?.allow_new !== false
  const presentationMode = workflow?.run_page_config?.presentation_mode ?? 'simple'

  React.useEffect(() => {
    setSidebarOpen(window.innerWidth >= 768)
  }, [])

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
      const { run: detail, nodes } = await adapter.loadRunDetail(id, runId)
      setSelectedRun(detail)
      setSelectedNodes(nodes)
    } catch {
      setHistoryDetailError(t('historyDetailError'))
    } finally {
      setHistoryDetailLoading(false)
    }
  }, [id, isRunning, t, adapter])

  const resultNodes = React.useMemo<WorkflowResultNode[]>(() => (
    Array.from(run.executionState.nodes.values()).map((node, index) => ({
      nodeType: node.type,
      outputs: node.output && typeof node.output === 'object' && !Array.isArray(node.output)
        ? node.output as Record<string, unknown>
        : null,
      order: index,
      status: node.status,
    }))
  ), [run.executionState.nodes])

  const savedRunRef = React.useRef<string | null>(null)
  React.useEffect(() => {
    if ((run.status === 'success' || run.status === 'failed') && run.runId && savedRunRef.current !== run.runId) {
      savedRunRef.current = run.runId
      adapter.saveRun(id, {
        runId: run.runId,
        status: run.status,
        outputs: run.outputs,
        nodes: resultNodes,
        error: run.error,
        inputs: run.submittedInputs,
        createdAt: new Date().toISOString(),
      })
    }
  }, [run.status, run.runId, run.outputs, run.error, run.submittedInputs, resultNodes, adapter, id])

  const historyNodes = React.useMemo<WorkflowResultNode[]>(() => (
    selectedNodes.map((node) => ({
      nodeType: node.node_type,
      outputs: node.outputs,
      order: node.execution_order,
      status: node.status,
    }))
  ), [selectedNodes])

  const selectedHistoryId = workspaceView === 'history' ? selectedRun?.id : null
  const displayIcon = workflow?.icon ?? null
  const isIconUrl = Boolean(displayIcon && (displayIcon.startsWith('http') || displayIcon.startsWith('/')))

  const historyPanel = (
    <div className="flex h-full min-h-0 flex-col bg-muted/50">
      <div className="flex items-center gap-2 border-b p-3">
        <button
          type="button"
          className="flex min-w-0 flex-1 items-center gap-2 rounded-md px-2 py-1 text-left hover:bg-accent/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          onClick={handleNewRun}
          disabled={isRunning}
        >
          <span className="relative flex h-7 w-7 shrink-0 items-center justify-center overflow-hidden rounded-md bg-muted text-sm">
            {displayIcon ? (
              isIconUrl ? (
                <Image src={displayIcon} alt={workflow?.name ?? ''} fill unoptimized className="object-cover" />
              ) : (
                displayIcon
              )
            ) : (
              <GitBranch className="h-4 w-4 text-muted-foreground" />
            )}
          </span>
          <span className="truncate text-sm font-medium">{workflow?.name}</span>
        </button>
        <Tooltip>
          <TooltipTrigger
            onClick={handleNewRun}
            disabled={isRunning}
            render={
              <Button
                variant="ghost"
                size="icon"
                className={cn(!allowNew && 'hidden')}
                aria-label={t('newRun')}
              >
                <SquarePlay className="h-4 w-4" />
              </Button>
            }
          />
          <TooltipContent>{t('newRun')}</TooltipContent>
        </Tooltip>
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
                  onClick={() => void handleSelectHistory(item.id)}
                  disabled={isRunning}
                  aria-current={selectedHistoryId === item.id ? 'true' : undefined}
                  className={cn(
                    'min-h-11 w-full rounded-md px-3 py-2.5 text-left transition-colors hover:bg-accent/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50',
                    selectedHistoryId === item.id && 'bg-accent'
                  )}
                >
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-sm font-medium">{t(`status.${item.status}`)}</span>
                    <time className="shrink-0 text-xs text-muted-foreground">
                      {formatDateTime(item.created_at, locale)}
                    </time>
                  </div>
                  <Tooltip>
                    <TooltipTrigger render={<code />} className="mt-1 block truncate text-xs text-muted-foreground cursor-default">
                      {item.id}
                    </TooltipTrigger>
                    <TooltipContent>{item.id}</TooltipContent>
                  </Tooltip>
                </button>
              </li>
            ))}
          </ol>
        )}
      </div>
    </div>
  )

  const renderResult = (nodes: WorkflowResultNode[], resultOutputs: Record<string, unknown> | null, answerText?: string, streaming = false) => (
    <WorkflowResultRenderer
      outputs={resultOutputs}
      nodes={nodes}
      answerText={answerText}
      isStreaming={streaming}
      t={t}
    />
  )

  const answerText = React.useMemo(() => (
    run.messages
      .flatMap((message) => message.role === 'assistant' ? message.parts : [])
      .filter((part) => part.type === 'text')
      .map((part) => part.text)
      .join('')
  ), [run.messages])

  const liveResult = renderResult(resultNodes, run.outputs, answerText, run.isStreaming)
  const historicalResult = selectedRun
    ? renderResult(historyNodes, selectedRun.outputs ?? null)
    : null

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
        id="workflow-history-sidebar"
        aria-labelledby="workflow-history-heading"
        className={cn(
          'h-full shrink-0 overflow-hidden border-r bg-muted/50 transition-all duration-300 ease-in-out',
          sidebarOpen ? 'w-64' : 'w-0 border-r-0',
          !showHistory && 'hidden',
        )}
      >
        <div className="h-full w-64">{historyPanel}</div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className={cn('flex min-h-14 shrink-0 items-center gap-3 border-b px-4 py-3 sm:px-6', !showHeader && 'hidden')}>
          <Button
            variant="ghost"
            size="icon"
            className={cn(!showHistory && 'hidden')}
            onClick={() => setSidebarOpen((open) => !open)}
            aria-label={t('openHistory')}
          >
            {sidebarOpen ? (
              <PanelLeftClose className="h-4 w-4" />
            ) : (
              <PanelLeft className="h-4 w-4" />
            )}
          </Button>
          {allowNew && !sidebarOpen && (
            <Tooltip>
              <TooltipTrigger
                onClick={handleNewRun}
                disabled={isRunning}
                render={
                  <Button variant="ghost" size="icon" aria-label={t('newRun')}>
                    <SquarePlay className="h-4 w-4" />
                  </Button>
                }
              />
              <TooltipContent>{t('newRun')}</TooltipContent>
            </Tooltip>
          )}
          {!sidebarOpen && (
            <>
              <span className="relative flex h-8 w-8 shrink-0 items-center justify-center overflow-hidden rounded-md bg-muted text-lg">
                {displayIcon ? (
                  isIconUrl ? (
                    <Image src={displayIcon} alt={workflow.name} fill unoptimized className="object-cover" />
                  ) : (
                    displayIcon
                  )
                ) : (
                  <GitBranch className="h-4 w-4 text-muted-foreground" />
                )}
              </span>
              <div className="min-w-0 flex-1">
                <h1 className="truncate text-sm font-medium">{workflow.name}</h1>
                {workflow.description && (
                  <p className="line-clamp-1 text-xs text-muted-foreground">
                    {workflow.description}
                  </p>
                )}
              </div>
            </>
          )}
        </header>

        <main className="min-h-0 flex-1 overflow-y-auto">
          <div className="mx-auto w-full max-w-4xl px-4 py-8 sm:px-8 lg:py-12">
            {workspaceView === 'form' && (
              <section aria-labelledby="workflow-inputs-heading">
                <div className="mb-8">
                  <h2 id="workflow-inputs-heading" className="text-2xl font-semibold tracking-tight">
                    {workflow.name}
                  </h2>
                  {workflow.description && (
                    <p className="mt-2 max-w-prose text-sm text-muted-foreground">
                      {workflow.description}
                    </p>
                  )}
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
                    <Tooltip>
                      <TooltipTrigger render={<code />} className="mt-2 block max-w-full truncate text-xs text-muted-foreground cursor-default">
                        {run.runId}
                      </TooltipTrigger>
                      <TooltipContent>{run.runId}</TooltipContent>
                    </Tooltip>
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
                        <Button variant="ghost" onClick={handleNewRun} className={cn(!allowNew && 'hidden')}>
                          <SquarePlay className="mr-2 h-4 w-4" />
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
                ) : liveResult ? (
                  <div className="mt-6 min-w-0">{liveResult}</div>
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
                          {t('time')}{formatDateTime(selectedRun.created_at, locale)}
                        </time>
                        <Tooltip>
                          <TooltipTrigger render={<code />} className="mt-1 block max-w-full truncate text-xs text-muted-foreground cursor-default">
                            {t('runId')}{selectedRun.id}
                          </TooltipTrigger>
                          <TooltipContent>{selectedRun.id}</TooltipContent>
                        </Tooltip>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        <Button variant="outline" onClick={handleRerunFromHistory}>
                          <RotateCcw className="mr-2 h-4 w-4" />
                          {t('runAgain')}
                        </Button>
                        <Button variant="ghost" onClick={handleNewRun} className={cn(!allowNew && 'hidden')}>
                          <SquarePlay className="mr-2 h-4 w-4" />
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
                    {historicalResult ? (
                      <div className="mt-6 min-w-0">{historicalResult}</div>
                    ) : !selectedRun.error_message ? (
                      <p className="mt-6 text-sm text-muted-foreground">{t('noResult')}</p>
                    ) : null}
                    {presentationMode === 'result_first' && selectedNodes.length > 0 && (
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
