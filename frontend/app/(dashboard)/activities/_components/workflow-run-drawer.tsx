'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import {
  CheckCircle,
  XCircle,
  Clock,
  Loader,
  Ban,
  AlertTriangle,
  Trash2,
} from 'lucide-react'
import { toast } from 'sonner'
import { workflowsApi, type WorkflowRun, type NodeExecution } from '@/lib/api'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Separator } from '@/components/ui/separator'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { useCanPerform } from '@/components/permission-guard'

interface WorkflowRunDrawerProps {
  runId: string
  open: boolean
  onOpenChange: (open: boolean) => void
  onDelete?: () => void
}

// Helper to format datetime
function formatDateTime(dateString: string | null | undefined): string {
  if (!dateString) return '-'
  const d = new Date(dateString)
  const year = d.getFullYear()
  const month = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  const hour = String(d.getHours()).padStart(2, '0')
  const minute = String(d.getMinutes()).padStart(2, '0')
  return `${year}/${month}/${day} ${hour}:${minute}`
}

// Helper to format duration
function formatDuration(ms: number | null | undefined): string {
  if (!ms) return '-'
  const seconds = Math.floor(ms / 1000)
  if (seconds < 60) return `${seconds}s`
  const minutes = Math.floor(seconds / 60)
  const remainingSeconds = seconds % 60
  return `${minutes}m ${remainingSeconds}s`
}

// Status badge component
function StatusBadge({ status, tWorkflow }: { status: string; tWorkflow: ReturnType<typeof useTranslations> }) {
  const statusConfig: Record<string, { icon: React.ReactNode; className: string; label: string }> = {
    success: {
      icon: <CheckCircle className="h-3 w-3" />,
      className: 'bg-green-500/10 text-green-700 dark:text-green-400 border-green-500/20',
      label: tWorkflow('completed'),
    },
    failed: {
      icon: <XCircle className="h-3 w-3" />,
      className: 'bg-red-500/10 text-red-700 dark:text-red-400 border-red-500/20',
      label: tWorkflow('failed'),
    },
    running: {
      icon: <Loader className="h-3 w-3 animate-spin" />,
      className: 'bg-blue-500/10 text-blue-700 dark:text-blue-400 border-blue-500/20',
      label: tWorkflow('running'),
    },
    pending: {
      icon: <Clock className="h-3 w-3" />,
      className: 'bg-gray-500/10 text-gray-700 dark:text-gray-400 border-gray-500/20',
      label: tWorkflow('pending'),
    },
    cancelled: {
      icon: <Ban className="h-3 w-3" />,
      className: 'bg-yellow-500/10 text-yellow-700 dark:text-yellow-400 border-yellow-500/20',
      label: tWorkflow('cancelled'),
    },
    timeout: {
      icon: <AlertTriangle className="h-3 w-3" />,
      className: 'bg-orange-500/10 text-orange-700 dark:text-orange-400 border-orange-500/20',
      label: tWorkflow('timeout'),
    },
  }

  const config = statusConfig[status] || statusConfig.pending

  return (
    <Badge variant="outline" className={config.className}>
      <span className="flex items-center gap-1">
        {config.icon}
        {config.label}
      </span>
    </Badge>
  )
}

export function WorkflowRunDrawer({ runId, open, onOpenChange, onDelete }: WorkflowRunDrawerProps) {
  const t = useTranslations('activities')
  const tWorkflow = useTranslations('workflow')
  const commonT = useTranslations('common')
  const { canPerform } = useCanPerform()
  const canDeleteWorkflowRun = canPerform('workflow:delete')

  const [run, setRun] = React.useState<WorkflowRun | null>(null)
  const [nodeExecutions, setNodeExecutions] = React.useState<NodeExecution[]>([])
  const [loading, setLoading] = React.useState(true)
  const [deleteDialogOpen, setDeleteDialogOpen] = React.useState(false)

  // Load run details
  React.useEffect(() => {
    if (!open || !runId) return

    const loadRunDetails = async () => {
      try {
        setLoading(true)
        console.log('Loading run details for:', runId)

        const [runData, nodesData] = await Promise.all([
          workflowsApi.getWorkflowRun(runId),
          workflowsApi.getRunNodeExecutions(runId),
        ])

        console.log('Run data:', runData)
        console.log('Node executions:', nodesData)

        setRun(runData)
        setNodeExecutions(nodesData)
      } catch (error) {
        console.error('Failed to load run details:', error)
      } finally {
        setLoading(false)
      }
    }

    loadRunDetails()
  }, [runId, open])

  const handleDelete = async () => {
    try {
      await workflowsApi.deleteWorkflowRun(runId)
      toast.success(t('runDetail.deleteSuccess'))
      onDelete?.()
      onOpenChange(false)
    } catch (error) {
      console.error('Failed to delete run:', error)
    } finally {
      setDeleteDialogOpen(false)
    }
  }

  if (loading || !run) {
    return (
      <Sheet open={open} onOpenChange={onOpenChange}>
        <SheetContent className="sm:max-w-2xl p-0 flex flex-col">
          <SheetHeader className="px-6 py-4 border-b shrink-0">
            <SheetTitle>{t('runDetail.title')}</SheetTitle>
          </SheetHeader>
          <div className="flex-1 flex items-center justify-center">
            <Loader className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        </SheetContent>
      </Sheet>
    )
  }

  return (
    <>
      <Sheet open={open} onOpenChange={onOpenChange}>
        <SheetContent className="sm:max-w-2xl p-0 flex flex-col">
          <SheetHeader className="px-6 py-4 border-b shrink-0">
            <SheetTitle>{t('runDetail.title')}</SheetTitle>
            <SheetDescription>
              <code className="text-xs">{run.id}</code>
            </SheetDescription>
          </SheetHeader>

          <div className="flex-1 overflow-y-auto">
            <div className="px-6 py-6 space-y-6">
            {/* Basic Info */}
            <div>
              <h3 className="text-sm font-semibold mb-3">{t('runDetail.basicInfo')}</h3>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">{t('table.status')}</span>
                  <StatusBadge status={run.status} tWorkflow={tWorkflow} />
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">{t('table.triggerType')}</span>
                  <Badge variant="outline">{run.trigger_type}</Badge>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">{t('table.createdAt')}</span>
                  <span>{formatDateTime(run.created_at)}</span>
                </div>
                {run.started_at && (
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">{t('runDetail.startedAt')}</span>
                    <span>{formatDateTime(run.started_at)}</span>
                  </div>
                )}
                {run.finished_at && (
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">{t('runDetail.finishedAt')}</span>
                    <span>{formatDateTime(run.finished_at)}</span>
                  </div>
                )}
                <div className="flex justify-between">
                  <span className="text-muted-foreground">{t('table.duration')}</span>
                  <span>{formatDuration(run.total_duration_ms)}</span>
                </div>
                {run.is_debug && (
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">{t('runDetail.debugMode')}</span>
                    <Badge variant="secondary">{t('runDetail.debug')}</Badge>
                  </div>
                )}
              </div>
            </div>

            <Separator />

            {/* Execution Stats */}
            <div>
              <h3 className="text-sm font-semibold mb-3">{t('runDetail.executionStats')}</h3>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1">
                  <p className="text-xs text-muted-foreground">{t('runDetail.executedNodes')}</p>
                  <p className="text-2xl font-bold">{run.executed_nodes}/{run.total_nodes}</p>
                </div>
                <div className="space-y-1">
                  <p className="text-xs text-muted-foreground">{t('runDetail.failedNodes')}</p>
                  <p className="text-2xl font-bold text-destructive">{run.failed_nodes}</p>
                </div>
                {run.total_token_usage && Object.keys(run.total_token_usage).length > 0 && (
                  <div className="space-y-1 col-span-2">
                    <p className="text-xs text-muted-foreground">{t('runDetail.totalTokens')}</p>
                    <p className="text-2xl font-bold">
                      {Object.values(run.total_token_usage).reduce((a, b) => a + b, 0).toLocaleString()}
                    </p>
                  </div>
                )}
              </div>
            </div>

            <Separator />

            {/* Error Info */}
            {run.error_message && (
              <>
                <div>
                  <h3 className="text-sm font-semibold mb-3">{t('runDetail.errorInfo')}</h3>
                  <Alert variant="destructive">
                    <XCircle className="h-4 w-4" />
                    <AlertTitle>{tWorkflow('failed')}</AlertTitle>
                    <AlertDescription className="mt-2 text-sm">
                      {run.error_message}
                    </AlertDescription>
                    {run.error_node_id && (
                      <AlertDescription className="mt-2 text-xs text-muted-foreground">
                        Node: <code>{run.error_node_id}</code>
                      </AlertDescription>
                    )}
                  </Alert>
                </div>
                <Separator />
              </>
            )}

            {/* Inputs/Outputs */}
            <div>
              <Tabs defaultValue="inputs">
                <TabsList className="grid w-full grid-cols-2">
                  <TabsTrigger value="inputs">{t('runDetail.inputs')}</TabsTrigger>
                  <TabsTrigger value="outputs">{t('runDetail.outputs')}</TabsTrigger>
                </TabsList>
                <TabsContent value="inputs" className="mt-4">
                  <pre className="text-xs bg-muted p-4 rounded-md overflow-x-auto">
                    {JSON.stringify(run.inputs, null, 2)}
                  </pre>
                </TabsContent>
                <TabsContent value="outputs" className="mt-4">
                  {run.outputs ? (
                    <pre className="text-xs bg-muted p-4 rounded-md overflow-x-auto">
                      {JSON.stringify(run.outputs, null, 2)}
                    </pre>
                  ) : (
                    <p className="text-sm text-muted-foreground text-center py-4">
                      {t('runDetail.noOutputs')}
                    </p>
                  )}
                </TabsContent>
              </Tabs>
            </div>

            <Separator />

            {/* Node Executions */}
            <div>
              <h3 className="text-sm font-semibold mb-3">{t('runDetail.nodeExecutions')}</h3>
              {nodeExecutions.length === 0 ? (
                <p className="text-sm text-muted-foreground text-center py-4">
                  {t('runDetail.noNodeExecutions')}
                </p>
              ) : (
                <div className="space-y-2">
                  {nodeExecutions.map((node) => (
                    <div
                      key={node.id}
                      className="border rounded-lg p-3 space-y-2"
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-medium">{node.node_name}</span>
                          <Badge variant="outline" className="text-xs">
                            {node.node_type}
                          </Badge>
                        </div>
                        <StatusBadge status={node.status} tWorkflow={tWorkflow} />
                      </div>
                      <div className="text-xs text-muted-foreground space-y-1">
                        <div className="flex justify-between">
                          <span>Duration</span>
                          <span>{formatDuration(node.execution_duration_ms)}</span>
                        </div>
                        {node.total_tokens && (
                          <div className="flex justify-between">
                            <span>Tokens</span>
                            <span>{node.total_tokens.toLocaleString()}</span>
                          </div>
                        )}
                        {node.error_message && (
                          <div className="text-destructive mt-2">
                            {t('runDetail.errorInfo')}: {node.error_message}
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Actions */}
            <div className="flex justify-end gap-2 pt-4">
              <Button
                variant="outline"
                onClick={() => onOpenChange(false)}
              >
                {commonT('close')}
              </Button>
              {canDeleteWorkflowRun && (
                <Button
                  variant="destructive"
                  onClick={() => setDeleteDialogOpen(true)}
                >
                  <Trash2 className="mr-2 h-4 w-4" />
                  {t('runDetail.deleteRun')}
                </Button>
              )}
            </div>
          </div>
        </div>
        </SheetContent>
      </Sheet>

      {/* Delete Confirmation Dialog */}
      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('runDetail.deleteRun')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('runDetail.confirmDelete')}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{commonT('cancel')}</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              onClick={handleDelete}
            >
              {commonT('delete')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}
