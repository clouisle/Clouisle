'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import {
  Search,
  Workflow,
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  X,
  Trash2,
  MoreHorizontal,
  CheckCircle,
  XCircle,
  Clock,
  Loader,
  Ban,
  AlertTriangle,
} from 'lucide-react'
import { toast } from 'sonner'
import {
  workflowsApi,
  type WorkflowRunListItemWithWorkflow,
  type WorkflowListItem,
  type RunStatus,
  type TriggerType,
} from '@/lib/api'
import { teamsApi } from '@/lib/api/admin/teams'
import { usersApi } from '@/lib/api/admin/users'
import type { Team } from '@/lib/api/teams'
import type { User } from '@/lib/api/auth'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Checkbox } from '@/components/ui/checkbox'
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
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { DataTableFacetedFilter } from '@/components/ui/data-table-faceted-filter'
import { WorkflowRunDrawer } from './workflow-run-drawer'
import { useCanPerform } from '@/components/permission-guard'

// Helper to format datetime
function formatDateTime(dateString: string): string {
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
function StatusBadge({ status }: { status: RunStatus }) {
  const statusConfig: Record<RunStatus, { icon: React.ReactNode; variant: 'default' | 'destructive' | 'secondary' | 'outline'; className?: string }> = {
    success: {
      icon: <CheckCircle className="h-3 w-3" />,
      variant: 'default',
      className: 'bg-green-500/10 text-green-700 dark:text-green-400 border-green-500/20',
    },
    failed: {
      icon: <XCircle className="h-3 w-3" />,
      variant: 'destructive',
    },
    running: {
      icon: <Loader className="h-3 w-3 animate-spin" />,
      variant: 'default',
      className: 'bg-blue-500/10 text-blue-700 dark:text-blue-400 border-blue-500/20',
    },
    pending: {
      icon: <Clock className="h-3 w-3" />,
      variant: 'secondary',
    },
    cancelled: {
      icon: <Ban className="h-3 w-3" />,
      variant: 'outline',
      className: 'bg-yellow-500/10 text-yellow-700 dark:text-yellow-400 border-yellow-500/20',
    },
    timeout: {
      icon: <AlertTriangle className="h-3 w-3" />,
      variant: 'outline',
      className: 'bg-orange-500/10 text-orange-700 dark:text-orange-400 border-orange-500/20',
    },
  }

  const config = statusConfig[status]

  return (
    <Badge variant={config.variant} className={config.className}>
      <span className="flex items-center gap-1">
        {config.icon}
        {status}
      </span>
    </Badge>
  )
}

export function WorkflowRunsTable() {
  const t = useTranslations('activities')
  const commonT = useTranslations('common')
  const { canPerform } = useCanPerform()
  const canDeleteWorkflowRun = canPerform('workflow:delete')

  // State
  const [runs, setRuns] = React.useState<WorkflowRunListItemWithWorkflow[]>([])
  const [total, setTotal] = React.useState(0)
  const [page, setPage] = React.useState(1)
  const [pageSize, setPageSize] = React.useState(20)
  const [loading, setLoading] = React.useState(true)
  const [selectedIds, setSelectedIds] = React.useState<Set<string>>(new Set())
  const [deleteDialogOpen, setDeleteDialogOpen] = React.useState(false)
  const [deletingIds, setDeletingIds] = React.useState<string[]>([])
  const [drawerOpen, setDrawerOpen] = React.useState(false)
  const [selectedRunId, setSelectedRunId] = React.useState<string | null>(null)

  // Filters
  const [search, setSearch] = React.useState('')
  const [teamFilter, setTeamFilter] = React.useState<string[]>([])
  const [workflowFilter, setWorkflowFilter] = React.useState<string[]>([])
  const [statusFilter, setStatusFilter] = React.useState<string[]>([])
  const [triggerTypeFilter, setTriggerTypeFilter] = React.useState<string[]>([])
  const [userFilter, setUserFilter] = React.useState<string[]>([])

  // Filter options
  const [teams, setTeams] = React.useState<Team[]>([])
  const [workflows, setWorkflows] = React.useState<WorkflowListItem[]>([])
  const [users, setUsers] = React.useState<User[]>([])

  // Load filter options
  React.useEffect(() => {
    const loadOptions = async () => {
      try {
        const [teamsData, workflowsData, usersData] = await Promise.all([
          teamsApi.getTeams(1, 100),
          workflowsApi.getWorkflows({ page: 1, pageSize: 100 }),
          usersApi.getUsers({ page: 1, pageSize: 100 }),
        ])
        setTeams(teamsData.items)
        setWorkflows(workflowsData.items)
        setUsers(usersData.items)
      } catch (error) {
        console.error('Failed to load filter options:', error)
      }
    }

    loadOptions()
  }, [])

  // Load workflow runs
  const loadRuns = React.useCallback(async () => {
    try {
      setLoading(true)
      const params = {
        page,
        pageSize,
        search: search || undefined,
        teamId: teamFilter.length > 0 ? teamFilter : undefined,
        workflowId: workflowFilter.length > 0 ? workflowFilter : undefined,
        status: statusFilter.length > 0 ? (statusFilter as RunStatus[]) : undefined,
        triggerType: triggerTypeFilter.length > 0 ? (triggerTypeFilter as TriggerType[]) : undefined,
        userId: userFilter.length > 0 ? userFilter : undefined,
      }
      console.log('Loading workflow runs with params:', params)
      const data = await workflowsApi.getAllWorkflowRuns(params)
      console.log('Workflow runs loaded successfully:', data)
      setRuns(data.items)
      setTotal(data.total)
    } catch (error: unknown) {
      console.error('Failed to load workflow runs:', error)
      const err = error as { response?: { data?: unknown } }
      console.error('Error details:', err.response?.data)
    } finally {
      setLoading(false)
    }
  }, [page, pageSize, search, teamFilter, workflowFilter, statusFilter, triggerTypeFilter, userFilter])

  React.useEffect(() => {
    loadRuns()
  }, [loadRuns])

  // Selection handlers
  const toggleSelectAll = () => {
    if (selectedIds.size === runs.length) {
      setSelectedIds(new Set())
    } else {
      setSelectedIds(new Set(runs.map((r) => r.id)))
    }
  }

  const toggleSelect = (id: string) => {
    const newSelected = new Set(selectedIds)
    if (newSelected.has(id)) {
      newSelected.delete(id)
    } else {
      newSelected.add(id)
    }
    setSelectedIds(newSelected)
  }

  // Delete handlers
  const handleDeleteClick = (ids: string[]) => {
    setDeletingIds(ids)
    setDeleteDialogOpen(true)
  }

  const handleDeleteConfirm = async () => {
    try {
      await Promise.all(deletingIds.map((id) => workflowsApi.deleteWorkflowRun(id)))
      toast.success(t('runDetail.deleteSuccess'))
      setSelectedIds(new Set())
      loadRuns()
    } catch (error) {
      console.error('Failed to delete runs:', error)
    } finally {
      setDeleteDialogOpen(false)
      setDeletingIds([])
    }
  }

  // View run
  const handleViewRun = (id: string) => {
    setSelectedRunId(id)
    setDrawerOpen(true)
  }

  // Reset filters
  const resetFilters = () => {
    setSearch('')
    setTeamFilter([])
    setWorkflowFilter([])
    setStatusFilter([])
    setTriggerTypeFilter([])
    setUserFilter([])
    setPage(1)
  }

  const hasFilters =
    search ||
    teamFilter.length > 0 ||
    workflowFilter.length > 0 ||
    statusFilter.length > 0 ||
    triggerTypeFilter.length > 0 ||
    userFilter.length > 0

  const totalPages = Math.ceil(total / pageSize)

  const statusOptions = [
    { label: t('status.success'), value: 'success' },
    { label: t('status.failed'), value: 'failed' },
    { label: t('status.running'), value: 'running' },
    { label: t('status.pending'), value: 'pending' },
    { label: t('status.cancelled'), value: 'cancelled' },
    { label: t('status.timeout'), value: 'timeout' },
  ]

  const triggerTypeOptions = [
    { label: t('triggerType.manual'), value: 'manual' },
    { label: t('triggerType.webhook'), value: 'webhook' },
    { label: t('triggerType.cron'), value: 'cron' },
  ]

  return (
    <>
      <div className="space-y-4">
        {/* Filters */}
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex flex-1 items-center gap-2 flex-wrap">
            <div className="relative flex-1 max-w-sm">
              <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder={t('filters.workflow')}
                value={search}
                onChange={(e) => {
                  setSearch(e.target.value)
                  setPage(1)
                }}
                className="pl-8"
              />
            </div>

            {teams.length > 0 && (
              <DataTableFacetedFilter
                title={commonT('team')}
                options={teams.map((team) => ({ label: team.name, value: team.id }))}
                selectedValues={new Set(teamFilter)}
                onSelectionChange={(values) => {
                  setTeamFilter(Array.from(values))
                  setPage(1)
                }}
                searchable
              />
            )}

            {workflows.length > 0 && (
              <DataTableFacetedFilter
                title={t('filters.workflow')}
                options={workflows.map((wf) => ({ label: wf.name, value: wf.id }))}
                selectedValues={new Set(workflowFilter)}
                onSelectionChange={(values) => {
                  setWorkflowFilter(Array.from(values))
                  setPage(1)
                }}
                searchable
              />
            )}

            <DataTableFacetedFilter
              title={t('filters.status')}
              options={statusOptions}
              selectedValues={new Set(statusFilter)}
              onSelectionChange={(values) => {
                setStatusFilter(Array.from(values))
                setPage(1)
              }}
            />

            <DataTableFacetedFilter
              title={t('filters.triggerType')}
              options={triggerTypeOptions}
              selectedValues={new Set(triggerTypeFilter)}
              onSelectionChange={(values) => {
                setTriggerTypeFilter(Array.from(values))
                setPage(1)
              }}
            />

            {users.length > 0 && (
              <DataTableFacetedFilter
                title={t('filters.triggeredBy')}
                options={users.map((user) => ({ label: user.username, value: user.id }))}
                selectedValues={new Set(userFilter)}
                onSelectionChange={(values) => {
                  setUserFilter(Array.from(values))
                  setPage(1)
                }}
                searchable
              />
            )}

            {hasFilters && (
              <Button variant="ghost" onClick={resetFilters} className="h-8 px-2 lg:px-3">
                {commonT('reset')}
                <X className="ml-2 h-4 w-4" />
              </Button>
            )}
          </div>

          {selectedIds.size > 0 && canDeleteWorkflowRun && (
            <Button
              variant="destructive"
              size="sm"
              onClick={() => handleDeleteClick(Array.from(selectedIds))}
            >
              <Trash2 className="mr-2 h-4 w-4" />
              {t('runDetail.deleteSelected', { count: selectedIds.size })}
            </Button>
          )}
        </div>

        {/* Table */}
        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-12">
                  <Checkbox
                    checked={runs.length > 0 && selectedIds.size === runs.length}
                    onCheckedChange={toggleSelectAll}
                  />
                </TableHead>
                <TableHead>{t('table.runId')}</TableHead>
                <TableHead>{t('table.workflow')}</TableHead>
                <TableHead>{t('table.status')}</TableHead>
                <TableHead>{t('table.triggerType')}</TableHead>
                <TableHead>{t('table.triggeredBy')}</TableHead>
                <TableHead>{t('table.duration')}</TableHead>
                <TableHead>{t('table.createdAt')}</TableHead>
                <TableHead className="w-12"></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading ? (
                <TableRow>
                  <TableCell colSpan={9} className="text-center py-8">
                    {commonT('loading')}
                  </TableCell>
                </TableRow>
              ) : runs.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={9} className="text-center py-8 text-muted-foreground">
                    {t('noData')}
                  </TableCell>
                </TableRow>
              ) : (
                runs.map((run) => (
                  <TableRow
                    key={run.id}
                    className="cursor-pointer hover:bg-muted/50"
                    onClick={() => handleViewRun(run.id)}
                  >
                    <TableCell onClick={(e) => e.stopPropagation()}>
                      <Checkbox
                        checked={selectedIds.has(run.id)}
                        onCheckedChange={() => toggleSelect(run.id)}
                      />
                    </TableCell>
                    <TableCell>
                      <code className="text-xs">{run.id.slice(0, 8)}</code>
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <Workflow className="h-4 w-4 text-muted-foreground" />
                        <span className="font-medium">{run.workflow_name}</span>
                      </div>
                    </TableCell>
                    <TableCell>
                      <StatusBadge status={run.status} />
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline">{run.trigger_type}</Badge>
                    </TableCell>
                    <TableCell>{run.triggered_by_name || '-'}</TableCell>
                    <TableCell>{formatDuration(run.total_duration_ms)}</TableCell>
                    <TableCell className="text-muted-foreground">
                      {formatDateTime(run.created_at)}
                    </TableCell>
                    <TableCell onClick={(e) => e.stopPropagation()}>
                      <DropdownMenu>
                        <DropdownMenuTrigger
                          render={
                            <Button variant="ghost" size="icon" className="h-8 w-8">
                              <MoreHorizontal className="h-4 w-4" />
                            </Button>
                          }
                        />
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem onClick={() => handleViewRun(run.id)}>
                            {t('runDetail.viewDetails')}
                          </DropdownMenuItem>
                          {canDeleteWorkflowRun && (
                            <DropdownMenuItem
                              variant="destructive"
                              onClick={() => handleDeleteClick([run.id])}
                            >
                              <Trash2 className="mr-2 h-4 w-4" />
                              {commonT('delete')}
                            </DropdownMenuItem>
                          )}
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </div>

        {/* Pagination */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Select value={String(pageSize)} onValueChange={(v) => { setPageSize(Number(v)); setPage(1) }}>
              <SelectTrigger size="sm" className="w-18">
                <SelectValue />
              </SelectTrigger>
              <SelectContent side="top" alignItemWithTrigger={false}>
                <SelectItem value="10">10</SelectItem>
                <SelectItem value="20">20</SelectItem>
                <SelectItem value="50">50</SelectItem>
                <SelectItem value="100">100</SelectItem>
              </SelectContent>
            </Select>
            <span>{t('rowsPerPage')}</span>
          </div>

          <div className="flex items-center gap-2">
            <span className="text-sm text-muted-foreground">
              {t('pageInfo', { page, total: totalPages || 1 })}
            </span>

            <div className="flex items-center gap-1">
              <Button
                variant="outline"
                size="icon"
                className="h-8 w-8"
                onClick={() => setPage(1)}
                disabled={page === 1}
              >
                <ChevronsLeft className="h-4 w-4" />
              </Button>
              <Button
                variant="outline"
                size="icon"
                className="h-8 w-8"
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1}
              >
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <Button
                variant="outline"
                size="icon"
                className="h-8 w-8"
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page >= totalPages}
              >
                <ChevronRight className="h-4 w-4" />
              </Button>
              <Button
                variant="outline"
                size="icon"
                className="h-8 w-8"
                onClick={() => setPage(totalPages)}
                disabled={page >= totalPages}
              >
                <ChevronsRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </div>
      </div>

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
            <AlertDialogAction variant="destructive" onClick={handleDeleteConfirm}>
              {commonT('delete')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Run Details Drawer */}
      {selectedRunId && (
        <WorkflowRunDrawer
          runId={selectedRunId}
          open={drawerOpen}
          onOpenChange={setDrawerOpen}
          onDelete={() => {
            loadRuns()
            setDrawerOpen(false)
          }}
        />
      )}
    </>
  )
}
