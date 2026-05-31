'use client'

import Image from 'next/image'
import Link from 'next/link'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useTranslations } from 'next-intl'
import { Copy, Download, FileEdit, Loader2, MoreHorizontal, RefreshCw, Search, Send, Trash2, X } from 'lucide-react'
import { toast } from 'sonner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { DataTableFacetedFilter } from '@/components/ui/data-table-faceted-filter'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
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
import { PermissionGuard } from '@/components/permission-guard'
import { Checkbox } from '@/components/ui/checkbox'
import { ApiError, type PageData } from '@/lib/api'
import { adminAgentsApi, type AdminAgent } from '@/lib/api/admin'
import { adminPackagesApi, downloadBlob } from '@/lib/api/packages'
import { useUrlSearchState } from '@/hooks/use-url-search-state'

function getErrorMessage(error: unknown) {
  if (error instanceof ApiError) return error.message
  if (error instanceof Error) return error.message
  return 'Unknown error'
}

function formatDate(value: string) {
  return new Date(value).toLocaleString()
}

function AppIcon({ icon, name }: { icon?: string | null; name: string }) {
  if (!icon) return null
  if (icon.startsWith('http')) {
    return (
      <div className="relative h-6 w-6 shrink-0 overflow-hidden rounded">
        <Image src={icon} alt={name} fill className="object-cover" unoptimized />
      </div>
    )
  }
  return <span className="shrink-0 text-lg">{icon}</span>
}

export function AdminAgentsPanel() {
  const t = useTranslations('apps.admin')
  const tCommon = useTranslations('common')
  const [agents, setAgents] = useState<AdminAgent[]>([])
  const [statusOptions, setStatusOptions] = useState<Array<{ value: string; label: string }>>([])
  const [visibilityOptions, setVisibilityOptions] = useState<Array<{ value: string; label: string }>>([])
  const [teamOptions, setTeamOptions] = useState<Array<{ value: string; label: string }>>([])
  const [creatorOptions, setCreatorOptions] = useState<Array<{ value: string; label: string }>>([])
  const [loading, setLoading] = useState(true)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(10)
  const [pageData, setPageData] = useState<PageData<AdminAgent> | null>(null)
  const [searchQuery, setSearchQuery] = useUrlSearchState()
  const [statusFilter, setStatusFilter] = useState<Set<string>>(new Set())
  const [visibilityFilter, setVisibilityFilter] = useState<Set<string>>(new Set())
  const [teamFilter, setTeamFilter] = useState<Set<string>>(new Set())
  const [creatorFilter, setCreatorFilter] = useState<Set<string>>(new Set())
  const [selectedAgents, setSelectedAgents] = useState<Set<string>>(new Set())

  const selectedStatuses = useMemo(() => Array.from(statusFilter), [statusFilter])
  const selectedVisibilities = useMemo(() => Array.from(visibilityFilter), [visibilityFilter])
  const selectedTeams = useMemo(() => Array.from(teamFilter), [teamFilter])
  const selectedCreators = useMemo(() => Array.from(creatorFilter), [creatorFilter])

  const loadAgents = useCallback(async () => {
    setLoading(true)
    try {
      const [agentsData, filterOptions] = await Promise.all([
        adminAgentsApi.listPage({
          page,
          pageSize,
          search: searchQuery || undefined,
          status: selectedStatuses.length > 0 ? selectedStatuses as AdminAgent['status'][] : undefined,
          visibility: selectedVisibilities.length > 0 ? selectedVisibilities as AdminAgent['visibility'][] : undefined,
          team_id: selectedTeams.length > 0 ? selectedTeams : undefined,
          creator: selectedCreators.length > 0 ? selectedCreators : undefined,
        }),
        adminAgentsApi.getFilterOptions(),
      ])
      setAgents(agentsData.items)
      setSelectedAgents(new Set())
      setPageData(agentsData)
      setStatusOptions(filterOptions.statuses.map((option) => ({ value: option.value, label: t(`status.${option.value}`) })))
      setVisibilityOptions(filterOptions.visibilities.map((option) => ({ value: option.value, label: t(`visibility.${option.value}`) })))
      setTeamOptions(filterOptions.teams)
      setCreatorOptions(filterOptions.creators)
    } catch (error) {
      toast.error(getErrorMessage(error))
    } finally {
      setLoading(false)
    }
  }, [page, pageSize, searchQuery, selectedStatuses, selectedVisibilities, selectedTeams, selectedCreators, t])

  useEffect(() => {
    loadAgents()
  }, [loadAgents])

  const totalPages = pageData ? Math.max(1, Math.ceil(pageData.total / pageSize)) : 1
  const isFiltered = Boolean(searchQuery) || statusFilter.size > 0 || visibilityFilter.size > 0 || teamFilter.size > 0 || creatorFilter.size > 0
  const allCurrentPageSelected = agents.length > 0 && agents.every((agent) => selectedAgents.has(agent.id))
  const selectedAgentItems = agents.filter((agent) => selectedAgents.has(agent.id))

  const toggleSelectAgent = (agentId: string) => {
    setSelectedAgents((current) => {
      const next = new Set(current)
      if (next.has(agentId)) next.delete(agentId)
      else next.add(agentId)
      return next
    })
  }

  const toggleSelectAll = () => {
    setSelectedAgents((current) => {
      if (allCurrentPageSelected) return new Set()
      const next = new Set(current)
      agents.forEach((agent) => next.add(agent.id))
      return next
    })
  }

  const resetFilters = () => {
    setSearchQuery('')
    setStatusFilter(new Set())
    setVisibilityFilter(new Set())
    setTeamFilter(new Set())
    setCreatorFilter(new Set())
    setPage(1)
  }

  const runAction = async (action: () => Promise<unknown>, successKey: string) => {
    try {
      await action()
      toast.success(t(successKey))
      await loadAgents()
    } catch (error) {
      toast.error(getErrorMessage(error))
    }
  }

  const handleExport = async (agent: AdminAgent) => {
    try {
      const { blob, filename } = await adminPackagesApi.export('agent', agent.id)
      downloadBlob(blob, filename)
    } catch (error) {
      toast.error(getErrorMessage(error))
    }
  }

  const handleBulkDelete = async () => {
    if (selectedAgentItems.length === 0) return
    if (!window.confirm(t('agents.bulkDeleteConfirm', { count: selectedAgentItems.length }))) return
    await runAction(
      () => Promise.all(selectedAgentItems.map((agent) => adminAgentsApi.delete(agent.id))),
      'actions.deleted'
    )
  }

  const handleBulkPublish = async (publish: boolean) => {
    if (selectedAgentItems.length === 0) return
    await runAction(
      () => Promise.all(selectedAgentItems.map((agent) => publish ? adminAgentsApi.publish(agent.id) : adminAgentsApi.unpublish(agent.id))),
      publish ? 'actions.published' : 'actions.unpublished'
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold tracking-tight">{t('agents.title')}</h2>
          <p className="mt-1 text-sm text-muted-foreground">{t('agents.description')}</p>
        </div>
        <Button variant="outline" size="sm" onClick={loadAgents} disabled={loading}>
          <RefreshCw className={`mr-2 h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
          {t('actions.refresh')}
        </Button>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder={t('agents.searchPlaceholder')}
            value={searchQuery}
            onChange={(event) => {
              setSearchQuery(event.target.value)
              setPage(1)
            }}
            className="h-9 w-56 pl-8"
          />
        </div>
        <DataTableFacetedFilter title={tCommon('status')} options={statusOptions} selectedValues={statusFilter} onSelectionChange={(values) => { setStatusFilter(values); setPage(1) }} />
        <DataTableFacetedFilter title={t('columns.visibility')} options={visibilityOptions} selectedValues={visibilityFilter} onSelectionChange={(values) => { setVisibilityFilter(values); setPage(1) }} />
        <DataTableFacetedFilter title={t('columns.team')} options={teamOptions} selectedValues={teamFilter} onSelectionChange={(values) => { setTeamFilter(values); setPage(1) }} />
        <DataTableFacetedFilter title={t('columns.creator')} options={creatorOptions} selectedValues={creatorFilter} onSelectionChange={(values) => { setCreatorFilter(values); setPage(1) }} />
        {isFiltered && (
          <Button variant="ghost" size="sm" onClick={resetFilters} className="h-9 px-2">
            <X className="mr-2 h-4 w-4" />
            {t('actions.reset')}
          </Button>
        )}
      </div>

      <div className="rounded-lg border">
        <Table>
          <TableHeader>
            <TableRow className="bg-muted/50 hover:bg-muted/50">
              <TableHead className="w-12">
                <Checkbox checked={allCurrentPageSelected} onCheckedChange={toggleSelectAll} />
              </TableHead>
              <TableHead>{t('columns.name')}</TableHead>
              <TableHead>{tCommon('status')}</TableHead>
              <TableHead>{t('columns.visibility')}</TableHead>
              <TableHead>{t('columns.team')}</TableHead>
              <TableHead>{t('columns.creator')}</TableHead>
              <TableHead>{t('columns.stats')}</TableHead>
              <TableHead>{t('columns.updatedAt')}</TableHead>
              <TableHead className="w-12" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? (
              <TableRow>
                <TableCell colSpan={9} className="h-24 text-center">
                  <Loader2 className="mx-auto h-5 w-5 animate-spin text-muted-foreground" />
                </TableCell>
              </TableRow>
            ) : agents.length === 0 ? (
              <TableRow>
                <TableCell colSpan={8} className="h-24 text-center text-muted-foreground">
                  {t('empty')}
                </TableCell>
              </TableRow>
            ) : agents.map((agent) => (
              <TableRow key={agent.id} data-state={selectedAgents.has(agent.id) ? 'selected' : undefined}>
                <TableCell>
                  <Checkbox checked={selectedAgents.has(agent.id)} onCheckedChange={() => toggleSelectAgent(agent.id)} />
                </TableCell>
                <TableCell>
                  <div className="flex max-w-72 items-center gap-2">
                    <AppIcon icon={agent.icon || agent.avatar_url} name={agent.name} />
                    <div className="min-w-0">
                      <div className="truncate font-medium">{agent.name}</div>
                    </div>
                  </div>
                </TableCell>
                <TableCell><Badge variant={agent.status === 'published' ? 'default' : 'secondary'}>{t(`status.${agent.status}`)}</Badge></TableCell>
                <TableCell><Badge variant="outline">{t(`visibility.${agent.visibility}`)}</Badge></TableCell>
                <TableCell>{agent.team?.name || '-'}</TableCell>
                <TableCell>{agent.created_by?.username || '-'}</TableCell>
                <TableCell className="text-sm text-muted-foreground">{t('agents.stats', { conversations: agent.conversation_count, messages: agent.message_count })}</TableCell>
                <TableCell className="text-sm text-muted-foreground">{formatDate(agent.updated_at)}</TableCell>
                <TableCell>
                  <DropdownMenu>
                    <DropdownMenuTrigger render={
                      <Button variant="ghost" size="icon" className="h-8 w-8">
                        <MoreHorizontal className="h-4 w-4" />
                      </Button>
                    } />
                    <DropdownMenuContent align="end">
                      <PermissionGuard permission="admin:app:update">
                        <Link href={`/apps/agents/${agent.id}/edit`}>
                          <DropdownMenuItem>
                            <FileEdit className="h-4 w-4" />
                            {t('actions.edit')}
                          </DropdownMenuItem>
                        </Link>
                      </PermissionGuard>
                      <PermissionGuard permission="admin:app:publish">
                        <DropdownMenuItem onClick={() => runAction(() => agent.status === 'published' ? adminAgentsApi.unpublish(agent.id) : adminAgentsApi.publish(agent.id), agent.status === 'published' ? 'actions.unpublished' : 'actions.published')}>
                          <Send className="h-4 w-4" />
                          {agent.status === 'published' ? t('actions.unpublish') : t('actions.publish')}
                        </DropdownMenuItem>
                      </PermissionGuard>
                      <PermissionGuard permission="admin:app:duplicate">
                        <DropdownMenuItem onClick={() => runAction(() => adminAgentsApi.duplicate(agent.id), 'actions.duplicated')}>
                          <Copy className="h-4 w-4" />
                          {t('actions.duplicate')}
                        </DropdownMenuItem>
                      </PermissionGuard>
                      <PermissionGuard permission="admin:app:read">
                        <DropdownMenuItem onClick={() => handleExport(agent)}>
                          <Download className="h-4 w-4" />
                          {t('actions.export')}
                        </DropdownMenuItem>
                      </PermissionGuard>
                      <PermissionGuard permission="admin:app:delete">
                        <DropdownMenuItem
                          variant="destructive"
                          onClick={() => {
                            if (window.confirm(t('agents.deleteConfirm', { name: agent.name }))) {
                              void runAction(() => adminAgentsApi.delete(agent.id), 'actions.deleted')
                            }
                          }}
                        >
                          <Trash2 className="h-4 w-4" />
                          {t('actions.delete')}
                        </DropdownMenuItem>
                      </PermissionGuard>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      <div className="flex items-center justify-between gap-4">
        <div className="text-sm text-muted-foreground">
          {pageData ? t('pagination.total', { total: pageData.total }) : null}
        </div>
        <div className="flex items-center gap-2">
          <Select value={String(pageSize)} onValueChange={(value) => { setPageSize(Number(value)); setPage(1) }}>
            <SelectTrigger className="h-8 w-24"><SelectValue /></SelectTrigger>
            <SelectContent>
              {[10, 20, 50].map((size) => <SelectItem key={size} value={String(size)}>{size}</SelectItem>)}
            </SelectContent>
          </Select>
          <Button variant="outline" size="sm" onClick={() => setPage((current) => Math.max(1, current - 1))} disabled={page <= 1}>{t('pagination.previous')}</Button>
          <span className="text-sm text-muted-foreground">{page} / {totalPages}</span>
          <Button variant="outline" size="sm" onClick={() => setPage((current) => Math.min(totalPages, current + 1))} disabled={page >= totalPages}>{t('pagination.next')}</Button>
        </div>
      </div>

      {selectedAgents.size > 0 && (
        <div className="fixed bottom-8 left-1/2 z-50 -translate-x-1/2">
          <div className="flex items-center gap-1 rounded-lg border bg-background px-2 py-1.5 shadow-lg">
            <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => setSelectedAgents(new Set())}>
              <X className="h-4 w-4" />
            </Button>
            <Badge variant="secondary" className="px-2 py-1">{t('bulk.selected', { count: selectedAgents.size })}</Badge>
            <PermissionGuard permission="admin:app:publish">
              <Tooltip>
                <TooltipTrigger render={<Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => handleBulkPublish(true)}><Send className="h-4 w-4" /></Button>} />
                <TooltipContent>{t('actions.publish')}</TooltipContent>
              </Tooltip>
              <Tooltip>
                <TooltipTrigger render={<Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => handleBulkPublish(false)}><X className="h-4 w-4" /></Button>} />
                <TooltipContent>{t('actions.unpublish')}</TooltipContent>
              </Tooltip>
            </PermissionGuard>
            <PermissionGuard permission="admin:app:delete">
              <Tooltip>
                <TooltipTrigger render={<Button variant="ghost" size="icon" className="h-8 w-8 text-destructive hover:bg-destructive/10 hover:text-destructive" onClick={handleBulkDelete}><Trash2 className="h-4 w-4" /></Button>} />
                <TooltipContent>{t('actions.delete')}</TooltipContent>
              </Tooltip>
            </PermissionGuard>
          </div>
        </div>
      )}
    </div>
  )
}
