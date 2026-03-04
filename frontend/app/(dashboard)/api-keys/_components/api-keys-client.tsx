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
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
} from 'lucide-react'
import { toast } from 'sonner'
import { apiKeysApi, type APIKey, type PageData } from '@/lib/api'
import { usersApi } from '@/lib/api/admin/users'
import type { User } from '@/lib/api/auth'
import { formatDateTime } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { DataTableFacetedFilter } from '@/components/ui/data-table-faceted-filter'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
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
import { APIKeyDialog } from './api-key-dialog'
import { DeleteAPIKeyDialog } from './delete-api-key-dialog'
import { ShowKeyDialog } from './show-key-dialog'
import { PermissionGuard, useCanPerform } from '@/components/permission-guard'

export function APIKeysClient() {
  const t = useTranslations('apiKeys')
  const commonT = useTranslations('common')
  const { canPerform } = useCanPerform()
  
  // 数据状态
  const [apiKeys, setApiKeys] = React.useState<APIKey[]>([])
  const [isLoading, setIsLoading] = React.useState(true)
  const [page, setPage] = React.useState(1)
  const [pageSize, setPageSize] = React.useState(10)
  const [pageData, setPageData] = React.useState<PageData<APIKey> | null>(null)
  
  // 筛选状态
  const [searchQuery, setSearchQuery] = React.useState('')
  const [statusFilter, setStatusFilter] = React.useState<Set<string>>(new Set())
  const [userFilter, setUserFilter] = React.useState<Set<string>>(new Set())
  const [users, setUsers] = React.useState<User[]>([])
  
  // 选择状态
  const [selectedKeys, setSelectedKeys] = React.useState<Set<string>>(new Set())
  
  // Dialog 状态
  const [keyDialogOpen, setKeyDialogOpen] = React.useState(false)
  const [deleteDialogOpen, setDeleteDialogOpen] = React.useState(false)
  const [bulkDeleteDialogOpen, setBulkDeleteDialogOpen] = React.useState(false)
  const [showKeyDialogOpen, setShowKeyDialogOpen] = React.useState(false)
  const [selectedAPIKey, setSelectedAPIKey] = React.useState<APIKey | null>(null)
  const [newAPIKey, setNewAPIKey] = React.useState<string | null>(null)

  // 加载统计
  const loadStats = React.useCallback(async () => {
    try {
      await apiKeysApi.getStats()
    } catch {
      // 忽略错误
    }
  }, [])
  
  // 加载用户列表（用于筛选）
  const loadUsers = React.useCallback(async () => {
    try {
      const data = await usersApi.getUsers({ pageSize: 100 })
      setUsers(data.items)
    } catch {
      // 忽略错误
    }
  }, [])
  
  // 加载 API Key 列表
  const loadAPIKeys = React.useCallback(async () => {
    setIsLoading(true)
    try {
      const data = await apiKeysApi.getAPIKeys({ page, pageSize })
      setApiKeys(data.items)
      setPageData(data)
    } catch {
      // 错误已由 API 客户端处理
    } finally {
      setIsLoading(false)
    }
  }, [page, pageSize])
  
  React.useEffect(() => {
    loadAPIKeys()
    loadStats()
    loadUsers()
  }, [loadAPIKeys, loadStats, loadUsers])
  
  // 筛选
  const filteredKeys = React.useMemo(() => {
    const now = new Date()
    return apiKeys.filter(key => {
      // 搜索筛选
      if (searchQuery) {
        const query = searchQuery.toLowerCase()
        if (!key.name.toLowerCase().includes(query) &&
            !key.key_prefix.toLowerCase().includes(query)) {
          return false
        }
      }
      
      // 用户筛选
      if (userFilter.size > 0 && !userFilter.has(key.user_id)) {
        return false
      }
      
      // 状态筛选
      if (statusFilter.size > 0) {
        const isExpired = key.expires_at && new Date(key.expires_at) < now
        const isActive = key.is_active && !isExpired
        
        if (statusFilter.has('active') && isActive) return true
        if (statusFilter.has('inactive') && !key.is_active) return true
        if (statusFilter.has('expired') && isExpired) return true
        
        return false
      }
      
      return true
    })
  }, [apiKeys, searchQuery, statusFilter, userFilter])
  
  // 检查是否有筛选条件
  const isFiltered = searchQuery || statusFilter.size > 0 || userFilter.size > 0
  
  // 重置所有筛选
  const resetFilters = () => {
    setSearchQuery('')
    setStatusFilter(new Set())
    setUserFilter(new Set())
  }
  
  // 状态选项
  const statusOptions = [
    { value: 'active', label: t('active') },
    { value: 'inactive', label: t('inactive') },
    { value: 'expired', label: t('expired') },
  ]
  
  // 用户选项
  const userOptions = React.useMemo(() => 
    users.map(user => ({
      value: user.id,
      label: user.username,
    })), [users])
  
  // 计算分页信息
  const totalPages = pageData ? Math.ceil(pageData.total / pageSize) : 1
  
  // 选择操作
  const toggleSelectAll = () => {
    if (selectedKeys.size === filteredKeys.length) {
      setSelectedKeys(new Set())
    } else {
      setSelectedKeys(new Set(filteredKeys.map(k => k.id)))
    }
  }
  
  const toggleSelectKey = (keyId: string) => {
    const newSelected = new Set(selectedKeys)
    if (newSelected.has(keyId)) {
      newSelected.delete(keyId)
    } else {
      newSelected.add(keyId)
    }
    setSelectedKeys(newSelected)
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
      loadAPIKeys()
      loadStats()
    } catch {
      // 错误已由 API 客户端处理
    }
  }
  
  // Dialog 成功回调
  const handleDialogSuccess = (key?: string) => {
    loadAPIKeys()
    loadStats()
    setSelectedKeys(new Set())
    
    // 如果是新创建的 key，显示密钥
    if (key) {
      setNewAPIKey(key)
      setShowKeyDialogOpen(true)
    }
  }
  
  // 批量删除
  const handleBulkDelete = () => {
    setBulkDeleteDialogOpen(true)
  }
  
  // 确认批量删除
  const confirmBulkDelete = async () => {
    try {
      const promises = Array.from(selectedKeys).map(id => apiKeysApi.deleteAPIKey(id))
      await Promise.all(promises)
      toast.success(t('bulkDeleted', { count: selectedKeys.size }))
      setSelectedKeys(new Set())
      loadAPIKeys()
      loadStats()
    } catch {
      // 错误已由 API 客户端处理
    } finally {
      setBulkDeleteDialogOpen(false)
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
      return <Badge variant="default" className="bg-emerald-500/10 text-emerald-500 hover:bg-emerald-500/20">{t('active')}</Badge>
    }
    return <Badge variant="outline" className="text-muted-foreground">{t('inactive')}</Badge>
  }

  return (
    <div className="flex flex-col gap-6">
      {/* 页头 */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold">{t('title')}</h1>
          <p className="text-muted-foreground">{t('description')}</p>
        </div>
        <div className="flex items-center gap-2">
          <PermissionGuard permission="apikey:create">
            <Button onClick={handleCreate}>
              <Plus className="mr-2 h-4 w-4" />
              {t('createKey')}
            </Button>
          </PermissionGuard>
        </div>
      </div>
      
      {/* 筛选栏 */}
      <div className="flex items-center justify-between gap-4">
        <div className="flex flex-1 items-center gap-2">
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              placeholder={t('filterKeys')}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-8 w-[200px] h-9"
            />
          </div>
          
          <DataTableFacetedFilter
            title={t('status')}
            options={statusOptions}
            selectedValues={statusFilter}
            onSelectionChange={setStatusFilter}
          />
          
          <DataTableFacetedFilter
            title={t('owner')}
            options={userOptions}
            selectedValues={userFilter}
            onSelectionChange={setUserFilter}
          />
          
          {isFiltered && (
            <>
              <Button
                variant="ghost"
                onClick={resetFilters}
                className="h-9 px-2 lg:px-3"
              >
                {commonT('reset')}
                <X className="ml-2 h-4 w-4" />
              </Button>
            </>
          )}
        </div>
      </div>
      
      {/* 表格 */}
      <div className="rounded-lg border">
        <Table>
          <TableHeader>
            <TableRow className="bg-muted/50 hover:bg-muted/50">
              <TableHead className="w-[40px]">
                <Checkbox
                  checked={selectedKeys.size === filteredKeys.length && filteredKeys.length > 0}
                  onCheckedChange={toggleSelectAll}
                />
              </TableHead>
              <TableHead>{t('name')}</TableHead>
              <TableHead>{t('keyPrefix')}</TableHead>
              <TableHead>{t('owner')}</TableHead>
              <TableHead>{t('status')}</TableHead>
              <TableHead>{t('rateLimit')}</TableHead>
              <TableHead>{t('expiresAt')}</TableHead>
              <TableHead>{t('lastUsed')}</TableHead>
              <TableHead>{t('createdAt')}</TableHead>
              <TableHead className="w-[50px]"></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableRow>
                <TableCell colSpan={10} className="h-24 text-center">
                  {commonT('loading')}
                </TableCell>
              </TableRow>
            ) : filteredKeys.length === 0 ? (
              <TableRow>
                <TableCell colSpan={10} className="h-24 text-center text-muted-foreground">
                  {t('noKeys')}
                </TableCell>
              </TableRow>
            ) : (
              filteredKeys.map((apiKey) => (
                <TableRow key={apiKey.id} data-state={selectedKeys.has(apiKey.id) ? 'selected' : undefined}>
                  <TableCell>
                    <Checkbox
                      checked={selectedKeys.has(apiKey.id)}
                      onCheckedChange={() => toggleSelectKey(apiKey.id)}
                    />
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <Key className="h-4 w-4 text-muted-foreground" />
                      <span className="font-medium">{apiKey.name}</span>
                    </div>
                  </TableCell>
                  <TableCell>
                    <code className="text-sm bg-muted px-2 py-0.5 rounded font-mono">
                      {apiKey.key_prefix}...
                    </code>
                  </TableCell>
                  <TableCell>
                    <span className="text-muted-foreground">
                      {apiKey.user?.username || '-'}
                    </span>
                  </TableCell>
                  <TableCell>{getStatusBadge(apiKey)}</TableCell>
                  <TableCell className="text-muted-foreground">
                    {apiKey.rate_limit > 0 ? `${apiKey.rate_limit}/min` : t('unlimited')}
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {apiKey.expires_at
                      ? formatDateTime(apiKey.expires_at)
                      : t('never')}
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {apiKey.last_used_at
                      ? formatDateTime(apiKey.last_used_at)
                      : t('neverUsed')}
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {formatDateTime(apiKey.created_at)}
                  </TableCell>
                  <TableCell>
                    {(canPerform('apikey:update') || canPerform('apikey:delete')) && (
                      <DropdownMenu>
                        <DropdownMenuTrigger className="ring-offset-background focus-visible:ring-ring data-[state=open]:bg-accent inline-flex h-8 w-8 items-center justify-center rounded-md hover:bg-accent focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:outline-none">
                          <MoreHorizontal className="h-4 w-4" />
                          <span className="sr-only">{t('common.openMenu')}</span>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          {canPerform('apikey:update') && (
                            <DropdownMenuItem onClick={() => handleEdit(apiKey)}>
                              <Pencil className="mr-2 h-4 w-4" />
                              {commonT('edit')}
                            </DropdownMenuItem>
                          )}

                          {canPerform('apikey:update') && (
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
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>
      
      {/* 分页 */}
      {pageData && (
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
      
      {/* 批量操作浮动工具栏 */}
      {selectedKeys.size > 0 && canPerform('apikey:delete') && (
        <div className="fixed bottom-8 left-1/2 -translate-x-1/2 z-50">
          <div className="flex items-center gap-1 rounded-lg border bg-background px-2 py-1.5 shadow-lg">
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              onClick={() => setSelectedKeys(new Set())}
            >
              <X className="h-4 w-4" />
            </Button>

            <Badge variant="secondary" className="px-2 py-1">
              {selectedKeys.size} {t('keysSelected')}
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
              <TooltipContent>{commonT('delete')}</TooltipContent>
            </Tooltip>
          </div>
        </div>
      )}
      
      {/* 批量删除确认 Dialog */}
      <AlertDialog open={bulkDeleteDialogOpen} onOpenChange={setBulkDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('confirmDelete')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('confirmBulkDelete', { count: selectedKeys.size })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{commonT('cancel')}</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              onClick={confirmBulkDelete}
            >
              {commonT('delete')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
