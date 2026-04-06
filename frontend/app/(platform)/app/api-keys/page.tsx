'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
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
import { formatDateTime } from '@/lib/utils'
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
import { DeleteAPIKeyDialog } from './_components/delete-api-key-dialog'
import { ShowKeyDialog } from './_components/show-key-dialog'

export default function APIKeysPage() {
  const t = useTranslations('apiKeys')
  const commonT = useTranslations('common')

  // 数据状态
  const [apiKeys, setApiKeys] = React.useState<APIKey[]>([])
  const [isLoading, setIsLoading] = React.useState(true)
  const [searchQuery, setSearchQuery] = React.useState('')

  // Dialog 状态
  const [keyDialogOpen, setKeyDialogOpen] = React.useState(false)
  const [deleteDialogOpen, setDeleteDialogOpen] = React.useState(false)
  const [showKeyDialogOpen, setShowKeyDialogOpen] = React.useState(false)
  const [selectedAPIKey, setSelectedAPIKey] = React.useState<APIKey | null>(null)
  const [newAPIKey, setNewAPIKey] = React.useState<string | null>(null)

  // 加载 API Key 列表
  const loadAPIKeys = React.useCallback(async () => {
    setIsLoading(true)
    try {
      const data = await apiKeysApi.getAPIKeys({ pageSize: 100 })
      setApiKeys(data.items)
    } catch {
      // 错误已由 API 客户端处理
    } finally {
      setIsLoading(false)
    }
  }, [])

  React.useEffect(() => {
    loadAPIKeys()
  }, [loadAPIKeys])

  // 筛选
  const filteredKeys = React.useMemo(() => {
    return apiKeys.filter(key => {
      if (searchQuery) {
        const query = searchQuery.toLowerCase()
        if (!key.name.toLowerCase().includes(query) &&
            !key.key_prefix.toLowerCase().includes(query)) {
          return false
        }
      }
      return true
    })
  }, [apiKeys, searchQuery])

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
      loadAPIKeys()
    } catch {
      // 错误已由 API 客户端处理
    }
  }

  // Dialog 成功回调
  const handleDialogSuccess = (key?: string) => {
    loadAPIKeys()

    // 如果是新创建的 key，显示密钥
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
  if (isLoading) {
    return (
      <div className="py-6 px-8 h-full overflow-y-auto">
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
    <div className="py-6 px-8 h-full overflow-y-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">{t('title')}</h1>
          <p className="text-muted-foreground mt-1">{t('description')}</p>
        </div>
        <Button onClick={handleCreate}>
          <Plus className="mr-2 h-4 w-4" />
          {t('createKey')}
        </Button>
      </div>

      {/* 搜索栏 */}
      <div className="relative mb-6 max-w-md">
        <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          placeholder={t('filterKeys')}
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="pl-8 h-9"
        />
      </div>

      {/* API Keys 列表 */}
      {apiKeys.length === 0 ? (
        <div className="text-center py-12 text-muted-foreground">
          <Key className="h-12 w-12 mx-auto mb-4 opacity-50" />
          <p>{t('noKeys')}</p>
          <p className="text-sm mt-1">{t('createKeyHint')}</p>
          <Button onClick={handleCreate} className="mt-4">
            <Plus className="mr-2 h-4 w-4" />
            {t('createKey')}
          </Button>
        </div>
      ) : filteredKeys.length === 0 ? (
        <div className="text-center py-12 text-muted-foreground">
          <Search className="h-12 w-12 mx-auto mb-4 opacity-50" />
          <p>{t('noKeysFound')}</p>
          <Button variant="outline" className="mt-4" onClick={() => setSearchQuery('')}>
            <X className="mr-2 h-4 w-4" />
            {commonT('clearSearch')}
          </Button>
        </div>
      ) : (
        <div className="space-y-2">
          {filteredKeys.map((apiKey) => {
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
                      {apiKey.expires_at ? formatDateTime(apiKey.expires_at) : t('never')}
                    </span>
                  </div>
                  <div className="flex flex-col items-end">
                    <span className="text-xs">{t('lastUsed')}</span>
                    <span className="font-medium text-foreground">
                      {apiKey.last_used_at ? formatDateTime(apiKey.last_used_at) : t('neverUsed')}
                    </span>
                  </div>
                  <div className="flex flex-col items-end">
                    <span className="text-xs">{t('createdAt')}</span>
                    <span className="font-medium text-foreground">
                      {formatDateTime(apiKey.created_at)}
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
                  <DropdownMenu>
                    <DropdownMenuTrigger className="opacity-0 group-hover:opacity-100 transition-opacity ring-offset-background focus-visible:ring-ring data-[state=open]:opacity-100 inline-flex h-8 w-8 items-center justify-center rounded-md hover:bg-accent focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:outline-none">
                      <MoreHorizontal className="h-4 w-4" />
                      <span className="sr-only">{commonT('openMenu')}</span>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                      <DropdownMenuItem onClick={() => handleEdit(apiKey)}>
                        <Pencil className="mr-2 h-4 w-4" />
                        {commonT('edit')}
                      </DropdownMenuItem>

                      <DropdownMenuItem onClick={() => handleToggleStatus(apiKey)}>
                        {apiKey.is_active ? (
                          <>
                            <KeyRound className="mr-2 h-4 w-4" />
                            {t('deactivate')}
                          </>
                        ) : (
                          <>
                            <Key className="mr-2 h-4 w-4" />
                            {t('activate')}
                          </>
                        )}
                      </DropdownMenuItem>

                      <DropdownMenuSeparator />
                      <DropdownMenuItem
                        onClick={() => handleDelete(apiKey)}
                        className="text-destructive focus:text-destructive"
                      >
                        <Trash2 className="mr-2 h-4 w-4" />
                        {commonT('delete')}
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </div>
              </div>
            )
          })}
        </div>
      )}

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
