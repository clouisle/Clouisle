'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { Check, ChevronLeft, ChevronRight, Megaphone, Search, ShieldAlert, Sparkles, X } from 'lucide-react'
import { notificationsApi, type NotificationItem, type NotificationLevel, type NotificationScope } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import { toast } from 'sonner'
import { Input } from '@/components/ui/input'
import { DataTableFacetedFilter } from '@/components/ui/data-table-faceted-filter'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import dynamic from 'next/dynamic'
import { useTheme } from 'next-themes'
import { useDebounce } from '@/hooks/use-debounce'
import { getNotificationDisplayMeta, type NotificationDisplayKind } from '@/lib/notifications/display'

const MDPreview = dynamic(() => import('@uiw/react-md-editor').then(mod => mod.default.Markdown), {
  ssr: false,
  loading: () => <NotificationMarkdownSkeleton />,
})

function preloadNotificationMarkdown() {
  if (typeof window !== 'undefined') {
    import('@uiw/react-md-editor').catch(() => {})
  }
}

function NotificationMarkdownSkeleton() {
  return (
    <div className="space-y-3" aria-hidden="true">
      <Skeleton className="h-5 w-1/3" />
      <div className="space-y-2">
        <Skeleton className="h-3 w-full" />
        <Skeleton className="h-3 w-5/6" />
        <Skeleton className="h-3 w-4/6" />
      </div>
      <Skeleton className="h-4 w-1/4" />
      <div className="space-y-2">
        <Skeleton className="h-3 w-full" />
        <Skeleton className="h-3 w-3/4" />
      </div>
    </div>
  )
}

const LEVELS: NotificationLevel[] = ['low', 'medium', 'high']
const SCOPES: NotificationScope[] = ['global', 'team', 'user']

const KIND_ICON: Record<NotificationDisplayKind, React.ComponentType<{ className?: string }>> = {
  announcement: Megaphone,
  security: ShieldAlert,
  action: Sparkles,
  delivery: Check,
  general: Sparkles,
}

function getRowClassName(item: NotificationItem) {
  const meta = getNotificationDisplayMeta(item)

  return cn(
    'cursor-pointer border-l-4 border-l-transparent',
    !item.is_read && 'bg-primary/5',
    meta.isAnnouncement && 'border-l-amber-500 bg-amber-500/10 hover:bg-amber-500/15 dark:bg-amber-500/15',
    meta.isAnnouncement && !item.is_read && 'bg-amber-500/15 hover:bg-amber-500/20 dark:bg-amber-500/20',
    meta.kind === 'security' && !meta.isAnnouncement && 'border-l-destructive bg-destructive/5',
    meta.kind === 'security' && !meta.isAnnouncement && !item.is_read && 'bg-destructive/10',
    meta.isProminent && 'shadow-sm',
  )
}

function NotificationKindBadge({ item, label }: { item: NotificationItem; label: string }) {
  const meta = getNotificationDisplayMeta(item)
  const Icon = KIND_ICON[meta.kind]

  return (
    <Badge variant={meta.isAnnouncement ? 'default' : 'secondary'} className="gap-1">
      <Icon className="size-3" />
      <span>{label}</span>
    </Badge>
  )
}

interface NotificationsClientProps {
  onReadUpdated?: () => void
}

export function NotificationsClient({ onReadUpdated }: NotificationsClientProps) {
  const t = useTranslations('notifications')
  const { resolvedTheme } = useTheme()

  const [items, setItems] = React.useState<NotificationItem[]>([])
  const [pinnedAnnouncements, setPinnedAnnouncements] = React.useState<NotificationItem[]>([])
  const [isLoading, setIsLoading] = React.useState(true)
  const [page, setPage] = React.useState(1)
  const [pageSize] = React.useState(20)
  const [total, setTotal] = React.useState(0)
  const [scopeFilter, setScopeFilter] = React.useState<Set<string>>(new Set())
  const [levelFilter, setLevelFilter] = React.useState<Set<string>>(new Set())
  const [searchQuery, setSearchQuery] = React.useState('')
  const debouncedSearchQuery = useDebounce(searchQuery.trim(), 300)
  const [readFilter, setReadFilter] = React.useState<Set<string>>(new Set())
  const [detailOpen, setDetailOpen] = React.useState(false)
  const [selectedItem, setSelectedItem] = React.useState<NotificationItem | null>(null)
  const [mounted, setMounted] = React.useState(false)

  React.useEffect(() => {
    setMounted(true)
    preloadNotificationMarkdown()
  }, [])

  const colorMode = mounted ? (resolvedTheme === 'dark' ? 'dark' : 'light') : 'light'

  const applySingleSelect = (values: Set<string>, setValues: (next: Set<string>) => void) => {
    if (values.size <= 1) {
      setValues(values)
      return
    }
    const lastValue = Array.from(values).pop()
    setValues(lastValue ? new Set([lastValue]) : new Set())
  }

  const fetchList = React.useCallback(async () => {
    try {
      setIsLoading(true)
      const scope = Array.from(scopeFilter)[0] as NotificationScope | undefined
      const level = Array.from(levelFilter)[0] as NotificationLevel | undefined
      const listParams = {
        page,
        page_size: pageSize,
        scope: scope || undefined,
        level: level || undefined,
        search: debouncedSearchQuery || undefined,
        unread_only: readFilter.has('unread'),
      }
      const result = await notificationsApi.list(listParams)
      const shouldPromoteAnnouncements = page === 1 && !scope && !level && !debouncedSearchQuery && !readFilter.has('unread')

      setItems(result.items)
      if (shouldPromoteAnnouncements) {
        const announcements = await notificationsApi.list({
          page: 1,
          page_size: 5,
          type: 'system_announcement',
        })
        const currentPageIds = new Set(result.items.map((item) => item.id))
        setPinnedAnnouncements(announcements.items.filter((item) => !currentPageIds.has(item.id)))
      } else {
        setPinnedAnnouncements([])
      }
      setTotal(result.total)
    } catch (error) {
      console.error('Failed to fetch notifications:', error)
    } finally {
      setIsLoading(false)
    }
  }, [page, pageSize, scopeFilter, levelFilter, readFilter, debouncedSearchQuery])

  React.useEffect(() => {
    fetchList()
  }, [fetchList])

  React.useEffect(() => {
    setPage(1)
  }, [scopeFilter, levelFilter, readFilter, debouncedSearchQuery])

  const handleMarkRead = async (id: string) => {
    try {
      await notificationsApi.markRead({ notification_ids: [id] })
      toast.success(t('toast.readUpdated'))
      onReadUpdated?.()
      await fetchList()
    } catch (error) {
      console.error('Failed to mark read:', error)
    }
  }

  const handleMarkAllRead = async () => {
    try {
      await notificationsApi.markRead({ mark_all: true })
      toast.success(t('toast.readUpdated'))
      onReadUpdated?.()
      await fetchList()
    } catch (error) {
      console.error('Failed to mark all read:', error)
    }
  }

  const totalPages = Math.max(1, Math.ceil(total / pageSize))
  const openDetail = (item: NotificationItem) => {
    setSelectedItem(item)
    setDetailOpen(true)
  }

  return (
    <div className="flex h-full flex-col gap-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">{t('title')}</h1>
          <p className="text-sm text-muted-foreground">{t('filters')}</p>
        </div>
        <Button onClick={handleMarkAllRead} className="cursor-pointer">
          <Check className="mr-2 size-4" />
          {t('markAllRead')}
        </Button>
      </div>

      <div className="flex flex-wrap items-center gap-4">
        <div className="relative w-72">
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder={t('searchPlaceholder')}
            className="pl-9 pr-9"
          />
          {searchQuery && (
            <button
              type="button"
              onClick={() => setSearchQuery('')}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground cursor-pointer"
            >
              <X className="size-4" />
            </button>
          )}
        </div>

        <DataTableFacetedFilter
          title={t('scope')}
          options={SCOPES.map((scope) => ({
            value: scope,
            label: t(`scopeOptions.${scope}`),
          }))}
          selectedValues={scopeFilter}
          onSelectionChange={(values) => applySingleSelect(values, setScopeFilter)}
        />

        <DataTableFacetedFilter
          title={t('level')}
          options={LEVELS.map((level) => ({
            value: level,
            label: t(`levelOptions.${level}`),
          }))}
          selectedValues={levelFilter}
          onSelectionChange={(values) => applySingleSelect(values, setLevelFilter)}
        />

        <DataTableFacetedFilter
          title={t('unreadOnly')}
          options={[
            { value: 'unread', label: t('unreadOnly') },
          ]}
          selectedValues={readFilter}
          onSelectionChange={(values) => applySingleSelect(values, setReadFilter)}
        />
      </div>

      {pinnedAnnouncements.length > 0 && (
        <div className="space-y-2 rounded-lg border border-amber-500/40 bg-amber-500/10 p-3">
          {pinnedAnnouncements.map((item) => {
            const meta = getNotificationDisplayMeta(item)
            return (
              <button
                key={item.id}
                type="button"
                className={cn(
                  'flex w-full cursor-pointer items-start justify-between gap-3 rounded-md px-3 py-2 text-left hover:bg-amber-500/10',
                  !item.is_read && 'bg-amber-500/15',
                )}
                onClick={() => openDetail(item)}
              >
                <div className="min-w-0 space-y-1">
                  <div className="flex min-w-0 items-center gap-2">
                    <NotificationKindBadge item={item} label={t(`kindOptions.${meta.kind}`)} />
                    {!item.is_read && <span className="inline-flex size-2 shrink-0 rounded-full bg-primary" />}
                    <span className="min-w-0 truncate text-sm font-semibold">{item.title}</span>
                  </div>
                  <p className="text-xs font-medium text-amber-700 dark:text-amber-300">{t('announcementHint')}</p>
                </div>
                {!item.is_read && (
                  <Button
                    variant="default"
                    size="sm"
                    className="shrink-0 cursor-pointer"
                    onClick={(event) => {
                      event.stopPropagation()
                      handleMarkRead(item.id)
                    }}
                  >
                    {t('markRead')}
                  </Button>
                )}
              </button>
            )
          })}
        </div>
      )}

      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t('admin.createTitle')}</TableHead>
              <TableHead>{t('scope')}</TableHead>
              <TableHead>{t('level')}</TableHead>
              <TableHead>{t('createdAt')}</TableHead>
              <TableHead className="text-right">{t('actions')}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              Array.from({ length: 6 }).map((_, index) => (
                <TableRow key={index}>
                  <TableCell colSpan={5}>
                    <Skeleton className="h-4 w-2/3" />
                  </TableCell>
                </TableRow>
              ))
            ) : items.length === 0 ? (
              <TableRow>
                <TableCell colSpan={5} className="text-center text-muted-foreground">
                  {t('empty')}
                </TableCell>
              </TableRow>
            ) : (
              items.map((item) => {
                const meta = getNotificationDisplayMeta(item)

                return (
                  <TableRow
                    key={item.id}
                    className={getRowClassName(item)}
                    onClick={() => openDetail(item)}
                  >
                    <TableCell className="max-w-[320px] min-w-0">
                      <div className="flex min-w-0 flex-col gap-1.5">
                        <div className="flex min-w-0 items-center gap-2">
                          <span className={cn('min-w-0 truncate font-medium', meta.isAnnouncement && 'font-semibold')}>{item.title}</span>
                          {!item.is_read && <span className="inline-flex size-2 shrink-0 rounded-full bg-primary" />}
                        </div>
                        <div className="flex flex-wrap items-center gap-1.5">
                          <NotificationKindBadge item={item} label={t(`kindOptions.${meta.kind}`)} />
                          {meta.isAnnouncement && (
                            <span className="text-xs font-medium text-amber-700 dark:text-amber-300">
                              {t('announcementHint')}
                            </span>
                          )}
                        </div>
                      </div>
                    </TableCell>
                    <TableCell>
                      <Badge variant="secondary">{t(`scopeOptions.${item.scope}`)}</Badge>
                    </TableCell>
                    <TableCell>
                      <Badge variant={meta.priorityScore >= 5 ? 'default' : 'outline'}>{t(`levelOptions.${item.level}`)}</Badge>
                    </TableCell>
                    <TableCell>{new Date(item.created_at).toLocaleString()}</TableCell>
                    <TableCell className="text-right">
                      {!item.is_read ? (
                        <Button
                          variant={meta.isAnnouncement ? 'default' : 'outline'}
                          size="sm"
                          className="cursor-pointer"
                          onClick={(event) => {
                            event.stopPropagation()
                            handleMarkRead(item.id)
                          }}
                        >
                          {t('markRead')}
                        </Button>
                      ) : null}
                    </TableCell>
                  </TableRow>
                )
              })
            )}
          </TableBody>
        </Table>
      </div>

      <div className="flex items-center justify-end gap-2">
        <Button
          variant="outline"
          size="sm"
          onClick={() => setPage((prev) => Math.max(1, prev - 1))}
          disabled={page <= 1}
          className="cursor-pointer"
        >
          <ChevronLeft className="size-4" />
        </Button>
        <span className="text-sm text-muted-foreground">{page} / {totalPages}</span>
        <Button
          variant="outline"
          size="sm"
          onClick={() => setPage((prev) => Math.min(totalPages, prev + 1))}
          disabled={page >= totalPages}
          className="cursor-pointer"
        >
          <ChevronRight className="size-4" />
        </Button>
      </div>

      <Dialog open={detailOpen} onOpenChange={setDetailOpen}>
        <DialogContent className="max-h-[80vh] overflow-hidden sm:max-w-xl">
          <DialogHeader>
            <DialogTitle>{selectedItem?.title || t('title')}</DialogTitle>
          </DialogHeader>
          {selectedItem && (() => {
            const meta = getNotificationDisplayMeta(selectedItem)

            return (
              <div className="flex min-h-[180px] max-h-[calc(80vh-8rem)] flex-col gap-4 overflow-hidden">
                <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                  <NotificationKindBadge item={selectedItem} label={t(`kindOptions.${meta.kind}`)} />
                  <Badge variant="secondary">{t(`scopeOptions.${selectedItem.scope}`)}</Badge>
                  <Badge variant={meta.priorityScore >= 5 ? 'default' : 'outline'}>{t(`levelOptions.${selectedItem.level}`)}</Badge>
                  <span className="mx-1 h-3 w-px bg-border/70" />
                  <span>{t('createdAt')}: {new Date(selectedItem.created_at).toLocaleString()}</span>
                </div>
                <div className={cn(
                  'min-h-0 flex-1 overflow-y-auto rounded-lg border bg-muted/30 p-6 text-sm text-foreground',
                  meta.isAnnouncement && 'border-amber-500/50 bg-amber-500/10',
                )} data-color-mode={colorMode}>
                  <div className="wmde-markdown">
                    <MDPreview source={selectedItem.content} />
                  </div>
                </div>
              </div>
            )
          })()}
        </DialogContent>
      </Dialog>
    </div>
  )
}
