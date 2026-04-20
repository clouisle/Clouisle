'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { Plus, Trash2, ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight, Search, X, Mail, MessageSquare, CheckCircle2, XCircle, Loader2, Clock, Eye, MoreHorizontal } from 'lucide-react'
import { notificationsApi, type NotificationItem } from '@/lib/api/admin/notifications'
import type { NotificationLevel, NotificationScope, NotificationDelivery } from '@/lib/api/notifications'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from '@/components/ui/alert-dialog'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { Badge } from '@/components/ui/badge'
import { DataTableFacetedFilter } from '@/components/ui/data-table-faceted-filter'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { Checkbox } from '@/components/ui/checkbox'
import { toast } from 'sonner'
import { CreateNotificationDialog } from './create-notification-dialog'
import { NotificationDetailDialog } from './notification-detail-dialog'
import { formatDateTime } from '@/lib/utils'

const LEVELS: NotificationLevel[] = ['low', 'medium', 'high']
const SCOPES: NotificationScope[] = ['global', 'team', 'user']

function DeliveryStatusIcon({ delivery }: { delivery: NotificationDelivery }) {
  const t = useTranslations('notifications')

  const getChannelLabel = (channel: string) => {
    const key = `channel.${channel}`
    return t.has(key) ? t(key) : channel
  }

  const getDeliveryStatusLabel = (status: string) => {
    const key = `deliveryStatus.${status}`
    return t.has(key) ? t(key) : status
  }

  const channelIcon = delivery.channel === 'email' ? (
    <Mail className="h-3.5 w-3.5" />
  ) : delivery.channel === 'dingtalk' ? (
    <MessageSquare className="h-3.5 w-3.5" />
  ) : null

  const statusIcon = delivery.status === 'success' ? (
    <CheckCircle2 className="h-3 w-3 text-green-500" />
  ) : delivery.status === 'failed' ? (
    <XCircle className="h-3 w-3 text-destructive" />
  ) : delivery.status === 'sending' ? (
    <Loader2 className="h-3 w-3 text-blue-500 animate-spin" />
  ) : (
    <Clock className="h-3 w-3 text-muted-foreground" />
  )

  const tooltipContent = delivery.error_message
    ? `${getDeliveryStatusLabel(delivery.status)}: ${delivery.error_message}`
    : getDeliveryStatusLabel(delivery.status)

  return (
    <Tooltip>
      <TooltipTrigger>
        <div className="inline-flex items-center gap-0.5 cursor-default">
          {channelIcon}
          {statusIcon}
        </div>
      </TooltipTrigger>
      <TooltipContent>
        <p>{getChannelLabel(delivery.channel)}: {tooltipContent}</p>
        {delivery.retry_count > 0 && (
          <p className="text-xs text-muted-foreground">
            {t('retryCount', { count: delivery.retry_count })}
          </p>
        )}
      </TooltipContent>
    </Tooltip>
  )
}

export function NotificationsAdminClient() {
  const t = useTranslations('notifications')
  const tCommon = useTranslations('common')

  const getScopeLabel = (scope: string) => {
    const key = `scopeOptions.${scope}`
    return t.has(key) ? t(key) : scope
  }

  const getLevelLabel = (level: string) => {
    const key = `levelOptions.${level}`
    return t.has(key) ? t(key) : level
  }

  const [items, setItems] = React.useState<NotificationItem[]>([])
  const [isLoading, setIsLoading] = React.useState(true)
  const [page, setPage] = React.useState(1)
  const [pageSize, setPageSize] = React.useState(10)
  const [total, setTotal] = React.useState(0)
  const [createOpen, setCreateOpen] = React.useState(false)
  const [detailOpen, setDetailOpen] = React.useState(false)
  const [selectedNotification, setSelectedNotification] = React.useState<NotificationItem | null>(null)
  const [selectedIds, setSelectedIds] = React.useState<Set<string>>(new Set())
  const [bulkDeleteDialogOpen, setBulkDeleteDialogOpen] = React.useState(false)
  const [deleteDialogOpen, setDeleteDialogOpen] = React.useState(false)
  const [deletingId, setDeletingId] = React.useState<string | null>(null)

  // Filter states
  const [searchQuery, setSearchQuery] = React.useState('')
  const [debouncedSearchQuery, setDebouncedSearchQuery] = React.useState('')
  const [scopeFilter, setScopeFilter] = React.useState<Set<string>>(new Set())
  const [levelFilter, setLevelFilter] = React.useState<Set<string>>(new Set())

  const fetchList = React.useCallback(async () => {
    try {
      setIsLoading(true)
      const result = await notificationsApi.adminList({
        page,
        page_size: pageSize,
        scope: scopeFilter.size > 0 ? Array.from(scopeFilter) as NotificationScope[] : undefined,
        level: levelFilter.size > 0 ? Array.from(levelFilter) as NotificationLevel[] : undefined,
        search: debouncedSearchQuery || undefined,
      })
      setItems(result.items)
      setTotal(result.total)
      setSelectedIds(new Set())
    } catch (error) {
      console.error('Failed to fetch notifications:', error)
    } finally {
      setIsLoading(false)
    }
  }, [page, pageSize, scopeFilter, levelFilter, debouncedSearchQuery])

  React.useEffect(() => {
    fetchList()
  }, [fetchList])

  React.useEffect(() => {
    setPage(1)
    setSelectedIds(new Set())
  }, [scopeFilter, levelFilter, debouncedSearchQuery])

  React.useEffect(() => {
    const timer = window.setTimeout(() => {
      setDebouncedSearchQuery(searchQuery.trim())
    }, 300)
    return () => window.clearTimeout(timer)
  }, [searchQuery])

  // Check if filters are active
  const isFiltered = searchQuery || scopeFilter.size > 0 || levelFilter.size > 0

  // Reset all filters
  const resetFilters = () => {
    setSearchQuery('')
    setDebouncedSearchQuery('')
    setScopeFilter(new Set())
    setLevelFilter(new Set())
    setPage(1)
    setSelectedIds(new Set())
  }

  // Scope options
  const scopeOptions = SCOPES.map(scope => ({
    value: scope,
    label: getScopeLabel(scope),
  }))

  // Level options
  const levelOptions = LEVELS.map(level => ({
    value: level,
    label: getLevelLabel(level),
  }))

  // Calculate total pages based on server total
  const totalPages = Math.max(1, Math.ceil(total / pageSize))

  const handleDelete = (id: string) => {
    setDeletingId(id)
    setDeleteDialogOpen(true)
  }

  const confirmDelete = async () => {
    if (!deletingId) return

    try {
      await notificationsApi.adminDelete(deletingId)
      toast.success(t('toast.deleted'))
      await fetchList()
    } catch (error) {
      console.error('Failed to delete notification:', error)
    } finally {
      setDeleteDialogOpen(false)
      setDeletingId(null)
    }
  }

  const handleBulkDelete = async () => {
    setBulkDeleteDialogOpen(true)
  }

  const confirmBulkDelete = async () => {
    if (selectedIds.size === 0) return

    try {
      await Promise.all(
        Array.from(selectedIds).map(id => notificationsApi.adminDelete(id))
      )
      toast.success(t('toast.bulkDeleted', { count: selectedIds.size }))
      setSelectedIds(new Set())
      await fetchList()
    } catch (error) {
      console.error('Failed to bulk delete notifications:', error)
    } finally {
      setBulkDeleteDialogOpen(false)
    }
  }

  const handleViewDetail = (notification: NotificationItem) => {
    setSelectedNotification(notification)
    setDetailOpen(true)
  }

  const handleRowClick = (notification: NotificationItem, e: React.MouseEvent) => {
    // 如果点击的是复选框或操作按钮，不触发行点击
    const target = e.target as HTMLElement
    if (target.closest('input[type="checkbox"]') || target.closest('button') || target.closest('[role="button"]')) {
      return
    }
    handleViewDetail(notification)
  }

  const handleCreateSuccess = () => {
    setCreateOpen(false)
    fetchList()
  }

  const handleSelectAll = (checked: boolean) => {
    if (checked) {
      setSelectedIds(new Set(items.map(item => item.id)))
    } else {
      setSelectedIds(new Set())
    }
  }

  const handleSelectOne = (id: string, checked: boolean) => {
    const newSelected = new Set(selectedIds)
    if (checked) {
      newSelected.add(id)
    } else {
      newSelected.delete(id)
    }
    setSelectedIds(newSelected)
  }

  const isAllSelected = items.length > 0 && selectedIds.size === items.length
  const isSomeSelected = selectedIds.size > 0 && selectedIds.size < items.length

  return (
    <div className="flex flex-col gap-6">
      {/* Page Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold">{t('admin.title')}</h1>
          <p className="text-muted-foreground">{t('description')}</p>
        </div>
        <div className="flex items-center gap-2">
          <Button onClick={() => setCreateOpen(true)}>
            <Plus className="mr-2 h-4 w-4" />
            {t('admin.create')}
          </Button>
        </div>
      </div>

      {/* Filters */}
      <div className="flex items-center justify-between gap-4">
        <div className="flex flex-1 items-center gap-2">
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              placeholder={t('searchPlaceholder')}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-8 w-[200px] h-9"
            />
          </div>

          <DataTableFacetedFilter
            title={t('scope')}
            options={scopeOptions}
            selectedValues={scopeFilter}
            onSelectionChange={setScopeFilter}
          />

          <DataTableFacetedFilter
            title={t('level')}
            options={levelOptions}
            selectedValues={levelFilter}
            onSelectionChange={setLevelFilter}
          />

          {isFiltered && (
            <Button
              variant="ghost"
              onClick={resetFilters}
              className="h-9 px-2 lg:px-3"
            >
              {tCommon('reset')}
              <X className="ml-2 h-4 w-4" />
            </Button>
          )}
        </div>
      </div>

      {/* Table */}
      <div className="rounded-lg border">
        <Table>
          <TableHeader>
            <TableRow className="bg-muted/50 hover:bg-muted/50">
              <TableHead className="w-[40px]">
                <Checkbox
                  checked={isAllSelected}
                  indeterminate={isSomeSelected}
                  onCheckedChange={handleSelectAll}
                />
              </TableHead>
              <TableHead>{t('admin.createTitle')}</TableHead>
              <TableHead>{t('admin.createScope')}</TableHead>
              <TableHead>{t('admin.createLevel')}</TableHead>
              <TableHead>{t('deliveryStatus.title')}</TableHead>
              <TableHead>{t('createdAt')}</TableHead>
              <TableHead className="w-[100px]"></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableRow>
                <TableCell colSpan={7} className="h-24 text-center">
                  {tCommon('loading')}
                </TableCell>
              </TableRow>
            ) : items.length === 0 ? (
              <TableRow>
                <TableCell colSpan={7} className="h-24 text-center text-muted-foreground">
                  {t('empty')}
                </TableCell>
              </TableRow>
            ) : (
              items.map((item) => (
                <TableRow
                  key={item.id}
                  data-state={selectedIds.has(item.id) ? 'selected' : undefined}
                  onClick={(e) => handleRowClick(item, e)}
                  className="cursor-pointer"
                >
                  <TableCell onClick={(e) => e.stopPropagation()}>
                    <Checkbox
                      checked={selectedIds.has(item.id)}
                      onCheckedChange={(checked) => handleSelectOne(item.id, checked as boolean)}
                    />
                  </TableCell>
                  <TableCell className="font-medium">
                    <div className="max-w-[280px] truncate">
                      {item.title}
                    </div>
                  </TableCell>
                  <TableCell>
                    <Badge variant="secondary">{getScopeLabel(item.scope)}</Badge>
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline">{getLevelLabel(item.level)}</Badge>
                  </TableCell>
                  <TableCell>
                    {item.deliveries && item.deliveries.length > 0 ? (
                      <div className="flex items-center gap-2">
                        {item.deliveries.map((delivery, idx) => (
                          <DeliveryStatusIcon key={idx} delivery={delivery} />
                        ))}
                      </div>
                    ) : (
                      <span className="text-muted-foreground text-sm">-</span>
                    )}
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {formatDateTime(item.created_at)}
                  </TableCell>
                  <TableCell onClick={(e) => e.stopPropagation()}>
                    <DropdownMenu>
                      <DropdownMenuTrigger render={<Button variant="ghost" size="icon" className="h-8 w-8" />}>
                        <MoreHorizontal className="h-4 w-4" />
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem onClick={() => handleViewDetail(item)}>
                          <Eye className="mr-2 h-4 w-4" />
                          {t('admin.detail')}
                        </DropdownMenuItem>
                        <DropdownMenuItem
                          variant="destructive"
                          onClick={() => handleDelete(item.id)}
                        >
                          <Trash2 className="mr-2 h-4 w-4" />
                          {tCommon('delete')}
                        </DropdownMenuItem>
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
            <SelectTrigger size="sm" className="w-[70px]">
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
            {t('pageInfo', { page, total: totalPages })}
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
              onClick={() => setPage(p => Math.max(1, p - 1))}
              disabled={page === 1}
            >
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <Button
              variant="outline"
              size="icon"
              className="h-8 w-8"
              onClick={() => setPage(p => Math.min(totalPages, p + 1))}
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

      {/* Create Dialog */}
      <CreateNotificationDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        onSuccess={handleCreateSuccess}
      />

      {/* Detail Dialog */}
      <NotificationDetailDialog
        notification={selectedNotification}
        open={detailOpen}
        onOpenChange={setDetailOpen}
      />

      {/* Bulk Actions Floating Bar */}
      {selectedIds.size > 0 && (
        <div className="fixed bottom-8 left-1/2 -translate-x-1/2 z-50">
          <div className="flex items-center gap-1 rounded-lg border bg-background px-2 py-1.5 shadow-lg">
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              onClick={() => setSelectedIds(new Set())}
            >
              <X className="h-4 w-4" />
            </Button>

            <Badge variant="secondary" className="px-2 py-1">
              {t('admin.selectedCount', { count: selectedIds.size })}
            </Badge>

            <Tooltip>
              <TooltipTrigger
                onClick={handleBulkDelete}
                render={
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8 text-destructive hover:text-destructive hover:bg-destructive/10"
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                }
              />
              <TooltipContent>{tCommon('delete')}</TooltipContent>
            </Tooltip>
          </div>
        </div>
      )}

      {/* Delete Confirmation Dialog */}
      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{tCommon('confirmDelete')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('admin.confirmDeleteDesc')}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{tCommon('cancel')}</AlertDialogCancel>
            <AlertDialogAction variant="destructive" onClick={confirmDelete}>
              {tCommon('delete')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Bulk Delete Confirmation Dialog */}
      <AlertDialog open={bulkDeleteDialogOpen} onOpenChange={setBulkDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('admin.confirmBulkDeleteTitle')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('admin.confirmBulkDeleteDesc', { count: selectedIds.size })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{tCommon('cancel')}</AlertDialogCancel>
            <AlertDialogAction variant="destructive" onClick={confirmBulkDelete}>
              {t('admin.delete')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
