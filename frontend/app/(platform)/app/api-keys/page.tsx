'use client'

import * as React from 'react'
import { useTranslations, useLocale } from 'next-intl'
import {
  Plus,
  Search,
  MoreHorizontal,
  Pencil,
  Trash2,
  Key,
  KeyRound,
  X,
  AlertCircle,
} from 'lucide-react'
import { toast } from 'sonner'
import { apiKeysApi, type APIKey } from '@/lib/api'
import { RoutePermissionGuard } from '@/components/auth/permission-guard'
import { PermissionGuard, useCanPerform } from '@/components/permission-guard'
import { formatDateTime } from '@/lib/utils'
import { useDebounce } from '@/hooks/use-debounce'
import { useInfiniteScroll } from '@/hooks/use-infinite-scroll'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Skeleton } from '@/components/ui/skeleton'
import { APIKeyDialog } from './_components/api-key-dialog'
import { ShowKeyDialog } from './_components/show-key-dialog'
import { DeleteAPIKeyDialog } from './_components/delete-api-key-dialog'

const PAGE_SIZE = 20

function APIKeysContent() {
  const t = useTranslations('apiKeys')
  const commonT = useTranslations('common')
  const locale = useLocale()
  const { canPerform } = useCanPerform()

  // 数据状态
  const [apiKeys, setApiKeys] = React.useState<APIKey[]>([])
  const [page, setPage] = React.useState(1)
  const [hasMore, setHasMore] = React.useState(false)
  const [isInitialLoading, setIsInitialLoading] = React.useState(true)
  const [isLoadingMore, setIsLoadingMore] = React.useState(false)
  const [loadError, setLoadError] = React.useState(false)
  const [searchQuery, setSearchQuery] = React.useState('')
  const debouncedSearch = useDebounce(searchQuery.trim(), 300)
  const requestIdRef = React.useRef(0)
  const hasLoadedOnceRef = React.useRef(false)
  const inFlightRef = React.useRef(false)
  const failedRequestRef = React.useRef<{ page: number; append: boolean } | null>(null)

  // Dialog 状态
  const [keyDialogOpen, setKeyDialogOpen] = React.useState(false)
  const [deleteDialogOpen, setDeleteDialogOpen] = React.useState(false)
  const [showKeyDialogOpen, setShowKeyDialogOpen] = React.useState(false)
  const [selectedAPIKey, setSelectedAPIKey] = React.useState<APIKey | null>(null)
  const [newAPIKey, setNewAPIKey] = React.useState<string | null>(null)

  // 加载 API Key 列表
  const loadPage = React.useCallback(async (pageToLoad: number, append: boolean) => {
    if (append && inFlightRef.current) return

    const requestId = ++requestIdRef.current
    inFlightRef.current = true
    failedRequestRef.current = null
    setLoadError(false)
    if (append) {
      setIsLoadingMore(true)
    } else {
      setIsInitialLoading(true)
      setIsLoadingMore(false)
      setHasMore(false)
    }

    try {
      const data = await apiKeysApi.getAPIKeys({
        page: pageToLoad,
        pageSize: PAGE_SIZE,
        search: debouncedSearch || undefined,
      })
      if (requestId !== requestIdRef.current) return

      setApiKeys((previous) => {
        if (!append) return data.items
        const merged = [...previous]
        const seen = new Set(previous.map((key) => key.id))
        for (const key of data.items) {
          if (seen.has(key.id)) continue
          seen.add(key.id)
          merged.push(key)
        }
        return merged
      })
      setPage(pageToLoad)
      setHasMore(pageToLoad * data.page_size < data.total)
    } catch {
      if (requestId !== requestIdRef.current) return
      // 错误已由 API 客户端处理
      failedRequestRef.current = { page: pageToLoad, append }
      setLoadError(true)
      setHasMore(false)
      if (!append) setApiKeys([])
    } finally {
      if (requestId === requestIdRef.current) {
        inFlightRef.current = false
        if (append) {
          setIsLoadingMore(false)
        } else {
          hasLoadedOnceRef.current = true
          setIsInitialLoading(false)
        }
      }
    }
  }, [debouncedSearch])

  React.useEffect(() => {
    void loadPage(1, false)
    return () => {
      requestIdRef.current += 1
    }
  }, [loadPage])

  const loadMore = React.useCallback(() => {
    if (inFlightRef.current || loadError || isLoadingMore || isInitialLoading || !hasMore) return
    void loadPage(page + 1, true)
  }, [hasMore, isInitialLoading, isLoadingMore, loadError, loadPage, page])

  const sentinelRef = useInfiniteScroll({
    hasMore: hasMore && !loadError,
    loading: isInitialLoading || isLoadingMore,
    onLoadMore: loadMore,
  })

  const handleRetry = () => {
    const failed = failedRequestRef.current
    if (inFlightRef.current || !failed) return
    void loadPage(failed.page, failed.append)
  }

  // 打开创建 Dialog
  const handleCreate = () => {
    setSelectedAPIKey(null)
    setKeyDialogOpen(true)
  }

  // 打开编辑 Dialog
  const handleEdit = (apiKey: APIKey) => {
    setSelectedAPIKey(apiKey)
    setKeyDialogOpen(true)
  }

  // 打开删除 Dialog
  const handleDelete = (apiKey: APIKey) => {
    setSelectedAPIKey(apiKey)
    setDeleteDialogOpen(true)
  }

  // 切换状态
  const handleToggleStatus = async (apiKey: APIKey) => {
    try {
      if (apiKey.is_active) {
        await apiKeysApi.deactivateAPIKey(apiKey.id)
        toast.success(t('keyDeactivated'))
      } else {
        await apiKeysApi.activateAPIKey(apiKey.id)
        toast.success(t('keyActivated'))
      }
      void loadPage(1, false)
    } catch {
      // 错误已由 API 客户端处理
    }
  }

  // Dialog 成功回调
  const handleDialogSuccess = (key?: string) => {
    void loadPage(1, false)
    if (key) {
      setNewAPIKey(key)
      setShowKeyDialogOpen(true)
    }
  }

  // 获取状态 Badge
  const getStatusBadge = (apiKey: APIKey) => {
    const now = new Date()
    const isExpired = apiKey.expires_at && new Date(apiKey.expires_at) < now

    if (isExpired) {
      return <Badge variant="outline" className="text-orange-500 border-orange-500/50">{t('expired')}</Badge>
    }
    if (apiKey.is_active) {
      return <Badge variant="default" className="bg-emerald-500/10 text-emerald-500 hover:bg-emerald-500/20 border-0">{t('active')}</Badge>
    }
    return <Badge variant="outline" className="text-muted-foreground">{t('inactive')}</Badge>
  }


  // Loading state
  if (isInitialLoading && !hasLoadedOnceRef.current) {
    return (
      <div className="py-6 px-8 h-full overflow-y-auto" data-testid="api-keys-page">
        <div className="flex items-center justify-between mb-6">
          <div>
            <Skeleton className="h-9 w-32" />
            <Skeleton className="h-5 w-64 mt-1" />
          </div>
          <Skeleton className="h-9 w-32" />
        </div>
        <Skeleton className="h-9 w-64 mb-6" />
        <div className="space-y-2">
          {[...Array(6)].map((_, i) => (
            <Skeleton key={i} className="h-20" />
          ))}
        </div>
      </div>
    )
  }

  return (
    <div className="py-6 px-8 h-full overflow-y-auto" data-testid="api-keys-page">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">{t('title')}</h1>
          <p className="text-muted-foreground mt-1">{t('description')}</p>
        </div>
        <PermissionGuard permission="apikey:create">
          <Button onClick={handleCreate} data-testid="api-keys-create-button">
            <Plus className="mr-2 h-4 w-4" />
            {t('createKey')}
          </Button>
        </PermissionGuard>
      </div>

      <div className="relative mb-6 max-w-md">
        <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          placeholder={t('filterKeys')}
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="pl-8 h-9"
        />
      </div>

      {loadError && (
        <div className="flex flex-col items-center gap-2 py-4 text-sm text-muted-foreground">
          <p>{commonT('loadFailed')}</p>
          <Button variant="outline" size="sm" onClick={handleRetry}>
            {commonT('retry')}
          </Button>
        </div>
      )}

      {!loadError && apiKeys.length === 0 && searchQuery && (
        <div className="text-center py-12 text-muted-foreground">
          <Search className="h-12 w-12 mx-auto mb-4 opacity-50" />
          <p>{t('noKeysFound')}</p>
          <Button variant="outline" className="mt-4" onClick={() => setSearchQuery('')}>
            <X className="mr-2 h-4 w-4" />
            {commonT('clearSearch')}
          </Button>
        </div>
      )}

      {!loadError && apiKeys.length === 0 && !searchQuery && (
        <div className="text-center py-12 text-muted-foreground">
          <Key className="h-12 w-12 mx-auto mb-4 opacity-50" />
          <p>{t('noKeys')}</p>
          <p className="text-sm mt-1">{t('createKeyHint')}</p>
          <PermissionGuard permission="apikey:create">
            <Button onClick={handleCreate} className="mt-4">
              <Plus className="mr-2 h-4 w-4" />
              {t('createKey')}
            </Button>
          </PermissionGuard>
        </div>
      )}

      {apiKeys.length > 0 && (
        <div className="space-y-2">
          {apiKeys.map((apiKey) => {
            const now = new Date()
            const isExpired = apiKey.expires_at && new Date(apiKey.expires_at) < now

            return (
              <div
                key={apiKey.id}
                className="group relative flex items-center gap-4 rounded-lg border bg-card p-4 hover:bg-accent/50 transition-colors"
              >
                {/* Icon */}
                <div className="shrink-0">
                  <Key className="h-5 w-5 text-muted-foreground" />
                </div>

                {/* Name and Key Prefix */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <h3 className="font-medium truncate">{apiKey.name}</h3>
                    {getStatusBadge(apiKey)}
                  </div>
                  <code className="text-xs text-muted-foreground bg-muted px-1.5 py-0.5 rounded font-mono">
                    {apiKey.key_prefix}...
                  </code>
                </div>

                {/* Metadata */}
                <div className="hidden lg:flex items-center gap-6 text-sm text-muted-foreground shrink-0">
                  <div className="flex flex-col items-end">
                    <span className="text-xs">{t('rateLimit')}</span>
                    <span className="font-medium text-foreground">
                      {apiKey.rate_limit > 0 ? `${apiKey.rate_limit}/min` : t('unlimited')}
                    </span>
                  </div>
                  <div className="flex flex-col items-end">
                    <span className="text-xs">{t('expiresAt')}</span>
                    <span className="font-medium text-foreground">
                      {apiKey.expires_at ? formatDateTime(apiKey.expires_at, locale) : t('never')}
                    </span>
                  </div>
                  <div className="flex flex-col items-end">
                    <span className="text-xs">{t('lastUsed')}</span>
                    <span className="font-medium text-foreground">
                      {apiKey.last_used_at ? formatDateTime(apiKey.last_used_at, locale) : t('neverUsed')}
                    </span>
                  </div>
                  <div className="flex flex-col items-end">
                    <span className="text-xs">{t('createdAt')}</span>
                    <span className="font-medium text-foreground">
                      {formatDateTime(apiKey.created_at, locale)}
                    </span>
                  </div>
                </div>

                {/* Expired Warning */}
                {isExpired && (
                  <div className="shrink-0">
                    <AlertCircle className="h-5 w-5 text-orange-500" />
                  </div>
                )}

                {/* Actions Menu */}
                <div className="shrink-0">
                  {(canPerform('apikey:update') || canPerform('apikey:delete')) && (
                    <DropdownMenu>
                      <DropdownMenuTrigger className="opacity-0 group-hover:opacity-100 transition-opacity ring-offset-background focus-visible:ring-ring data-[state=open]:opacity-100 inline-flex h-8 w-8 items-center justify-center rounded-md hover:bg-accent focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:outline-none">
                        <MoreHorizontal className="h-4 w-4" />
                        <span className="sr-only">{commonT('openMenu')}</span>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        {canPerform('apikey:update') && (
                          <>
                            <DropdownMenuItem onClick={() => handleEdit(apiKey)}>
                              <Pencil className="mr-2 h-4 w-4" />
                              {commonT('edit')}
                            </DropdownMenuItem>
                            <DropdownMenuItem onClick={() => handleToggleStatus(apiKey)}>
                              {apiKey.is_active ? (
                                <><KeyRound className="mr-2 h-4 w-4" />{t('deactivate')}</>
                              ) : (
                                <><Key className="mr-2 h-4 w-4" />{t('activate')}</>
                              )}
                            </DropdownMenuItem>
                          </>
                        )}
                        {canPerform('apikey:delete') && (
                          <>
                            <DropdownMenuSeparator />
                            <DropdownMenuItem
                              onClick={() => handleDelete(apiKey)}
                              className="text-destructive focus:text-destructive"
                            >
                              <Trash2 className="mr-2 h-4 w-4" />
                              {commonT('delete')}
                            </DropdownMenuItem>
                          </>
                        )}
                      </DropdownMenuContent>
                    </DropdownMenu>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}

      {isLoadingMore && (
        <div className="py-4 text-center text-sm text-muted-foreground">
          {commonT('loadingMore')}
        </div>
      )}

      <div ref={sentinelRef} aria-hidden="true" className="h-px" />

      {/* 创建/编辑 Dialog */}
      <APIKeyDialog
        open={keyDialogOpen}
        onOpenChange={setKeyDialogOpen}
        apiKey={selectedAPIKey}
        onSuccess={handleDialogSuccess}
      />

      {/* 删除确认 Dialog */}
      <DeleteAPIKeyDialog
        open={deleteDialogOpen}
        onOpenChange={setDeleteDialogOpen}
        apiKey={selectedAPIKey}
        onSuccess={() => handleDialogSuccess()}
      />

      {/* 显示新创建的 Key */}
      <ShowKeyDialog
        open={showKeyDialogOpen}
        onOpenChange={setShowKeyDialogOpen}
        apiKey={newAPIKey}
      />
    </div>
  )
}

export default function APIKeysPage() {
  return (
    <RoutePermissionGuard>
      <APIKeysContent />
    </RoutePermissionGuard>
  )
}
