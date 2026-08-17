'use client'

import * as React from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import Image from 'next/image'
import { useLocale, useTranslations } from 'next-intl'
import { AlertCircle, CheckCircle2, ChevronDown, Circle, GitBranch, Loader2, PanelLeft, PanelLeftClose, Play, RotateCcw, SkipForward, Square, SquarePlay, XCircle } from 'lucide-react'
import { ApiError, type NodeExecution, type Workflow, type WorkflowPauseRequest, type WorkflowRun, type WorkflowRunListItem } from '@/lib/api'
import { ExecutionTimeline, PauseRequestActions, VariableForm, useVariableForm } from '@/components/chat'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { useWorkflowRun } from '@/hooks/use-workflow-run'
import { jwtWorkflowRunAdapter, type WorkflowRunAdapter } from '@/lib/workflow/run-adapter'
import { extractVariables } from '@/lib/utils/extract-variables'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { cn, formatDateTime } from '@/lib/utils'
import { WorkflowResultRenderer, type WorkflowResultNode } from './workflow-result-renderer'
import { renderNodeOutput } from '@/app/(platform)/app/apps/workflow/[id]/_components/node-output-renderer'

type WorkflowWorkspaceView = 'form' | 'live' | 'history'

const TRACE_STATUS_CONFIG: Record<string, {
  icon: React.ComponentType<{ className?: string }>
  dotClass: string
  iconClass: string
  animate?: boolean
}> = {
  pending: { icon: Circle, dotClass: 'border-border', iconClass: 'text-muted-foreground' },
  running: { icon: Loader2, dotClass: 'border-blue-200 dark:border-blue-900', iconClass: 'text-blue-500', animate: true },
  success: { icon: CheckCircle2, dotClass: 'border-green-200 dark:border-green-900', iconClass: 'text-green-500' },
  failed: { icon: XCircle, dotClass: 'border-red-200 dark:border-red-900', iconClass: 'text-red-500' },
  skipped: { icon: SkipForward, dotClass: 'border-border', iconClass: 'text-muted-foreground' },
}

interface WorkflowRunPageProps {
  id: string
  adapter?: WorkflowRunAdapter
  embedMode?: boolean
}

export function WorkflowRunPage({ id, adapter = jwtWorkflowRunAdapter, embedMode }: WorkflowRunPageProps) {
  const router = useRouter()
  const searchParams = useSearchParams()
  const locale = useLocale()
  const t = useTranslations('run')
  const tCommon = useTranslations('common')
  const tTool = useTranslations('chat.tool')
  const tWorkflow = useTranslations('workflow')
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
  const [pendingPause, setPendingPause] = React.useState<WorkflowPauseRequest | null>(null)
  const [pauseError, setPauseError] = React.useState<string | null>(null)
  const [isPauseSubmitting, setIsPauseSubmitting] = React.useState(false)
  const [resumingHistoryRunId, setResumingHistoryRunId] = React.useState<string | null>(null)
  const [isHistoryCancelling, setIsHistoryCancelling] = React.useState(false)

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
  const isWaiting = run.status === 'waiting'
  const isActive = isRunning || isWaiting
  const selectedRunIsWaiting = workspaceView === 'history' && selectedRun?.status === 'waiting'
  const pauseRunId = isWaiting ? run.runId : selectedRunIsWaiting ? selectedRun.id : null
  const embedCfg = (embedMode ? workflow?.embed_config : undefined) as Record<string, unknown> | undefined
  const showHeader = !embedMode || embedCfg?.show_header !== false
  const showHistory = !embedMode || embedCfg?.show_history !== false
  const allowNew = !embedMode || embedCfg?.allow_new !== false
  const presentationMode = workflow?.run_page_config?.presentation_mode ?? 'simple'

  React.useEffect(() => {
    setSidebarOpen(window.innerWidth >= 768)
  }, [])

  // Deep links from approval notifications carry ?run=<runId>; jump straight
  // to that run's detail (the resuming effect loads and pins it). Internal
  // selection (history click) sets the same URL, so suppress the effect there.
  const suppressDeepLinkRef = React.useRef(false)
  const historyLoadGenerationRef = React.useRef(0)
  const selectRunInUrl = React.useCallback((runId: string | null) => {
    const params = new URLSearchParams(searchParams.toString())
    params.set('type', 'workflow')
    if (runId) {
      params.set('run', runId)
    } else {
      params.delete('run')
    }
    router.replace(`/run/${id}?${params.toString()}`, { scroll: false })
  }, [id, router, searchParams])

  React.useEffect(() => {
    if (suppressDeepLinkRef.current) {
      suppressDeepLinkRef.current = false
      return
    }
    const runId = searchParams.get('run')
    if (!runId || resumingHistoryRunId) return
    // The resuming effect pins the run it loads (selectedRun) before clearing
    // resumingHistoryRunId. Guarding on the displayed run keeps the deep link
    // one-shot: otherwise the effect re-arms the moment the resume settles,
    // so refreshing a ?run= URL loops forever (loadRunDetail + loadHistory on
    // every pass) and the history sidebar never leaves its loading state.
    if (selectedRun?.id === runId) return
    setWorkspaceView('history')
    setResumingHistoryRunId(runId)
  }, [searchParams, resumingHistoryRunId, selectedRun])

  React.useEffect(() => {
    if (isActive) {
      setWorkspaceView('live')
    }
  }, [isActive])

  React.useEffect(() => {
    if (!pauseRunId || !adapter.getPendingPauseRequest) {
      setPendingPause(null)
      return
    }

    let active = true
    setPauseError(null)
    void adapter.getPendingPauseRequest(id, pauseRunId)
      .then((request) => {
        if (active) setPendingPause(request)
      })
      .catch(() => {
        if (active) setPauseError(t('pause.loadError'))
      })
    return () => {
      active = false
    }
  }, [adapter, id, pauseRunId, t])

  React.useEffect(() => {
    if (!resumingHistoryRunId || workspaceView !== 'history') return

    const generation = ++historyLoadGenerationRef.current
    let active = true
    let retryTimer: ReturnType<typeof setTimeout> | null = null
    const refresh = async () => {
      try {
        const { run: detail, nodes } = await adapter.loadRunDetail(id, resumingHistoryRunId)
        if (!active || generation !== historyLoadGenerationRef.current) return

        // Accept the first load (current is null) as well as updates for the
        // run being resumed; never clobber a different run the user selected.
        setSelectedRun((current) => (!current || current.id === resumingHistoryRunId) ? detail : current)
        setSelectedNodes(nodes)

        if (detail.status === 'waiting' && adapter.getPendingPauseRequest) {
          const request = await adapter.getPendingPauseRequest(id, resumingHistoryRunId)
          if (!active || generation !== historyLoadGenerationRef.current) return
          if (request) {
            setPendingPause(request)
            setResumingHistoryRunId(null)
            void loadHistory()
            return
          }
        }

        if (['success', 'failed', 'cancelled', 'timeout'].includes(detail.status)) {
          setResumingHistoryRunId(null)
          void loadHistory()
          return
        }

        retryTimer = setTimeout(() => void refresh(), 750)
      } catch {
        if (!active || generation !== historyLoadGenerationRef.current) return
        setHistoryDetailError(t('historyDetailError'))
        // Keep resumingHistoryRunId set: clearing it would let the deep-link
        // effect re-arm and retry a run whose detail keeps failing, looping
        // loadRunDetail forever. Recovery: click a history item or reload.
      }
    }

    void refresh()
    return () => {
      active = false
      if (retryTimer) clearTimeout(retryTimer)
    }
  }, [adapter, id, loadHistory, resumingHistoryRunId, t, workspaceView])

  const handleRun = async () => {
    if (isUploading || !variableForm.validate()) return
    setWorkspaceView('live')
    await run.start(variableForm.values)
  }

  const handlePauseSubmission = React.useCallback(async (
    values: Record<string, unknown>,
    comment?: string,
  ) => {
    if (!pauseRunId || !pendingPause || !adapter.submitPauseRequest) return

    setIsPauseSubmitting(true)
    setPauseError(null)
    try {
      const result = await adapter.submitPauseRequest(id, pauseRunId, pendingPause.id, values, comment)
      const resolved = result?.status === 'submitted'
      if (!resolved) {
        const refreshed = adapter.getPendingPauseRequest
          ? await adapter.getPendingPauseRequest(id, pauseRunId)
          : null
        setPendingPause(refreshed)
        return
      }
      setPendingPause(null)
      if (isWaiting && pauseRunId === run.runId) {
        run.resume()
      } else {
        setSelectedRun((current) => current?.id === pauseRunId
          ? { ...current, status: 'pending' }
          : current)
        setResumingHistoryRunId(pauseRunId)
      }
    } catch {
      setPauseError(t('pause.submitError'))
    } finally {
      setIsPauseSubmitting(false)
    }
  }, [adapter, id, isWaiting, pauseRunId, pendingPause, run, t])

  const handleNewRun = React.useCallback(() => {
    suppressDeepLinkRef.current = true
    historyLoadGenerationRef.current += 1
    run.reset()
    variableForm.reset()
    setSelectedRun(null)
    setSelectedNodes([])
    setHistoryDetailError(null)
    setWorkspaceView('form')
    setPendingPause(null)
    setResumingHistoryRunId(null)
    setPauseError(null)
    selectRunInUrl(null)
  }, [run, variableForm, selectRunInUrl])

  const handleRunAgain = React.useCallback(() => {
    suppressDeepLinkRef.current = true
    historyLoadGenerationRef.current += 1
    run.reset()
    setSelectedRun(null)
    setSelectedNodes([])
    setHistoryDetailError(null)
    setWorkspaceView('form')
    setResumingHistoryRunId(null)
    selectRunInUrl(null)
  }, [run, selectRunInUrl])

  const handleRerunFromHistory = React.useCallback(() => {
    suppressDeepLinkRef.current = true
    historyLoadGenerationRef.current += 1
    if (selectedRun?.inputs) {
      variableForm.setValues(selectedRun.inputs)
    }
    run.reset()
    setSelectedRun(null)
    setSelectedNodes([])
    setHistoryDetailError(null)
    setWorkspaceView('form')
    setResumingHistoryRunId(null)
    selectRunInUrl(null)
  }, [run, selectedRun, variableForm, selectRunInUrl])

  const handleSelectHistory = React.useCallback(async (runId: string) => {
    if (isActive) return
    suppressDeepLinkRef.current = true
    historyLoadGenerationRef.current += 1
    setResumingHistoryRunId(null)
    setWorkspaceView('history')
    setHistoryDetailLoading(true)
    setHistoryDetailError(null)
    try {
      const { run: detail, nodes } = await adapter.loadRunDetail(id, runId)
      setSelectedRun(detail)
      setSelectedNodes(nodes)
      selectRunInUrl(runId)
    } catch {
      setHistoryDetailError(t('historyDetailError'))
    } finally {
      setHistoryDetailLoading(false)
    }
  }, [id, isActive, t, adapter, selectRunInUrl])

  // 等待输入的历史运行可以取消（后端会关闭其暂停请求）；取消后刷新详情，
  // 状态变为 cancelled 后按钮自动切回“再次运行”。
  const handleCancelHistoryRun = React.useCallback(async () => {
    if (!selectedRun) return
    setIsHistoryCancelling(true)
    try {
      await runApi.cancelWorkflowRun(selectedRun.id)
      setPendingPause(null)
      setPauseError(null)
      const { run: detail, nodes } = await adapter.loadRunDetail(id, selectedRun.id)
      setSelectedRun(detail)
      setSelectedNodes(nodes)
    } catch {
      setHistoryDetailError(t('cancelFailed'))
    } finally {
      setIsHistoryCancelling(false)
    }
  }, [selectedRun, runApi, adapter, id, t])

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
    <div className="flex h-full min-h-0 flex-col bg-background">
      {/* Sidebar header */}
      <div className="flex h-14 shrink-0 items-center justify-between p-3">
        <Tooltip>
          <TooltipTrigger
            type="button"
            className="flex min-w-0 cursor-pointer items-center gap-2 rounded-md text-left transition-colors hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            onClick={handleNewRun}
            disabled={isActive}
            render={<button />}
          >
            {displayIcon ? (
              isIconUrl ? (
                <div className="relative h-6 w-6 shrink-0 overflow-hidden">
                  <Image src={displayIcon} alt={workflow?.name ?? ''} fill unoptimized className="object-cover" />
                </div>
              ) : (
                <span className="flex h-6 w-6 shrink-0 items-center justify-center leading-none text-lg">{displayIcon}</span>
              )
            ) : (
              <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">
                <GitBranch className="h-3.5 w-3.5" />
              </div>
            )}
            <span className="max-w-[120px] truncate text-sm font-medium text-foreground">{workflow?.name}</span>
          </TooltipTrigger>
          <TooltipContent>{t('newRun')}</TooltipContent>
        </Tooltip>
        {allowNew && (
          <Tooltip>
            <TooltipTrigger
              onClick={handleNewRun}
              disabled={isActive}
              render={
                <Button variant="ghost" size="icon" className="h-9 w-9" aria-label={t('newRun')}>
                  <SquarePlay className="h-5 w-5" />
                </Button>
              }
            />
            <TooltipContent>{t('newRun')}</TooltipContent>
          </Tooltip>
        )}
      </div>

      {/* Section label */}
      <div id="workflow-history-heading" className="shrink-0 px-4 pb-1 pt-3">
        <span className="text-xs text-muted-foreground">{t('history')}</span>
      </div>

      {/* History list */}
      <div className="min-h-0 flex-1 overflow-y-auto py-2">
        {historyLoading ? (
          <div className="flex justify-center py-4">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        ) : history.length === 0 ? (
          <div className="px-3 py-4 text-center text-sm text-muted-foreground">{t('noHistory')}</div>
        ) : (
          <div className="space-y-1 px-2">
            {history.map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => void handleSelectHistory(item.id)}
                disabled={isActive}
                aria-current={selectedHistoryId === item.id ? 'true' : undefined}
                className={cn(
                  'group flex w-full items-center gap-2 rounded-lg px-3 py-2 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50',
                  selectedHistoryId === item.id ? 'bg-accent' : 'hover:bg-accent/50'
                )}
              >
                <GitBranch className="h-4 w-4 shrink-0 text-muted-foreground" />
                <span className="flex min-w-0 flex-1 flex-col">
                  <span className="truncate text-sm font-medium">{t(`status.${item.status}`)}</span>
                  <Tooltip>
                    <TooltipTrigger render={<code />} className="block cursor-default truncate text-xs text-muted-foreground">
                      {item.id}
                    </TooltipTrigger>
                    <TooltipContent>{item.id}</TooltipContent>
                  </Tooltip>
                </span>
                <time className="shrink-0 text-xs text-muted-foreground">
                  {formatDateTime(item.created_at, locale)}
                </time>
              </button>
            ))}
          </div>
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
          'flex h-full shrink-0 flex-col overflow-hidden border-r bg-background transition-all duration-300 ease-in-out',
          sidebarOpen ? 'w-64' : 'w-0 border-r-0',
          !showHistory && 'hidden',
        )}
      >
        <div className="flex h-full w-64 min-h-0 flex-col">{historyPanel}</div>
      </aside>

      <div className="relative flex min-w-0 flex-1 flex-col">
        {/* Header - floating over the workspace area, no bar background */}
        <header className={cn('absolute inset-x-0 top-0 z-10 flex items-center gap-2 px-3 py-3', !showHeader && 'hidden')}>
          {!(showHistory && sidebarOpen) && (
            <>
              {displayIcon ? (
                isIconUrl ? (
                  <div className="relative h-6 w-6 shrink-0 overflow-hidden">
                    <Image src={displayIcon} alt={workflow.name} fill unoptimized className="object-cover" />
                  </div>
                ) : (
                  <span className="flex h-6 w-6 shrink-0 items-center justify-center leading-none text-lg">{displayIcon}</span>
                )
              ) : (
                <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">
                  <GitBranch className="h-3.5 w-3.5" />
                </div>
              )}
              <div className="mr-2 min-w-0">
                <span className="block truncate text-sm font-medium text-foreground">{workflow.name}</span>
              </div>
            </>
          )}
          {showHistory && (
            <Button
              variant="outline"
              size="icon"
              className="h-9 w-9 rounded-full bg-background/80 shadow-sm backdrop-blur-sm"
              onClick={() => setSidebarOpen((open) => !open)}
              aria-label={sidebarOpen ? t('closeHistory') : t('openHistory')}
            >
              {sidebarOpen ? (
                <PanelLeftClose className="h-5 w-5" />
              ) : (
                <PanelLeft className="h-5 w-5" />
              )}
            </Button>
          )}
          {allowNew && (!showHistory || !sidebarOpen) && (
            <Tooltip>
              <TooltipTrigger
                onClick={handleNewRun}
                disabled={isActive}
                render={
                  <Button variant="outline" size="icon" className="h-9 w-9 rounded-full bg-background/80 shadow-sm backdrop-blur-sm" aria-label={t('newRun')}>
                    <SquarePlay className="h-5 w-5" />
                  </Button>
                }
              />
              <TooltipContent>{t('newRun')}</TooltipContent>
            </Tooltip>
          )}
        </header>

        <main className="min-h-0 flex-1 overflow-y-auto">
          <div className={cn('mx-auto w-full max-w-4xl px-4 sm:px-8', showHeader ? 'pb-8 pt-24 lg:pb-12 lg:pt-28' : 'py-8 lg:py-12')}>
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
                  disabled={isActive}
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
                    {isActive ? (
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

                {isWaiting && pendingPause && adapter.submitPauseRequest && (
                  <PauseRequestActions
                    workflowId={id}
                    runId={pauseRunId ?? ''}
                    pauseRequestId={pendingPause.id}
                    request={pendingPause}
                    values={variableForm.values}
                    onValuesChange={variableForm.setValues}
                    onSubmit={(values, comment) => void handlePauseSubmission(values, comment)}
                    submitting={isPauseSubmitting}
                    error={pauseError}
                    canSubmit={pendingPause.can_submit}
                    approverNames={pendingPause.approver_names}
                  />
                )}

                {isWaiting && !pendingPause && pauseError && (
                  <Alert variant="destructive" className="mt-6">
                    <AlertDescription>{pauseError}</AlertDescription>
                  </Alert>
                )}

                {isWaiting && adapter.submitPauseRequest && !pendingPause && !pauseError && (
                  <Alert className="mt-6">
                    <AlertDescription>{t('pause.waitingForReview')}</AlertDescription>
                  </Alert>
                )}

                {isWaiting && !adapter.submitPauseRequest && (
                  <Alert className="mt-6 border-amber-500/30 bg-amber-500/[0.08]">
                    <AlertDescription>{t('pause.embedNotice')}</AlertDescription>
                  </Alert>
                )}

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
                      <ExecutionTimeline executionState={run.executionState} showDetails={!embedMode} />
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
                        {selectedRun.status === 'waiting' ? (
                          <Button
                            variant="outline"
                            onClick={() => void handleCancelHistoryRun()}
                            disabled={isHistoryCancelling}
                          >
                            {isHistoryCancelling ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Square className="mr-2 h-4 w-4" />}
                            {isHistoryCancelling ? t('cancelling') : t('cancel')}
                          </Button>
                        ) : (
                          <Button variant="outline" onClick={handleRerunFromHistory}>
                            <RotateCcw className="mr-2 h-4 w-4" />
                            {t('runAgain')}
                          </Button>
                        )}
                        <Button variant="ghost" onClick={handleNewRun} className={cn(!allowNew && 'hidden')}>
                          <SquarePlay className="mr-2 h-4 w-4" />
                          {t('newRun')}
                        </Button>
                      </div>
                    </div>
                    {selectedRun.status === 'waiting' && pendingPause && adapter.submitPauseRequest && (
                      <PauseRequestActions
                        workflowId={id}
                        runId={pauseRunId ?? ''}
                        pauseRequestId={pendingPause.id}
                        request={pendingPause}
                        values={variableForm.values}
                        onValuesChange={variableForm.setValues}
                        onSubmit={(values, comment) => void handlePauseSubmission(values, comment)}
                        submitting={isPauseSubmitting}
                        error={pauseError}
                        canSubmit={pendingPause.can_submit}
                        approverNames={pendingPause.approver_names}
                      />
                    )}
                    {selectedRun.status === 'waiting' && !pendingPause && pauseError && (
                      <Alert variant="destructive" className="mt-6">
                        <AlertDescription>{pauseError}</AlertDescription>
                      </Alert>
                    )}
                    {selectedRun.status === 'waiting' && adapter.submitPauseRequest && !pendingPause && !pauseError && (
                      <Alert className="mt-6">
                        <AlertDescription>{t('pause.waitingForReview')}</AlertDescription>
                      </Alert>
                    )}
                    {selectedRun.status === 'waiting' && !adapter.submitPauseRequest && (
                      <Alert className="mt-6 border-amber-500/30 bg-amber-500/[0.08]">
                        <AlertDescription>{t('pause.embedNotice')}</AlertDescription>
                      </Alert>
                    )}
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
                    {selectedNodes.length > 0 && (
                      <Collapsible className="mt-8 border-t pt-5">
                        <CollapsibleTrigger className="min-h-11 text-sm font-medium underline-offset-4 hover:underline">
                          {t('showTrace')}
                        </CollapsibleTrigger>
                        <CollapsibleContent className="pt-4">
                          <ol className="relative">
                            {selectedNodes
                              .slice()
                              .sort((a, b) => a.execution_order - b.execution_order)
                              .map((node, index) => {
                                const config = TRACE_STATUS_CONFIG[node.status] ?? TRACE_STATUS_CONFIG.pending
                                const StatusIcon = config.icon
                                return (
                                  <li key={node.id} className="relative pb-5 pl-9 last:pb-0">
                                    {index < selectedNodes.length - 1 && (
                                      <span
                                        aria-hidden
                                        className="absolute bottom-0 left-[11px] top-6 w-px bg-border"
                                      />
                                    )}
                                    <span
                                      className={cn(
                                        'absolute left-0 top-0 flex h-6 w-6 items-center justify-center rounded-full border bg-background',
                                        config.dotClass
                                      )}
                                    >
                                      <StatusIcon className={cn('h-3.5 w-3.5', config.iconClass, config.animate && 'animate-spin')} />
                                    </span>
                                    <div className="min-w-0 pt-0.5">
                                      <div className="flex items-baseline justify-between gap-3">
                                        <span className="truncate text-sm font-medium">{node.node_name}</span>
                                        <span className="shrink-0 text-xs text-muted-foreground">
                                          {t(`nodeStatus.${node.status}`)}
                                        </span>
                                      </div>
                                      {!embedMode && node.error_message && (
                                        <p className="mt-1 text-xs text-red-600 dark:text-red-400">{node.error_message}</p>
                                      )}
                                      {!embedMode && ((node.inputs && Object.keys(node.inputs).length > 0) ||
                                        (node.outputs && Object.keys(node.outputs).length > 0 && !node.error_message)) && (
                                        <details className="group mt-1">
                                          <summary className="flex list-none cursor-pointer items-center gap-1 text-xs text-muted-foreground transition-colors hover:text-foreground">
                                            <ChevronDown className="h-3 w-3 transition-transform group-open:rotate-180" />
                                            {tCommon('showDetails')}
                                          </summary>
                                          <div className="mt-2 space-y-2">
                                            {node.inputs && Object.keys(node.inputs).length > 0 && (
                                              <div>
                                                <div className="mb-1 text-xs font-medium text-muted-foreground">
                                                  {tTool('input')}
                                                </div>
                                                <pre className="overflow-x-auto rounded bg-background/50 p-2 text-xs">
                                                  {JSON.stringify(node.inputs, null, 2)}
                                                </pre>
                                              </div>
                                            )}
                                            {node.outputs && Object.keys(node.outputs).length > 0 && !node.error_message && (
                                              <div>
                                                <div className="mb-1 text-xs font-medium text-muted-foreground">
                                                  {tTool('output')}
                                                </div>
                                                {renderNodeOutput(node.node_type, node.outputs, tWorkflow)}
                                              </div>
                                            )}
                                          </div>
                                        </details>
                                      )}
                                    </div>
                                  </li>
                                )
                              })}
                          </ol>
                        </CollapsibleContent>
                      </Collapsible>
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
