'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import {
  Plus,
  Search,
  MoreHorizontal,
  Pencil,
  Trash2,
  Shield,
  ShieldCheck,
  X,
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
} from 'lucide-react'
import { toast } from 'sonner'
import { rolesApi, type Role } from '@/lib/api/admin/roles'
import type { PageData } from '@/lib/api/users'
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
import { RoleDialog } from './role-dialog'
import { DeleteRoleDialog } from './delete-role-dialog'
import { PermissionGuard, useCanPerform } from '@/components/permission-guard'

export function RolesClient() {
  const t = useTranslations('roles')
  const commonT = useTranslations('common')
  const { canPerform } = useCanPerform()
  
  // 数据状态
  const [roles, setRoles] = React.useState<Role[]>([])
  const [isLoading, setIsLoading] = React.useState(true)
  const [page, setPage] = React.useState(1)
  const [pageSize, setPageSize] = React.useState(10)
  const [pageData, setPageData] = React.useState<PageData<Role> | null>(null)
  
  // 筛选状态
  const [searchQuery, setSearchQuery] = React.useState('')
  
  // 选择状态
  const [selectedRoles, setSelectedRoles] = React.useState<Set<string>>(new Set())
  
  // Dialog 状态
  const [roleDialogOpen, setRoleDialogOpen] = React.useState(false)
  const [deleteDialogOpen, setDeleteDialogOpen] = React.useState(false)
  const [bulkDeleteDialogOpen, setBulkDeleteDialogOpen] = React.useState(false)
  const [selectedRole, setSelectedRole] = React.useState<Role | null>(null)
  
  // 加载角色列表
  const loadRoles = React.useCallback(async () => {
    setIsLoading(true)
    try {
      const data = await rolesApi.getRoles(page, pageSize)
      setRoles(data.items)
      setPageData(data)
    } catch {
      // 错误已由 API 客户端处理
    } finally {
      setIsLoading(false)
    }
  }, [page, pageSize])
  
  React.useEffect(() => {
    loadRoles()
  }, [loadRoles])
  
  // 过滤角色
  const filteredRoles = React.useMemo(() => {
    return roles.filter(role => {
      if (searchQuery) {
        const query = searchQuery.toLowerCase()
        const matchName = role.name.toLowerCase().includes(query)
        const matchDesc = role.description?.toLowerCase().includes(query) ?? false
        if (!matchName && !matchDesc) return false
      }
      return true
    })
  }, [roles, searchQuery])
  
  // 可选择的角色（非系统角色）
  const selectableRoles = React.useMemo(() => {
    return filteredRoles.filter(role => !role.is_system_role)
  }, [filteredRoles])
  
  // 分页计算
  const totalPages = pageData ? Math.ceil(pageData.total / pageSize) : 1
  
  // 重置筛选
  const resetFilters = () => {
    setSearchQuery('')
  }
  
  const hasFilters = searchQuery !== ''
  
  // 全选/取消全选（仅非系统角色）
  const toggleSelectAll = () => {
    if (selectedRoles.size === selectableRoles.length && selectableRoles.length > 0) {
      setSelectedRoles(new Set())
    } else {
      setSelectedRoles(new Set(selectableRoles.map(r => r.id)))
    }
  }
  
  // 切换单个选择
  const toggleSelectRole = (roleId: string) => {
    const newSelected = new Set(selectedRoles)
    if (newSelected.has(roleId)) {
      newSelected.delete(roleId)
    } else {
      newSelected.add(roleId)
    }
    setSelectedRoles(newSelected)
  }
  
  // 打开创建 Dialog
  const handleCreate = () => {
    setSelectedRole(null)
    setRoleDialogOpen(true)
  }
  
  // 打开编辑 Dialog
  const handleEdit = (role: Role) => {
    setSelectedRole(role)
    setRoleDialogOpen(true)
  }
  
  // 打开删除 Dialog
  const handleDelete = (role: Role) => {
    setSelectedRole(role)
    setDeleteDialogOpen(true)
  }
  
  // 打开批量删除 Dialog
  const handleBulkDelete = () => {
    setBulkDeleteDialogOpen(true)
  }
  
  // 确认批量删除
  const confirmBulkDelete = async () => {
    try {
      const promises = Array.from(selectedRoles).map(id => rolesApi.deleteRole(id))
      await Promise.all(promises)
      toast.success(t('bulkDeleted', { count: selectedRoles.size }))
      setSelectedRoles(new Set())
      loadRoles()
    } catch {
      // 错误已由 API 客户端处理
    } finally {
      setBulkDeleteDialogOpen(false)
    }
  }
  
  // Dialog 成功回调
  const handleDialogSuccess = () => {
    loadRoles()
    setSelectedRoles(new Set())
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
          <PermissionGuard permission="role:create">
            <Button onClick={handleCreate}>
              <Plus className="mr-2 h-4 w-4" />
              {t('createRole')}
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
              placeholder={t('filterRoles')}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-8 w-[200px] h-9"
            />
          </div>
          
          {hasFilters && (
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
                  checked={selectedRoles.size === selectableRoles.length && selectableRoles.length > 0}
                  onCheckedChange={toggleSelectAll}
                  disabled={selectableRoles.length === 0}
                />
              </TableHead>
              <TableHead>{t('roleName')}</TableHead>
              <TableHead>{t('description')}</TableHead>
              <TableHead>{t('permissions')}</TableHead>
              <TableHead>{t('type')}</TableHead>
              <TableHead className="w-[50px]"></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableRow>
                <TableCell colSpan={6} className="h-24 text-center">
                  {commonT('loading')}
                </TableCell>
              </TableRow>
            ) : filteredRoles.length === 0 ? (
              <TableRow>
                <TableCell colSpan={6} className="h-24 text-center text-muted-foreground">
                  {t('noRoles')}
                </TableCell>
              </TableRow>
            ) : (
              filteredRoles.map((role) => (
                <TableRow key={role.id} data-state={selectedRoles.has(role.id) ? 'selected' : undefined}>
                  <TableCell>
                    <Checkbox
                      checked={selectedRoles.has(role.id)}
                      onCheckedChange={() => toggleSelectRole(role.id)}
                      disabled={role.is_system_role}
                    />
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <Shield className="h-4 w-4 text-muted-foreground" />
                      <span className="font-medium">{role.name}</span>
                    </div>
                  </TableCell>
                  <TableCell className="text-muted-foreground max-w-[300px] truncate">
                    {role.description || '-'}
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-1">
                      <Badge variant="outline" className="text-xs">
                        {role.permissions?.length || 0} {t('permissionCount')}
                      </Badge>
                    </div>
                  </TableCell>
                  <TableCell>
                    {role.is_system_role ? (
                      <Badge variant="secondary" className="text-xs">
                        <ShieldCheck className="mr-1 h-3 w-3" />
                        {t('systemRole')}
                      </Badge>
                    ) : (
                      <Badge variant="outline" className="text-xs text-muted-foreground">
                        {t('customRole')}
                      </Badge>
                    )}
                  </TableCell>
                  <TableCell>
                    {(canPerform('role:update') || canPerform('role:delete')) && (
                      <DropdownMenu>
                        <DropdownMenuTrigger className="ring-offset-background focus-visible:ring-ring data-[state=open]:bg-accent inline-flex h-8 w-8 items-center justify-center rounded-md hover:bg-accent focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:outline-none">
                          <MoreHorizontal className="h-4 w-4" />
                          <span className="sr-only">{t('common.openMenu')}</span>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          {canPerform('role:update') && (
                            <DropdownMenuItem onClick={() => handleEdit(role)}>
                              <Pencil className="mr-2 h-4 w-4" />
                              {commonT('edit')}
                            </DropdownMenuItem>
                          )}

                          {!role.is_system_role && canPerform('role:delete') && (
                            <>
                              {canPerform('role:update') && <DropdownMenuSeparator />}
                              <DropdownMenuItem
                                onClick={() => handleDelete(role)}
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
      <RoleDialog
        open={roleDialogOpen}
        onOpenChange={setRoleDialogOpen}
        role={selectedRole}
        onSuccess={handleDialogSuccess}
      />
      
      {/* 删除确认 Dialog */}
      <DeleteRoleDialog
        open={deleteDialogOpen}
        onOpenChange={setDeleteDialogOpen}
        role={selectedRole}
        onSuccess={handleDialogSuccess}
      />
      
      {/* 批量操作浮动工具栏 */}
      {selectedRoles.size > 0 && canPerform('role:delete') && (
        <div className="fixed bottom-8 left-1/2 -translate-x-1/2 z-50">
          <div className="flex items-center gap-1 rounded-lg border bg-background px-2 py-1.5 shadow-lg">
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              onClick={() => setSelectedRoles(new Set())}
            >
              <X className="h-4 w-4" />
            </Button>

            <Badge variant="secondary" className="px-2 py-1">
              {selectedRoles.size} {t('rolesSelected')}
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
              {t('confirmBulkDelete', { count: selectedRoles.size })}
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
