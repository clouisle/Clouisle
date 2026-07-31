'use client'

import * as React from 'react'
import { useRouter } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { AlertCircle, GitBranch, History, Loader2, Play, RotateCcw, Square } from 'lucide-react'
import { ApiError, workflowsApi, type NodeExecution, type Workflow, type WorkflowRun, type WorkflowRunListItem } from '@/lib/api'
import { ExecutionTimeline, VariableForm, useVariableForm } from '@/components/chat'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { useWorkflowRun } from '@/hooks/use-workflow-run'
import { extractVariables } from '@/lib/utils/extract-variables'
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
  const [history, setHistory] = React.useState<WorkflowRunListItem[]>([])
  const [historyLoading, setHistoryLoading] = React.useState(true)
  const [isUploading, setIsUploading] = React.useState(false)
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

  const handleRun = async () => {
    if (isUploading || !variableForm.validate()) return
    await run.start(variableForm.values)
  }

  const handleSelectHistory = async (runId: string) => {
    const [detail, nodes] = await Promise.all([
      workflowsApi.getMyWorkflowRun(id, runId),
      workflow?.run_page_config?.presentation_mode === 'result_first'
        ? workflowsApi.getMyRunNodeExecutions(id, runId)
        : Promise.resolve([]),
    ])
    setSelectedRun(detail)
    setSelectedNodes(nodes)
  }

  const historyResult = selectedRun?.outputs
    ? JSON.stringify(selectedRun.outputs, null, 2)
    : ''

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

      <main className="mx-auto grid max-w-6xl gap-10 px-4 py-8 sm:px-6 lg:grid-cols-[minmax(0,1fr)_20rem] lg:py-12">
        <div className="min-w-0 space-y-10">
          <section aria-labelledby="workflow-inputs-heading">
            <div className="mb-6">
              <p className="text-xs font-medium uppercase tracking-widest text-muted-foreground">{t('inputs')}</p>
              <h2 id="workflow-inputs-heading" className="mt-2 text-2xl font-semibold tracking-tight">{t('configureWorkflow')}</h2>
              <p className="mt-2 max-w-prose text-sm text-muted-foreground">{variables.length ? t('fillParameters') : t('noInputs')}</p>
            </div>
            <VariableForm variables={variables} values={variableForm.values} onChange={variableForm.setValues} fieldErrors={variableForm.fieldErrors} compact={false} disabled={isRunning} onUploadingChange={setIsUploading} />
            <div className="mt-6 flex flex-wrap gap-3">
              {isRunning ? (
                <Button variant="outline" onClick={() => void run.stop()} disabled={run.isCancelling}><Square className="mr-2 h-4 w-4" />{run.isCancelling ? t('cancelling') : t('cancel')}</Button>
              ) : (
                <Button onClick={() => void handleRun()} disabled={isUploading}><Play className="mr-2 h-4 w-4" />{t('startRun')}</Button>
              )}
              {run.status !== 'idle' && !isRunning && <Button variant="ghost" onClick={run.reset}><RotateCcw className="mr-2 h-4 w-4" />{t('reset')}</Button>}
            </div>
          </section>

          <section aria-labelledby="workflow-result-heading" aria-live="polite" className="border-t pt-8">
            <div className="flex items-center justify-between gap-4">
              <div><p className="text-xs font-medium uppercase tracking-widest text-muted-foreground">{t('result')}</p><h2 id="workflow-result-heading" className="mt-2 text-xl font-semibold">{t(`status.${run.status}`)}</h2></div>
              {run.runId && <code className="max-w-48 truncate text-xs text-muted-foreground" title={run.runId}>{run.runId}</code>}
            </div>
            {run.error ? <Alert variant="destructive" className="mt-5"><AlertCircle className="h-4 w-4" /><AlertTitle>{t('runFailed')}</AlertTitle><AlertDescription>{run.error}</AlertDescription></Alert> : result ? <pre className="mt-5 max-h-[32rem] overflow-auto whitespace-pre-wrap break-words rounded-lg bg-muted/50 p-5 text-sm leading-6">{result}</pre> : <p className="mt-5 text-sm text-muted-foreground">{isRunning ? t('running') : t('noResult')}</p>}
            {workflow.run_page_config?.presentation_mode === 'result_first' && run.executionState.nodes.size > 0 && (
              <Collapsible className="mt-6 border-t pt-5">
                <CollapsibleTrigger className="min-h-11 text-sm font-medium underline-offset-4 hover:underline">{t('showTrace')}</CollapsibleTrigger>
                <CollapsibleContent className="pt-4"><ExecutionTimeline executionState={run.executionState} /></CollapsibleContent>
              </Collapsible>
            )}
            {selectedRun && (
              <div className="mt-8 border-t pt-6"><div className="flex items-center justify-between gap-3"><h3 className="font-medium">{t('historyResult')}</h3><Button variant="ghost" size="sm" onClick={() => { setSelectedRun(null); setSelectedNodes([]) }}>{t('close')}</Button></div>{historyResult ? <pre className="mt-4 max-h-80 overflow-auto whitespace-pre-wrap break-words rounded-lg bg-muted/50 p-4 text-sm">{historyResult}</pre> : <p className="mt-4 text-sm text-muted-foreground">{t('noResult')}</p>}{selectedNodes.length > 0 && <details className="mt-5"><summary className="cursor-pointer text-sm font-medium">{t('showTrace')}</summary><ol className="mt-3 divide-y">{selectedNodes.map((node) => <li key={node.id} className="py-3 text-sm"><span className="font-medium">{node.node_name}</span><span className="ml-2 text-muted-foreground">{node.status}</span></li>)}</ol></details>}</div>
            )}
          </section>
        </div>

        <aside aria-labelledby="workflow-history-heading" className="min-w-0 border-t pt-8 lg:border-l lg:border-t-0 lg:pl-8 lg:pt-0">
          <div className="flex items-center gap-2"><History className="h-4 w-4 text-muted-foreground" /><h2 id="workflow-history-heading" className="font-medium">{t('history')}</h2></div>
          {historyLoading ? <Loader2 className="mt-6 h-5 w-5 animate-spin text-muted-foreground" /> : history.length === 0 ? <p className="mt-6 text-sm text-muted-foreground">{t('noHistory')}</p> : <ol className="mt-4 divide-y">{history.map((item) => <li key={item.id} className="py-2"><button type="button" onClick={() => void handleSelectHistory(item.id)} className="min-h-11 w-full rounded-md px-2 py-2 text-left hover:bg-muted/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"><div className="flex items-center justify-between gap-3"><span className="text-sm font-medium">{t(`status.${item.status}`)}</span><time className="shrink-0 text-xs text-muted-foreground">{new Date(item.created_at).toLocaleString()}</time></div><code className="mt-1 block truncate text-xs text-muted-foreground" title={item.id}>{item.id}</code></button></li>)}</ol>}
        </aside>
      </main>
    </div>
  )
}
