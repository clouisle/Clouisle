'use client'

import * as React from 'react'
import { useLocale, useTranslations } from 'next-intl'
import { Check, Loader2, Megaphone, Search, ShieldAlert, Sparkles, X } from 'lucide-react'
import { notificationsApi, type NotificationItem, type NotificationLevel, type NotificationScope } from '@/lib/api'
import { PauseRequestActions } from '@/components/chat/pause-request-actions'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { cn, formatDateTime } from '@/lib/utils'
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
import { useInfiniteScroll } from '@/hooks/use-infinite-scroll'
import { getNotificationDisplayMeta, getPauseActionMeta, type NotificationDisplayKind } from '@/lib/notifications/display'

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
const PAGE_SIZE = 20

type NotificationLoadOperation = 'first' | 'more' | 'refresh'

const KIND_ICON: Record<NotificationDisplayKind, React.ComponentType<{ className?: string }>> = {
  announcement: Megaphone,
  security: ShieldAlert,
  action: Sparkles,
  delivery: Check,
  general: Sparkles,
}

function getRowClassName(item: NotificationItem) {
  return cn(!item.is_read && 'bg-primary/5')
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
  const commonT = useTranslations('common')
  const locale = useLocale()
  const { resolvedTheme } = useTheme()

  const [items, setItems] = React.useState<NotificationItem[]>([])
  const [isLoading, setIsLoading] = React.useState(true)
  const [isLoadingMore, setIsLoadingMore] = React.useState(false)
  const [isRefreshing, setIsRefreshing] = React.useState(false)
  const [failedOperation, setFailedOperation] = React.useState<NotificationLoadOperation | null>(null)
  const loadFailed = failedOperation !== null
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

  const requestSeqRef = React.useRef(0)
  const pendingCountRef = React.useRef(0)
  const loadedPagesRef = React.useRef(0)
  const totalRef = React.useRef(0)

  const buildListParams = React.useCallback((page: number) => {
    const scope = Array.from(scopeFilter)[0] as NotificationScope | undefined
    const level = Array.from(levelFilter)[0] as NotificationLevel | undefined
    return {
      page,
      page_size: PAGE_SIZE,
      scope: scope || undefined,
      level: level || undefined,
      search: debouncedSearchQuery || undefined,
      unread_only: readFilter.has('unread'),
    }
  }, [scopeFilter, levelFilter, readFilter, debouncedSearchQuery])

  // 重新加载第一页：筛选/搜索变化或首次进入
  const loadFirstPage = React.useCallback(async () => {
    const seq = ++requestSeqRef.current
    pendingCountRef.current += 1
    setIsLoading(true)
    setIsLoadingMore(false)
    setIsRefreshing(false)
    setFailedOperation(null)
    // 新筛选条件读取失败时不能沿用旧筛选的条目和游标
    loadedPagesRef.current = 0
    totalRef.current = 0
    setItems([])
    setTotal(0)
    try {
      const result = await notificationsApi.list(buildListParams(1))
      if (seq !== requestSeqRef.current) return
      setItems(result.items)
      setTotal(result.total)
      totalRef.current = result.total
      loadedPagesRef.current = 1
    } catch (error) {
      console.error('Failed to fetch notifications:', error)
      if (seq === requestSeqRef.current) setFailedOperation('first')
    } finally {
      pendingCountRef.current -= 1
      if (seq === requestSeqRef.current) setIsLoading(false)
    }
  }, [buildListParams])

  // 滚动到底部时增量加载，不再一次性拉取所有未读页
  const loadMore = React.useCallback(async () => {
    if (pendingCountRef.current > 0 || loadedPagesRef.current === 0) return
    if (items.length >= totalRef.current) return

    const seq = requestSeqRef.current
    const nextPage = loadedPagesRef.current + 1
    pendingCountRef.current += 1
    setIsLoadingMore(true)
    setFailedOperation(null)
    try {
      const result = await notificationsApi.list(buildListParams(nextPage))
      if (seq !== requestSeqRef.current) return
      const seen = new Set(items.map(item => item.id))
      const appended: NotificationItem[] = []
      for (const item of result.items) {
        if (seen.has(item.id)) continue
        seen.add(item.id)
        appended.push(item)
      }
      const nextTotal = result.items.length === 0 ? items.length : result.total
      setItems([...items, ...appended])
      totalRef.current = nextTotal
      setTotal(nextTotal)
      loadedPagesRef.current = nextPage
    } catch (error) {
      console.error('Failed to fetch notifications:', error)
      if (seq === requestSeqRef.current) setFailedOperation('more')
    } finally {
      pendingCountRef.current -= 1
      if (seq === requestSeqRef.current) setIsLoadingMore(false)
    }
  }, [items, buildListParams])

  // 已读状态变化后刷新已加载窗口：未读集合收缩时不会跳过条目。
  // force=true 会接管在途的追加请求（旧响应按 seq 丢弃），保证变更后的窗口刷新一定执行。
  const refreshLoadedPages = React.useCallback(async (options?: { force?: boolean }) => {
    const force = options?.force ?? false
    const pages = loadedPagesRef.current
    if (pages === 0) {
      await loadFirstPage()
      return
    }
    if (!force && pendingCountRef.current > 0) return

    const seq = force ? ++requestSeqRef.current : requestSeqRef.current
    pendingCountRef.current += 1
    if (force) {
      setIsLoading(false)
      setIsLoadingMore(false)
    }
    setIsRefreshing(true)
    setFailedOperation(null)
    try {
      const merged: NotificationItem[] = []
      const seen = new Set<string>()
      let latestTotal = totalRef.current
      let nextLoadedPages = 1

      for (let page = 1; page <= pages; page += 1) {
        const result = await notificationsApi.list(buildListParams(page))
        if (seq !== requestSeqRef.current) return
        latestTotal = result.total
        if (result.items.length === 0) {
          nextLoadedPages = Math.max(page - 1, 1)
          break
        }
        nextLoadedPages = page
        for (const item of result.items) {
          if (seen.has(item.id)) continue
          seen.add(item.id)
          merged.push(item)
        }
      }

      setItems(merged)
      loadedPagesRef.current = nextLoadedPages
      totalRef.current = latestTotal
      setTotal(latestTotal)
    } catch (error) {
      console.error('Failed to fetch notifications:', error)
      if (seq === requestSeqRef.current) setFailedOperation('refresh')
    } finally {
      pendingCountRef.current -= 1
      if (seq === requestSeqRef.current) setIsRefreshing(false)
    }
  }, [buildListParams, loadFirstPage])

  const retryLoad = React.useCallback(() => {
    const operation = failedOperation
    setFailedOperation(null)
    if (operation === 'more' && loadedPagesRef.current > 0) {
      void loadMore()
      return
    }
    if (operation === 'refresh' && loadedPagesRef.current > 0) {
      void refreshLoadedPages({ force: true })
      return
    }
    void loadFirstPage()
  }, [failedOperation, loadFirstPage, loadMore, refreshLoadedPages])

  React.useEffect(() => {
    void loadFirstPage()
  }, [loadFirstPage])

  React.useEffect(() => () => {
    // 卸载后到达的响应不再写入状态
    requestSeqRef.current += 1
  }, [])

  const hasMore = items.length < total
  const sentinelRef = useInfiniteScroll({
    hasMore: hasMore && !loadFailed,
    loading: isLoading || isLoadingMore || isRefreshing,
    onLoadMore: () => { void loadMore() },
  })

  const handleMarkRead = async (id: string) => {
    try {
      await notificationsApi.markRead({ notification_ids: [id] })
      toast.success(t('toast.readUpdated'))
      onReadUpdated?.()
      await refreshLoadedPages({ force: true })
    } catch (error) {
      console.error('Failed to mark read:', error)
    }
  }

  const handleMarkAllRead = async () => {
    try {
      await notificationsApi.markRead({ mark_all: true })
      toast.success(t('toast.readUpdated'))
      onReadUpdated?.()
      await refreshLoadedPages({ force: true })
    } catch (error) {
      console.error('Failed to mark all read:', error)
    }
  }

  const handleInlineResolved = async () => {
    onReadUpdated?.()
    await refreshLoadedPages({ force: true })
  }

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
            ) : loadFailed && items.length === 0 ? (
              <TableRow>
                <TableCell colSpan={5} className="text-center">
                  <div className="flex flex-col items-center gap-2">
                    <span className="text-muted-foreground">{commonT('loadFailed')}</span>
                    <Button variant="outline" size="sm" onClick={retryLoad}>
                      {commonT('retry')}
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
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
                  <TableRow key={item.id} className={getRowClassName(item)}>
                    <TableCell className="max-w-[320px] min-w-0">
                      <button
                        type="button"
                        className="flex min-w-0 cursor-pointer flex-col gap-1.5 text-left"
                        onClick={() => openDetail(item)}
                      >
                        <span className="flex min-w-0 items-center gap-2">
                          <span className={cn('min-w-0 truncate font-medium', meta.isAnnouncement && 'font-semibold')}>{item.title}</span>
                          {!item.is_read && <span className="inline-flex size-2 shrink-0 rounded-full bg-primary" />}
                        </span>
                        <span className="flex flex-wrap items-center gap-1.5">
                          <NotificationKindBadge item={item} label={t(`kindOptions.${meta.kind}`)} />
                        </span>
                      </button>
                    </TableCell>
                    <TableCell>
                      <Badge variant="secondary">{t(`scopeOptions.${item.scope}`)}</Badge>
                    </TableCell>
                    <TableCell>
                      <Badge variant={meta.priorityScore >= 5 ? 'default' : 'outline'}>{t(`levelOptions.${item.level}`)}</Badge>
                    </TableCell>
                    <TableCell>{formatDateTime(item.created_at, locale)}</TableCell>
                    <TableCell className="text-right">
                      {getPauseActionMeta(item) ? (
                        <PauseRequestActions
                          variant="compact"
                          workflowId={getPauseActionMeta(item)!.workflowId}
                          runId={getPauseActionMeta(item)!.runId}
                          pauseRequestId={getPauseActionMeta(item)!.requestId}
                          onResolved={() => void handleInlineResolved()}
                        />
                      ) : !item.is_read ? (
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

      {/* 无限滚动：哨兵始终挂载，滚动到底部自动加载下一页 */}
      <div ref={sentinelRef} aria-hidden className="h-px w-full" />

      {isLoadingMore && (
        <div className="flex items-center justify-center gap-2 py-2 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" />
          {commonT('loadingMore')}
        </div>
      )}

      {loadFailed && items.length > 0 && (
        <div className="flex items-center justify-center gap-2 py-2 text-sm text-muted-foreground">
          <span>{commonT('loadFailed')}</span>
          <Button variant="outline" size="sm" onClick={retryLoad}>
            {commonT('retry')}
          </Button>
        </div>
      )}

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
                  <span>{t('createdAt')}: {formatDateTime(selectedItem.created_at, locale)}</span>
                </div>
                <div className={cn(
                  'min-h-0 flex-1 overflow-y-auto rounded-lg border bg-muted/30 p-6 text-sm text-foreground',
                  meta.isAnnouncement && 'border-amber-500/50',
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
