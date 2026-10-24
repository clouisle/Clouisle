'use client'

import * as React from 'react'
import { useLocale, useTranslations } from 'next-intl'
import {
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  RefreshCw,
  Search,
  X,
} from 'lucide-react'
import {
  deliveriesApi,
  type DeliveryPage,
  type DeliveryProvider,
  type DeliveryStatus,
} from '@/lib/api/deliveries'
import { ApiError } from '@/lib/api/client'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { DataTableFacetedFilter } from '@/components/ui/data-table-faceted-filter'
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
import { useDebounce } from '@/hooks/use-debounce'
import { useUrlSearchState } from '@/hooks/use-url-search-state'
import { formatDateTime } from '@/lib/utils'

const PROVIDERS: DeliveryProvider[] = ['feishu', 'wechat']
const STATUSES: DeliveryStatus[] = [
  'pending',
  'sending',
  'sent',
  'error',
  'unavailable',
  'unknown',
]
const PAGE_SIZES = [10, 20, 50, 100]

function statusVariant(status: DeliveryStatus) {
  if (status === 'error') return 'destructive' as const
  return 'outline' as const
}

export function DeliveryLogClient() {
  const t = useTranslations('deliveryLog')
  const commonT = useTranslations('common')
  const locale = useLocale()
  const [search, setSearch] = useUrlSearchState()
  const [providers, setProviders] = React.useState<Set<string>>(new Set())
  const [statuses, setStatuses] = React.useState<Set<string>>(new Set())
  const [page, setPage] = React.useState(1)
  const [pageSize, setPageSize] = React.useState(20)
  const [data, setData] = React.useState<DeliveryPage | null>(null)
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState('')
  const generation = React.useRef(0)
  const debouncedSearch = useDebounce(search, 300)

  const load = React.useCallback(async () => {
    const current = ++generation.current
    setLoading(true)
    setError('')
    try {
      const term = debouncedSearch.trim()
      const isRunId = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(term)
      const next = await deliveriesApi.list({
        provider_type: providers.size ? Array.from(providers) as DeliveryProvider[] : undefined,
        status: statuses.size ? Array.from(statuses) as DeliveryStatus[] : undefined,
        run_id: isRunId ? term : undefined,
        filename: !isRunId && term ? term : undefined,
        limit: pageSize,
        offset: (page - 1) * pageSize,
      })
      if (current === generation.current) setData(next)
    } catch (err) {
      if (current !== generation.current) return
      setData(null)
      setError(err instanceof ApiError ? err.message : t('loadFailed'))
    } finally {
      if (current === generation.current) setLoading(false)
    }
  }, [debouncedSearch, page, pageSize, providers, statuses, t])

  React.useEffect(() => {
    const requests = generation
    void load()
    return () => { requests.current++ }
  }, [load])

  const hasFilters = Boolean(search) || providers.size > 0 || statuses.size > 0

  const resetFilters = () => {
    setSearch('')
    setProviders(new Set())
    setStatuses(new Set())
    setPage(1)
  }

  const total = data?.total ?? 0
  const totalPages = Math.max(1, Math.ceil(total / pageSize))
  const rows = data?.items ?? []

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold">{t('title')}</h1>
        <p className="mt-2 text-muted-foreground">{t('description')}</p>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>{t('title')}</CardTitle>
        </CardHeader>
        <CardContent>

        <div className="mb-4 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex flex-1 flex-wrap items-center gap-2">
            <div className="relative max-w-sm flex-1">
              <Search className="absolute top-2.5 left-2.5 h-4 w-4 text-muted-foreground" />
              <Input
                aria-label={t('searchPlaceholder')}
                placeholder={t('searchPlaceholder')}
                value={search}
                onChange={(event) => {
                  setSearch(event.target.value)
                  setPage(1)
                }}
                className="pl-8"
              />
            </div>

            <DataTableFacetedFilter
              title={t('provider')}
              options={PROVIDERS.map((value) => ({ value, label: t(`providers.${value}`) }))}
              selectedValues={providers}
              onSelectionChange={(values) => {
                setProviders(values)
                setPage(1)
              }}
            />

            <DataTableFacetedFilter
              title={t('status')}
              options={STATUSES.map((value) => ({ value, label: t(`statuses.${value}`) }))}
              selectedValues={statuses}
              onSelectionChange={(values) => {
                setStatuses(values)
                setPage(1)
              }}
            />

            {hasFilters && (
              <Button variant="ghost" onClick={resetFilters} className="h-8 px-2 lg:px-3">
                {commonT('reset')}
                <X className="ml-2 h-4 w-4" />
              </Button>
            )}
          </div>

          <Button
            variant="outline"
            onClick={() => void load()}
            disabled={loading}
            aria-label={t('refresh')}
            title={t('refresh')}
          >
            <RefreshCw className={loading ? 'h-4 w-4 animate-spin' : 'h-4 w-4'} />
          </Button>
        </div>

        {error && (
          <p role="alert" className="mb-4 text-sm text-destructive">
            {error}
          </p>
        )}

        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t('columns.time')}</TableHead>
                <TableHead>{t('columns.provider')}</TableHead>
                <TableHead>{t('columns.kind')}</TableHead>
                <TableHead>{t('columns.file')}</TableHead>
                <TableHead>{t('columns.status')}</TableHead>
                <TableHead>{t('columns.error')}</TableHead>
                <TableHead>{t('columns.runId')}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading || rows.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={7} className="h-24 text-center text-muted-foreground">
                    {loading ? t('loading') : t('empty')}
                  </TableCell>
                </TableRow>
              ) : (
                rows.map((row) => (
                  <TableRow key={row.id}>
                    <TableCell className="whitespace-nowrap">
                      {formatDateTime(row.created_at, locale.slice(0, 2), '-', {
                        withSeconds: true,
                      })}
                    </TableCell>
                    <TableCell className="whitespace-nowrap">
                      {t(`providers.${row.provider_type}`)}
                    </TableCell>
                    <TableCell className="whitespace-nowrap">
                      {t(`kinds.${row.kind}`)}
                    </TableCell>
                    <TableCell className="max-w-[18rem]">
                      <div className="truncate" title={row.filename ?? undefined}>
                        {row.filename || row.content_type || '-'}
                      </div>
                      <div className="truncate text-xs text-muted-foreground">
                        {row.event_key}
                      </div>
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant={statusVariant(row.status)}
                        className={row.status === 'sent' ? 'bg-green-500 text-white' : undefined}
                      >
                        {t(`statuses.${row.status}`)}
                      </Badge>
                    </TableCell>
                    <TableCell className="max-w-[20rem]">
                      <div
                        className="whitespace-pre-wrap break-words font-mono text-xs [overflow-wrap:anywhere]"
                        title={row.error_detail ?? row.error ?? undefined}
                      >
                        {row.error_detail || row.error || '-'}
                      </div>
                    </TableCell>
                    <TableCell className="max-w-[12rem]">
                      <div
                        className="truncate font-mono text-xs"
                        title={row.run_id ?? undefined}
                      >
                        {row.run_id || '-'}
                      </div>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </div>

        <div className="mt-4 flex items-center justify-between">
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Select
              value={pageSize.toString()}
              onValueChange={(value) => {
                setPageSize(Number(value))
                setPage(1)
              }}
            >
              <SelectTrigger size="sm" className="w-18" aria-label={t('rowsPerPage')}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent side="top" alignItemWithTrigger={false}>
                {PAGE_SIZES.map((size) => (
                  <SelectItem key={size} value={size.toString()}>
                    {size}
                  </SelectItem>
                ))}
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
                aria-label={t('firstPage')}
                onClick={() => setPage(1)}
                disabled={loading || page === 1}
              >
                <ChevronsLeft className="h-4 w-4" />
              </Button>
              <Button
                variant="outline"
                size="icon"
                className="h-8 w-8"
                aria-label={t('previousPage')}
                onClick={() => setPage((current) => Math.max(1, current - 1))}
                disabled={loading || page === 1}
              >
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <Button
                variant="outline"
                size="icon"
                className="h-8 w-8"
                aria-label={t('nextPage')}
                onClick={() => setPage((current) => Math.min(totalPages, current + 1))}
                disabled={loading || page >= totalPages}
              >
                <ChevronRight className="h-4 w-4" />
              </Button>
              <Button
                variant="outline"
                size="icon"
                className="h-8 w-8"
                aria-label={t('lastPage')}
                onClick={() => setPage(totalPages)}
                disabled={loading || page >= totalPages}
              >
                <ChevronsRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </div>

        </CardContent>
      </Card>
    </div>
  )
}
