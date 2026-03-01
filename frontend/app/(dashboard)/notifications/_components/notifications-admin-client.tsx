'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { Plus, Trash2, ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight, Search, X, Mail, MessageSquare, CheckCircle2, XCircle, Loader2, Clock } from 'lucide-react'
import { notificationsApi, type NotificationItem } from '@/lib/api/admin/notifications'
import type { NotificationLevel, NotificationScope, NotificationDelivery } from '@/lib/api/notifications'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger } from '@/components/ui/alert-dialog'
import { Badge } from '@/components/ui/badge'
import { DataTableFacetedFilter } from '@/components/ui/data-table-faceted-filter'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { toast } from 'sonner'
import { CreateNotificationDialog } from './create-notification-dialog'
import { formatDateTime } from '@/lib/utils'

const LEVELS: NotificationLevel[] = ['low', 'medium', 'high']
const SCOPES: NotificationScope[] = ['global', 'team', 'user']

function DeliveryStatusIcon({ delivery }: { delivery: NotificationDelivery }) {
  const t = useTranslations('notifications')

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
    ? `${t(`deliveryStatus.${delivery.status}`)}: ${delivery.error_message}`
    : t(`deliveryStatus.${delivery.status}`)

  return (
    <Tooltip>
      <TooltipTrigger>
        <div className="inline-flex items-center gap-0.5 cursor-default">
          {channelIcon}
          {statusIcon}
        </div>
      </TooltipTrigger>
      <TooltipContent>
        <p>{t(`channel.${delivery.channel}`)}: {tooltipContent}</p>
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

  const [items, setItems] = React.useState<NotificationItem[]>([])
  const [isLoading, setIsLoading] = React.useState(true)
  const [page, setPage] = React.useState(1)
  const [pageSize, setPageSize] = React.useState(10)
  const [total, setTotal] = React.useState(0)
  const [createOpen, setCreateOpen] = React.useState(false)

  // Filter states
  const [searchQuery, setSearchQuery] = React.useState('')
  const [scopeFilter, setScopeFilter] = React.useState<Set<string>>(new Set())
  const [levelFilter, setLevelFilter] = React.useState<Set<string>>(new Set())

  const fetchList = React.useCallback(async () => {
    try {
      setIsLoading(true)
      const result = await notificationsApi.adminList({
        page,
        page_size: pageSize,
      })
      setItems(result.items)
      setTotal(result.total)
    } catch (error) {
      console.error('Failed to fetch notifications:', error)
    } finally {
      setIsLoading(false)
    }
  }, [page, pageSize])

  React.useEffect(() => {
    fetchList()
  }, [fetchList])

  // Filter notifications (client-side filtering on current page)
  const filteredItems = React.useMemo(() => {
    return items.filter(item => {
      // Search filter
      if (searchQuery) {
        const query = searchQuery.toLowerCase()
        if (!item.title.toLowerCase().includes(query) &&
            !item.content.toLowerCase().includes(query)) {
          return false
        }
      }

      // Scope filter
      if (scopeFilter.size > 0 && !scopeFilter.has(item.scope)) {
        return false
      }

      // Level filter
      if (levelFilter.size > 0 && !levelFilter.has(item.level)) {
        return false
      }

      return true
    })
  }, [items, searchQuery, scopeFilter, levelFilter])

  // Check if filters are active
  const isFiltered = searchQuery || scopeFilter.size > 0 || levelFilter.size > 0

  // Reset all filters
  const resetFilters = () => {
    setSearchQuery('')
    setScopeFilter(new Set())
    setLevelFilter(new Set())
  }

  // Scope options
  const scopeOptions = SCOPES.map(scope => ({
    value: scope,
    label: t(`scopeOptions.${scope}`),
  }))

  // Level options
  const levelOptions = LEVELS.map(level => ({
    value: level,
    label: t(`levelOptions.${level}`),
  }))

  // Calculate total pages based on server total
  const totalPages = Math.max(1, Math.ceil(total / pageSize))

  const handleDelete = async (id: string) => {
    try {
      await notificationsApi.adminDelete(id)
      toast.success(t('toast.deleted'))
      await fetchList()
    } catch (error) {
      console.error('Failed to delete notification:', error)
    }
  }

  const handleCreateSuccess = () => {
    setCreateOpen(false)
    fetchList()
  }

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
              <TableHead>{t('admin.createTitle')}</TableHead>
              <TableHead>{t('admin.createScope')}</TableHead>
              <TableHead>{t('admin.createLevel')}</TableHead>
              <TableHead>{t('deliveryStatus.title')}</TableHead>
              <TableHead>{t('createdAt')}</TableHead>
              <TableHead className="w-[50px]"></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableRow>
                <TableCell colSpan={6} className="h-24 text-center">
                  {tCommon('loading')}
                </TableCell>
              </TableRow>
            ) : filteredItems.length === 0 ? (
              <TableRow>
                <TableCell colSpan={6} className="h-24 text-center text-muted-foreground">
                  {t('empty')}
                </TableCell>
              </TableRow>
            ) : (
              filteredItems.map((item) => (
                <TableRow key={item.id}>
                  <TableCell className="max-w-[280px] truncate font-medium">
                    {item.title}
                  </TableCell>
                  <TableCell>
                    <Badge variant="secondary">{t(`scopeOptions.${item.scope}`)}</Badge>
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline">{t(`levelOptions.${item.level}`)}</Badge>
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
                  <TableCell>
                    <AlertDialog>
                      <AlertDialogTrigger render={<Button variant="ghost" size="icon" />}>
                        <Trash2 className="h-4 w-4" />
                      </AlertDialogTrigger>
                      <AlertDialogContent>
                        <AlertDialogHeader>
                          <AlertDialogTitle>{t('admin.confirmDeleteTitle')}</AlertDialogTitle>
                          <AlertDialogDescription>{t('admin.confirmDeleteDesc')}</AlertDialogDescription>
                        </AlertDialogHeader>
                        <AlertDialogFooter>
                          <AlertDialogCancel>{tCommon('cancel')}</AlertDialogCancel>
                          <AlertDialogAction onClick={() => handleDelete(item.id)}>
                            {t('admin.delete')}
                          </AlertDialogAction>
                        </AlertDialogFooter>
                      </AlertDialogContent>
                    </AlertDialog>
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
    </div>
  )
}
