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
  X,
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
} from 'lucide-react'
import { toast } from 'sonner'
import { permissionsApi, type Permission, type PageData } from '@/lib/api'
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
import { PermissionDialog } from './permission-dialog'
import { DeletePermissionDialog } from './delete-permission-dialog'

export function PermissionsClient() {
  const t = useTranslations('permissions')
  const commonT = useTranslations('common')
  
  // 数据状态
  const [permissions, setPermissions] = React.useState<Permission[]>([])
  const [isLoading, setIsLoading] = React.useState(true)
  const [page, setPage] = React.useState(1)
  const [pageSize, setPageSize] = React.useState(10)
  const [pageData, setPageData] = React.useState<PageData<Permission> | null>(null)
  
  // 筛选状态
  const [searchQuery, setSearchQuery] = React.useState('')
  const [scopeFilter, setScopeFilter] = React.useState<Set<string>>(new Set())
  
  // 选择状态
  const [selectedPermissions, setSelectedPermissions] = React.useState<Set<string>>(new Set())
  
  // Dialog 状态
  const [permissionDialogOpen, setPermissionDialogOpen] = React.useState(false)
  const [deleteDialogOpen, setDeleteDialogOpen] = React.useState(false)
  const [bulkDeleteDialogOpen, setBulkDeleteDialogOpen] = React.useState(false)
  const [selectedPermission, setSelectedPermission] = React.useState<Permission | null>(null)
  
  // 加载权限列表
  const loadPermissions = React.useCallback(async () => {
    setIsLoading(true)
    try {
      const data = await permissionsApi.getPermissions(page, pageSize)
      setPermissions(data.items)
      setPageData(data)
    } catch {
      // 错误已由 API 客户端处理
    } finally {
      setIsLoading(false)
    }
  }, [page, pageSize])
  
  React.useEffect(() => {
    loadPermissions()
  }, [loadPermissions])
  
  // 过滤权限
  const filteredPermissions = React.useMemo(() => {
    return permissions.filter(permission => {
      // 搜索过滤
      if (searchQuery) {
        const query = searchQuery.toLowerCase()
        const matchCode = permission.code.toLowerCase().includes(query)
        const matchDesc = permission.description?.toLowerCase().includes(query) ?? false
        if (!matchCode && !matchDesc) return false
      }
      // Scope 过滤
      if (scopeFilter.size > 0 && !scopeFilter.has(permission.scope)) return false
      return true
    })
  }, [permissions, searchQuery, scopeFilter])
  
  // 检查是否有筛选条件
  const isFiltered = searchQuery || scopeFilter.size > 0
  
  // 重置筛选
  const resetFilters = () => {
    setSearchQuery('')
    setScopeFilter(new Set())
  }
  
  // Scope 选项（包含数量统计）
  const scopeOptions = React.useMemo(() => {
    const scopeCounts = new Map<string, number>()
    
    permissions.forEach(permission => {
      scopeCounts.set(permission.scope, (scopeCounts.get(permission.scope) || 0) + 1)
    })
    
    return Array.from(scopeCounts.entries())
      .sort((a, b) => a[0].localeCompare(b[0]))
      .map(([scope, count]) => ({
        value: scope,
        label: scope,
        count,
      }))
  }, [permissions])
  
  // 可选择的权限（排除通配符权限）
  const selectablePermissions = React.useMemo(() => {
    return filteredPermissions.filter(p => p.code !== '*')
  }, [filteredPermissions])
  
  // 分页计算
  const totalPages = pageData ? Math.ceil(pageData.total / pageSize) : 1
  
  // 全选/取消全选
  const toggleSelectAll = () => {
    if (selectedPermissions.size === selectablePermissions.length && selectablePermissions.length > 0) {
      setSelectedPermissions(new Set())
    } else {
      setSelectedPermissions(new Set(selectablePermissions.map(p => p.id)))
    }
  }
  
  // 切换单个选择
  const toggleSelectPermission = (permissionId: string) => {
    const newSelected = new Set(selectedPermissions)
    if (newSelected.has(permissionId)) {
      newSelected.delete(permissionId)
    } else {
      newSelected.add(permissionId)
    }
    setSelectedPermissions(newSelected)
  }
  
  // 打开创建 Dialog
  const handleCreate = () => {
    setSelectedPermission(null)
    setPermissionDialogOpen(true)
  }
  
  // 打开编辑 Dialog
  const handleEdit = (permission: Permission) => {
    setSelectedPermission(permission)
    setPermissionDialogOpen(true)
  }
  
  // 打开删除 Dialog
  const handleDelete = (permission: Permission) => {
    setSelectedPermission(permission)
    setDeleteDialogOpen(true)
  }
  
  // 打开批量删除 Dialog
  const handleBulkDelete = () => {
    setBulkDeleteDialogOpen(true)
  }
  
  // 确认批量删除
  const confirmBulkDelete = async () => {
    try {
      const promises = Array.from(selectedPermissions).map(id => permissionsApi.deletePermission(id))
      await Promise.all(promises)
      toast.success(t('bulkDeleted', { count: selectedPermissions.size }))
      setSelectedPermissions(new Set())
      loadPermissions()
    } catch {
      // 错误已由 API 客户端处理
    } finally {
      setBulkDeleteDialogOpen(false)
    }
  }
  
  // Dialog 成功回调
  const handleDialogSuccess = () => {
    loadPermissions()
    setSelectedPermissions(new Set())
  }
  
  // 判断是否为系统权限（通配符）
  const isSystemPermission = (permission: Permission) => permission.code === '*'
  
  return (
    <div className="flex flex-col gap-6">
      {/* 页头 */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold">{t('title')}</h1>
          <p className="text-muted-foreground">{t('description')}</p>
        </div>
        <div className="flex items-center gap-2">
          <Button onClick={handleCreate}>
            <Plus className="mr-2 h-4 w-4" />
            {t('createPermission')}
          </Button>
        </div>
      </div>
      
      {/* 筛选栏 */}
      <div className="flex items-center justify-between gap-4">
        <div className="flex flex-1 items-center gap-2">
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              placeholder={t('filterPermissions')}
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
          
          {isFiltered && (
            <Button
              variant="ghost"
              onClick={resetFilters}
              className="h-9 px-2 lg:px-3"
            >
              {commonT('reset')}
              <X className="ml-2 h-4 w-4" />
            </Button>
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
                  checked={selectedPermissions.size === selectablePermissions.length && selectablePermissions.length > 0}
                  onCheckedChange={toggleSelectAll}
                  disabled={selectablePermissions.length === 0}
                />
              </TableHead>
              <TableHead>{t('code')}</TableHead>
              <TableHead>{t('scope')}</TableHead>
              <TableHead>{t('permissionDescription')}</TableHead>
              <TableHead className="w-[50px]"></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableRow>
                <TableCell colSpan={5} className="h-24 text-center">
                  {commonT('loading')}
                </TableCell>
              </TableRow>
            ) : filteredPermissions.length === 0 ? (
              <TableRow>
                <TableCell colSpan={5} className="h-24 text-center text-muted-foreground">
                  {t('noPermissions')}
                </TableCell>
              </TableRow>
            ) : (
              filteredPermissions.map((permission) => (
                <TableRow key={permission.id} data-state={selectedPermissions.has(permission.id) ? 'selected' : undefined}>
                  <TableCell>
                    <Checkbox
                      checked={selectedPermissions.has(permission.id)}
                      onCheckedChange={() => toggleSelectPermission(permission.id)}
                      disabled={isSystemPermission(permission)}
                    />
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <Key className="h-4 w-4 text-muted-foreground" />
                      <code className="text-sm bg-muted px-1.5 py-0.5 rounded font-medium">
                        {permission.code}
                      </code>
                      {isSystemPermission(permission) && (
                        <Badge variant="secondary" className="text-xs">
                          {t('systemPermission')}
                        </Badge>
                      )}
                    </div>
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline" className="text-xs capitalize">
                      {permission.scope}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-muted-foreground max-w-[300px] truncate">
                    {permission.description || '-'}
                  </TableCell>
                  <TableCell>
                    {!isSystemPermission(permission) && (
                      <DropdownMenu>
                        <DropdownMenuTrigger className="ring-offset-background focus-visible:ring-ring data-[state=open]:bg-accent inline-flex h-8 w-8 items-center justify-center rounded-md hover:bg-accent focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:outline-none">
                          <MoreHorizontal className="h-4 w-4" />
                          <span className="sr-only">Open menu</span>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem onClick={() => handleEdit(permission)}>
                            <Pencil className="mr-2 h-4 w-4" />
                            {commonT('edit')}
                          </DropdownMenuItem>
                          
                          <DropdownMenuSeparator />
                          
                          <DropdownMenuItem 
                            onClick={() => handleDelete(permission)}
                            className="text-destructive focus:text-destructive"
                          >
                            <Trash2 className="mr-2 h-4 w-4" />
                            {commonT('delete')}
                          </DropdownMenuItem>
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
      <PermissionDialog
        open={permissionDialogOpen}
        onOpenChange={setPermissionDialogOpen}
        permission={selectedPermission}
        onSuccess={handleDialogSuccess}
      />
      
      {/* 删除确认 Dialog */}
      <DeletePermissionDialog
        open={deleteDialogOpen}
        onOpenChange={setDeleteDialogOpen}
        permission={selectedPermission}
        onSuccess={handleDialogSuccess}
      />
      
      {/* 批量操作浮动工具栏 */}
      {selectedPermissions.size > 0 && (
        <div className="fixed bottom-8 left-1/2 -translate-x-1/2 z-50">
          <div className="flex items-center gap-1 rounded-lg border bg-background px-2 py-1.5 shadow-lg">
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              onClick={() => setSelectedPermissions(new Set())}
            >
              <X className="h-4 w-4" />
            </Button>
            
            <Badge variant="secondary" className="px-2 py-1">
              {selectedPermissions.size} {t('permissionsSelected')}
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
              {t('confirmBulkDelete', { count: selectedPermissions.size })}
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
