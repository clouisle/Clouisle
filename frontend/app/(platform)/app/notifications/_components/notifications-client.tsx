'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { Check, ChevronLeft, ChevronRight, Search, X } from 'lucide-react'
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

interface NotificationsClientProps {
  onReadUpdated?: () => void
}

export function NotificationsClient({ onReadUpdated }: NotificationsClientProps) {
  const t = useTranslations('notifications')
  const { resolvedTheme } = useTheme()

  const [items, setItems] = React.useState<NotificationItem[]>([])
  const [isLoading, setIsLoading] = React.useState(true)
  const [page, setPage] = React.useState(1)
  const [pageSize] = React.useState(20)
  const [total, setTotal] = React.useState(0)
  const [scopeFilter, setScopeFilter] = React.useState<Set<string>>(new Set())
  const [levelFilter, setLevelFilter] = React.useState<Set<string>>(new Set())
  const [searchQuery, setSearchQuery] = React.useState('')
  const [debouncedSearchQuery, setDebouncedSearchQuery] = React.useState('')
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
      const result = await notificationsApi.list({
        page,
        page_size: pageSize,
        scope: scope || undefined,
        level: level || undefined,
        search: debouncedSearchQuery || undefined,
        unread_only: readFilter.has('unread'),
      })
      setItems(result.items)
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

  React.useEffect(() => {
    const timer = window.setTimeout(() => {
      setDebouncedSearchQuery(searchQuery.trim())
    }, 300)
    return () => window.clearTimeout(timer)
  }, [searchQuery])

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
              items.map((item) => (
                <TableRow
                  key={item.id}
                  className={cn('cursor-pointer', !item.is_read && 'bg-primary/5')}
                  onClick={() => openDetail(item)}
                >
                  <TableCell className="max-w-[320px] truncate">
                    <div className="flex items-center gap-2">
                      <span className="font-medium">{item.title}</span>
                      {!item.is_read && <span className="inline-flex size-2 rounded-full bg-primary" />}
                    </div>
                  </TableCell>
                  <TableCell>
                    <Badge variant="secondary">{t(`scopeOptions.${item.scope}`)}</Badge>
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline">{t(`levelOptions.${item.level}`)}</Badge>
                  </TableCell>
                  <TableCell>{new Date(item.created_at).toLocaleString()}</TableCell>
                  <TableCell className="text-right">
                    {!item.is_read ? (
                      <Button
                        variant="outline"
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
              ))
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
          {selectedItem && (
            <div className="flex min-h-[180px] max-h-[calc(80vh-8rem)] flex-col gap-4 overflow-hidden">
              <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                <Badge variant="secondary">{t(`scopeOptions.${selectedItem.scope}`)}</Badge>
                <Badge variant="outline">{t(`levelOptions.${selectedItem.level}`)}</Badge>
                <span className="mx-1 h-3 w-px bg-border/70" />
                <span>{t('createdAt')}: {new Date(selectedItem.created_at).toLocaleString()}</span>
              </div>
              <div className="min-h-0 flex-1 overflow-y-auto rounded-lg border bg-muted/30 p-6 text-sm text-foreground" data-color-mode={colorMode}>
                <div className="wmde-markdown">
                  <MDPreview source={selectedItem.content} />
                </div>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}
