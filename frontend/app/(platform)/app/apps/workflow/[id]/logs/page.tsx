'use client'

import * as React from 'react'
import { useParams, useRouter } from 'next/navigation'
import { useTranslations, useLocale } from 'next-intl'
import {
  Calendar,
  Activity,
  ChevronLeft,
  ChevronRight,
  ArrowLeft,
  ExternalLink,
  FileText,
  LayoutGrid,
  GitBranch,
  CheckCircle,
  XCircle,
  Clock,
  Loader2 as LoaderIcon
} from 'lucide-react'
import Image from 'next/image'
import { workflowsApi, type Workflow, type WorkflowRunListItem } from '@/lib/api/workflows'
import { Skeleton } from '@/components/ui/skeleton'
import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Badge } from '@/components/ui/badge'

const PAGE_SIZE = 20

// Helper to format datetime
function formatDateTime(dateString: string, locale: string): string {
  const date = new Date(dateString)
  if (locale === 'zh') {
    return date.toLocaleString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    })
  } else {
    return date.toLocaleString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    })
  }
}

// Status badge component
function StatusBadge({ status }: { status: string }) {
  const t = useTranslations('workflow')

  switch (status) {
    case 'completed':
      return (
        <Badge variant="default" className="bg-green-500 hover:bg-green-600">
          <CheckCircle className="h-3 w-3 mr-1" />
          {t('completed')}
        </Badge>
      )
    case 'failed':
      return (
        <Badge variant="destructive">
          <XCircle className="h-3 w-3 mr-1" />
          {t('failed')}
        </Badge>
      )
    case 'running':
      return (
        <Badge variant="secondary" className="bg-blue-500 hover:bg-blue-600 text-white">
          <LoaderIcon className="h-3 w-3 mr-1 animate-spin" />
          {t('running')}
        </Badge>
      )
    case 'pending':
      return (
        <Badge variant="outline">
          <Clock className="h-3 w-3 mr-1" />
          {t('pending')}
        </Badge>
      )
    default:
      return <Badge variant="outline">{status}</Badge>
  }
}

export default function WorkflowLogsPage() {
  const params = useParams()
  const router = useRouter()
  const t = useTranslations('workflow')
  const locale = useLocale()

  const workflowId = params.id as string

  const [workflow, setWorkflow] = React.useState<Workflow | null>(null)
  const [isLoading, setIsLoading] = React.useState(true)
  const [runs, setRuns] = React.useState<WorkflowRunListItem[]>([])
  const [totalRuns, setTotalRuns] = React.useState(0)
  const [currentPage, setCurrentPage] = React.useState(1)
  const [isLoadingRuns, setIsLoadingRuns] = React.useState(false)

  // Search and filter state
  const [statusFilter, setStatusFilter] = React.useState('all')
  const [dateFilter, setDateFilter] = React.useState('all')

  // Fetch workflow data
  const fetchWorkflow = React.useCallback(async () => {
    try {
      setIsLoading(true)
      const data = await workflowsApi.getWorkflow(workflowId)
      setWorkflow(data)
    } catch {
      router.push('/app/apps')
    } finally {
      setIsLoading(false)
    }
  }, [workflowId, router])

  // Fetch workflow runs
  const fetchRuns = React.useCallback(async (page: number = 1) => {
    try {
      setIsLoadingRuns(true)
      const result = await workflowsApi.getWorkflowRuns(workflowId, {
        page,
        pageSize: PAGE_SIZE,
        status: statusFilter !== 'all' ? statusFilter as 'pending' | 'running' | 'success' | 'failed' | 'cancelled' | 'timeout' : undefined,
      })
      setRuns(result.items)
      setTotalRuns(result.total)
      setCurrentPage(page)
    } catch {
      // Error handled by API client
    } finally {
      setIsLoadingRuns(false)
    }
  }, [workflowId, statusFilter])

  React.useEffect(() => {
    fetchWorkflow()
  }, [fetchWorkflow])

  React.useEffect(() => {
    if (workflow) {
      fetchRuns()
    }
  }, [workflow, fetchRuns])

  // Filter runs (client-side for search)
  const filteredRuns = React.useMemo(() => {
    let result = [...runs]

    // Date filter
    if (dateFilter !== 'all') {
      const now = new Date()
      const cutoff = new Date()
      switch (dateFilter) {
        case '7d':
          cutoff.setDate(now.getDate() - 7)
          break
        case '30d':
          cutoff.setDate(now.getDate() - 30)
          break
        case '90d':
          cutoff.setDate(now.getDate() - 90)
          break
      }
      result = result.filter((r) => new Date(r.created_at) >= cutoff)
    }

    return result
  }, [runs, dateFilter])

  const totalPages = Math.ceil(totalRuns / PAGE_SIZE)

  if (isLoading || !workflow) {
    return (
      <div className="flex h-screen items-center justify-center">
        <LoaderIcon className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  return (
    <div className="flex h-screen flex-col">
      {/* Header */}
      <div className="absolute top-4 left-4 z-50 flex items-center gap-2">
        {/* Back Button */}
        <Button
          variant="ghost"
          size="icon"
          className="h-9 w-9 bg-card shadow-sm"
          onClick={() => router.push('/app/apps')}
        >
          <ArrowLeft className="h-4 w-4" />
        </Button>

        {/* Workflow Dropdown Menu */}
        <DropdownMenu>
          <DropdownMenuTrigger className="inline-flex items-center justify-center rounded-md text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 border border-input hover:bg-accent hover:text-accent-foreground h-9 bg-card shadow-sm gap-2 px-2">
            {workflow.icon && (workflow.icon.startsWith('http') || workflow.icon.startsWith('/')) ? (
              <Image
                src={workflow.icon}
                alt={workflow.name || ''}
                width={20}
                height={20}
                className="rounded object-cover"
                unoptimized
              />
            ) : (
              <div className="flex h-5 w-5 shrink-0 items-center justify-center rounded bg-primary/10">
                <GitBranch className="h-3 w-3 text-primary" />
              </div>
            )}
            <span className="text-sm font-medium max-w-32 truncate">{workflow.name || t('untitled')}</span>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="w-48">
            <DropdownMenuItem
              className="gap-2"
              onClick={() => router.push(`/app/apps/workflow/${workflowId}`)}
            >
              <LayoutGrid className="h-4 w-4" />
              <span>{t('orchestrate')}</span>
            </DropdownMenuItem>
            <DropdownMenuItem
              className="gap-2"
              onClick={() => router.push(`/app/apps/workflow/${workflowId}/api`)}
            >
              <ExternalLink className="h-4 w-4" />
              <span>{t('accessApi')}</span>
            </DropdownMenuItem>
            <DropdownMenuItem className="gap-2 bg-primary/10 text-primary">
              <FileText className="h-4 w-4" />
              <span>{t('logs')}</span>
            </DropdownMenuItem>
            <DropdownMenuItem
              className="gap-2"
              onClick={() => router.push(`/app/apps/${workflowId}/monitor`)}
            >
              <Activity className="h-4 w-4" />
              <span>{t('monitor')}</span>
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      {/* Content */}
      <div className="flex-1 flex flex-col overflow-hidden pt-20">
        {/* Filters Bar */}
        <div className="px-6 py-4 border-b shrink-0">
          <div className="flex items-center gap-3 flex-wrap">
            {/* Status Filter */}
            <Select value={statusFilter} onValueChange={(v) => v && setStatusFilter(v)}>
              <SelectTrigger className="w-40 h-9">
                <Activity className="h-4 w-4 mr-2 text-muted-foreground" />
                <SelectValue>
                  {statusFilter === 'all' && t('allStatus')}
                  {statusFilter === 'completed' && t('completed')}
                  {statusFilter === 'failed' && t('failed')}
                  {statusFilter === 'running' && t('running')}
                  {statusFilter === 'pending' && t('pending')}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">{t('allStatus')}</SelectItem>
                <SelectItem value="completed">{t('completed')}</SelectItem>
                <SelectItem value="failed">{t('failed')}</SelectItem>
                <SelectItem value="running">{t('running')}</SelectItem>
                <SelectItem value="pending">{t('pending')}</SelectItem>
              </SelectContent>
            </Select>

            {/* Date Filter */}
            <Select value={dateFilter} onValueChange={(v) => v && setDateFilter(v)}>
              <SelectTrigger className="w-40 h-9">
                <Calendar className="h-4 w-4 mr-2 text-muted-foreground" />
                <SelectValue>
                  {dateFilter === 'all' && t('allTime')}
                  {dateFilter === '7d' && t('last7Days')}
                  {dateFilter === '30d' && t('last30Days')}
                  {dateFilter === '90d' && t('last90Days')}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">{t('allTime')}</SelectItem>
                <SelectItem value="7d">{t('last7Days')}</SelectItem>
                <SelectItem value="30d">{t('last30Days')}</SelectItem>
                <SelectItem value="90d">{t('last90Days')}</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>

        {/* Table */}
        <div className="flex-1 overflow-auto px-6">
          {isLoadingRuns ? (
            <div className="py-6 space-y-3">
              {[...Array(5)].map((_, i) => (
                <Skeleton key={i} className="h-12 w-full" />
              ))}
            </div>
          ) : filteredRuns.length === 0 ? (
            <div className="flex-1 flex items-center justify-center py-16">
              <div className="text-center text-muted-foreground">
                <Activity className="h-12 w-12 mx-auto mb-3 opacity-30" />
                <p>{t('noRuns')}</p>
              </div>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead className="w-20">{t('runId')}</TableHead>
                  <TableHead className="w-25">{t('status')}</TableHead>
                  <TableHead className="w-25">{t('triggerType')}</TableHead>
                  <TableHead className="w-30">{t('duration')}</TableHead>
                  <TableHead className="w-45">{t('createdAt')}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredRuns.map((run) => (
                  <TableRow
                    key={run.id}
                    className="cursor-pointer"
                    onClick={() => {
                      // TODO: Open run detail drawer
                      console.log('Open run detail:', run.id)
                    }}
                  >
                    <TableCell className="font-mono text-xs">
                      {run.id.slice(0, 8)}...
                    </TableCell>
                    <TableCell>
                      <StatusBadge status={run.status} />
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline">{run.trigger_type}</Badge>
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {run.finished_at && run.started_at
                        ? `${Math.round((new Date(run.finished_at).getTime() - new Date(run.started_at).getTime()) / 1000)}s`
                        : '-'}
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {formatDateTime(run.created_at, locale)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="px-6 py-3 border-t flex items-center justify-between shrink-0">
            <p className="text-sm text-muted-foreground">
              {t('showingRuns', {
                from: (currentPage - 1) * PAGE_SIZE + 1,
                to: Math.min(currentPage * PAGE_SIZE, totalRuns),
                total: totalRuns,
              })}
            </p>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={currentPage === 1}
                onClick={() => fetchRuns(currentPage - 1)}
              >
                <ChevronLeft className="h-4 w-4 mr-1" />
                {t('prev')}
              </Button>
              <span className="text-sm text-muted-foreground px-2">
                {currentPage} / {totalPages}
              </span>
              <Button
                variant="outline"
                size="sm"
                disabled={currentPage === totalPages}
                onClick={() => fetchRuns(currentPage + 1)}
              >
                {t('next')}
                <ChevronRight className="h-4 w-4 ml-1" />
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
