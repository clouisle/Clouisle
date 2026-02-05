'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import {
  Plus,
  Search,
  MoreHorizontal,
  Pencil,
  Trash2,
  UserCheck,
  UserX,
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  Shield,
  X,
  Mail,
  UserPlus,
  UserMinus,
  Link as LinkIcon,
} from 'lucide-react'
import { toast } from 'sonner'
import { usersApi, rolesApi, type User, type PageData, type UserStats } from '@/lib/api'
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
import { UserDialog } from './user-dialog'
import { DeleteUserDialog } from './delete-user-dialog'
import { SendEmailDialog } from './send-email-dialog'
import { PermissionGuard, useCanPerform } from '@/components/permission-guard'

type Role = {
  id: string
  name: string
  description: string | null
  is_system_role: boolean
}

export function UsersClient() {
  const t = useTranslations('users')
  const commonT = useTranslations('common')
  const { canPerform } = useCanPerform()
  
  // 数据状态
  const [users, setUsers] = React.useState<User[]>([])
  const [roles, setRoles] = React.useState<Role[]>([])
  const [stats, setStats] = React.useState<UserStats | null>(null)
  const [isLoading, setIsLoading] = React.useState(true)
  const [page, setPage] = React.useState(1)
  const [pageSize, setPageSize] = React.useState(10)
  const [pageData, setPageData] = React.useState<PageData<User> | null>(null)
  
  // 筛选状态
  const [searchQuery, setSearchQuery] = React.useState('')
  const [statusFilter, setStatusFilter] = React.useState<Set<string>>(new Set())
  const [roleFilter, setRoleFilter] = React.useState<Set<string>>(new Set())
  
  // 选择状态
  const [selectedUsers, setSelectedUsers] = React.useState<Set<string>>(new Set())
  
  // Dialog 状态
  const [userDialogOpen, setUserDialogOpen] = React.useState(false)
  const [deleteDialogOpen, setDeleteDialogOpen] = React.useState(false)
  const [bulkDeleteDialogOpen, setBulkDeleteDialogOpen] = React.useState(false)
  const [emailDialogOpen, setEmailDialogOpen] = React.useState(false)
  const [selectedUser, setSelectedUser] = React.useState<User | null>(null)
  
  // 加载角色列表
  React.useEffect(() => {
    const loadRoles = async () => {
      try {
        const data = await rolesApi.getRoles(1, 100)
        setRoles(data.items)
      } catch {
        // 忽略错误
      }
    }
    loadRoles()
  }, [])

  // 加载用户统计
  const loadStats = React.useCallback(async () => {
    try {
      const data = await usersApi.getStats()
      setStats(data)
    } catch {
      // 忽略错误
    }
  }, [])
  
  // 加载用户列表
  const loadUsers = React.useCallback(async () => {
    setIsLoading(true)
    try {
      const data = await usersApi.getUsers({ page, pageSize })
      setUsers(data.items)
      setPageData(data)
    } catch {
      // 错误已由 API 客户端处理
    } finally {
      setIsLoading(false)
    }
  }, [page, pageSize])
  
  React.useEffect(() => {
    loadUsers()
    loadStats()
  }, [loadUsers, loadStats])
  
  // 筛选用户
  const filteredUsers = React.useMemo(() => {
    return users.filter(user => {
      // 搜索筛选
      if (searchQuery) {
        const query = searchQuery.toLowerCase()
        if (!user.username.toLowerCase().includes(query) &&
            !user.email.toLowerCase().includes(query)) {
          return false
        }
      }
      
      // 状态筛选
      if (statusFilter.size > 0) {
        const isActive = user.is_active
        if (!statusFilter.has(isActive ? 'active' : 'inactive')) {
          return false
        }
      }
      
      // 角色筛选
      if (roleFilter.size > 0) {
        const hasMatchingRole = user.roles.some(role => roleFilter.has(role.name))
        if (!hasMatchingRole) return false
      }
      
      return true
    })
  }, [users, searchQuery, statusFilter, roleFilter])
  
  // 检查是否有筛选条件
  const isFiltered = searchQuery || statusFilter.size > 0 || roleFilter.size > 0
  
  // 重置所有筛选
  const resetFilters = () => {
    setSearchQuery('')
    setStatusFilter(new Set())
    setRoleFilter(new Set())
  }
  
  // 状态选项
  const statusOptions = [
    { value: 'active', label: t('active') },
    { value: 'inactive', label: t('inactive') },
  ]
  
  // 角色选项（包含用户数量统计）
  const roleOptions = React.useMemo(() => {
    const roleCounts = new Map<string, number>()
    
    // 统计各角色
    users.forEach(user => {
      user.roles.forEach(role => {
        roleCounts.set(role.name, (roleCounts.get(role.name) || 0) + 1)
      })
    })
    
    return roles.map(role => ({
      value: role.name,
      label: role.name,
      icon: <Shield className="h-4 w-4" />,
      count: roleCounts.get(role.name) || 0,
    }))
  }, [roles, users])
  
  // 计算分页信息
  const totalPages = pageData ? Math.ceil(pageData.total / pageSize) : 1
  
  // 选择操作
  const toggleSelectAll = () => {
    if (selectedUsers.size === filteredUsers.length) {
      setSelectedUsers(new Set())
    } else {
      setSelectedUsers(new Set(filteredUsers.map(u => u.id)))
    }
  }
  
  const toggleSelectUser = (userId: string) => {
    const newSelected = new Set(selectedUsers)
    if (newSelected.has(userId)) {
      newSelected.delete(userId)
    } else {
      newSelected.add(userId)
    }
    setSelectedUsers(newSelected)
  }
  
  // 打开创建 Dialog
  const handleCreate = () => {
    setSelectedUser(null)
    setUserDialogOpen(true)
  }
  
  // 打开编辑 Dialog
  const handleEdit = (user: User) => {
    setSelectedUser(user)
    setUserDialogOpen(true)
  }
  
  // 打开删除 Dialog
  const handleDelete = (user: User) => {
    setSelectedUser(user)
    setDeleteDialogOpen(true)
  }
  
  // 切换用户状态
  const handleToggleStatus = async (user: User) => {
    try {
      if (user.is_active) {
        await usersApi.deactivateUser(user.id)
        toast.success(t('userDeactivated'))
      } else {
        await usersApi.activateUser(user.id)
        toast.success(t('userActivated'))
      }
      loadUsers()
      loadStats()
    } catch {
      // 错误已由 API 客户端处理
    }
  }
  
  // Dialog 成功回调
  const handleDialogSuccess = () => {
    loadUsers()
    loadStats()
    setSelectedUsers(new Set())
  }
  
  // 批量发送邮件
  const handleBulkEmail = () => {
    setEmailDialogOpen(true)
  }

  // 批量激活
  const handleBulkActivate = async () => {
    try {
      const promises = Array.from(selectedUsers).map(id => usersApi.activateUser(id))
      await Promise.all(promises)
      toast.success(t('bulkActivated', { count: selectedUsers.size }))
      setSelectedUsers(new Set())
      loadUsers()
      loadStats()
    } catch {
      // 错误已由 API 客户端处理
    }
  }
  
  // 批量停用
  const handleBulkDeactivate = async () => {
    try {
      const promises = Array.from(selectedUsers).map(id => usersApi.deactivateUser(id))
      await Promise.all(promises)
      toast.success(t('bulkDeactivated', { count: selectedUsers.size }))
      setSelectedUsers(new Set())
      loadUsers()
      loadStats()
    } catch {
      // 错误已由 API 客户端处理
    }
  }
  
  // 批量删除
  const handleBulkDelete = () => {
    setBulkDeleteDialogOpen(true)
  }
  
  // 确认批量删除
  const confirmBulkDelete = async () => {
    try {
      const promises = Array.from(selectedUsers).map(id => usersApi.deleteUser(id))
      await Promise.all(promises)
      toast.success(t('bulkDeleted', { count: selectedUsers.size }))
      setSelectedUsers(new Set())
      loadUsers()
      loadStats()
    } catch {
      // 错误已由 API 客户端处理
    } finally {
      setBulkDeleteDialogOpen(false)
    }
  }
  
  // 获取状态 Badge
  const getStatusBadge = (user: User) => {
    if (user.is_active) {
      return <Badge variant="default" className="bg-emerald-500/10 text-emerald-500 hover:bg-emerald-500/20">{t('active')}</Badge>
    }
    return <Badge variant="outline" className="text-muted-foreground">{t('inactive')}</Badge>
  }
  
  // 获取用户主要角色
  const getPrimaryRole = (user: User) => {
    if (user.roles.length > 0) return user.roles[0].name
    return '-'
  }
  
  return (
    <div className="flex flex-col gap-6">
      {/* 待审核用户提示 */}
      {stats && stats.pending > 0 && (
        <div className="flex items-center gap-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 dark:border-amber-900/50 dark:bg-amber-900/20">
          <UserCheck className="h-5 w-5 text-amber-600 dark:text-amber-500" />
          <div className="flex-1">
            <p className="text-sm font-medium text-amber-800 dark:text-amber-200">
              {t('pendingApprovalNotice', { count: stats.pending })}
            </p>
          </div>
          <Button
            variant="outline"
            size="sm"
            className="border-amber-300 bg-transparent hover:bg-amber-100 dark:border-amber-800 dark:hover:bg-amber-900/40"
            onClick={() => setStatusFilter(new Set(['inactive']))}
          >
            {t('viewPending')}
          </Button>
        </div>
      )}

      {/* 页头 */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold">{t('title')}</h1>
          <p className="text-muted-foreground">{t('description')}</p>
        </div>
        <div className="flex items-center gap-2">
          <PermissionGuard permission="user:create">
            <Button onClick={handleCreate}>
              <Plus className="mr-2 h-4 w-4" />
              {t('createUser')}
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
              placeholder={t('filterUsers')}
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
            title={t('role')}
            options={roleOptions}
            selectedValues={roleFilter}
            onSelectionChange={setRoleFilter}
            searchable
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
                  checked={selectedUsers.size === filteredUsers.length && filteredUsers.length > 0}
                  onCheckedChange={toggleSelectAll}
                />
              </TableHead>
              <TableHead>{t('username')}</TableHead>
              <TableHead>Email</TableHead>
              <TableHead>SSO</TableHead>
              <TableHead>{t('status')}</TableHead>
              <TableHead>{t('role')}</TableHead>
              <TableHead>{t('createdAt')}</TableHead>
              <TableHead className="w-[50px]"></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableRow>
                <TableCell colSpan={8} className="h-24 text-center">
                  {commonT('loading')}
                </TableCell>
              </TableRow>
            ) : filteredUsers.length === 0 ? (
              <TableRow>
                <TableCell colSpan={8} className="h-24 text-center text-muted-foreground">
                  {t('noUsers')}
                </TableCell>
              </TableRow>
            ) : (
              filteredUsers.map((user) => (
                <TableRow key={user.id} data-state={selectedUsers.has(user.id) ? 'selected' : undefined}>
                  <TableCell>
                    <Checkbox
                      checked={selectedUsers.has(user.id)}
                      onCheckedChange={() => toggleSelectUser(user.id)}
                    />
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <span className="font-medium">{user.username}</span>
                      {user.is_superuser && (
                        <Badge variant="secondary">{t('superuser')}</Badge>
                      )}
                    </div>
                  </TableCell>
                  <TableCell className="text-muted-foreground">{user.email}</TableCell>
                  <TableCell>
                    {user.sso_connections && user.sso_connections.length > 0 ? (
                      <div className="flex items-center gap-1">
                        {user.sso_connections.map((conn) => (
                          <Tooltip key={conn.id}>
                            <TooltipTrigger>
                              {conn.provider_icon_url ? (
                                <img
                                  src={conn.provider_icon_url}
                                  alt={conn.provider_display_name}
                                  className="h-4 w-4 rounded"
                                />
                              ) : (
                                <LinkIcon className="h-4 w-4 text-muted-foreground" />
                              )}
                            </TooltipTrigger>
                            <TooltipContent>
                              <div className="text-xs">
                                <p className="font-medium">{conn.provider_display_name}</p>
                                {conn.provider_email && (
                                  <p className="text-muted-foreground">{conn.provider_email}</p>
                                )}
                              </div>
                            </TooltipContent>
                          </Tooltip>
                        ))}
                      </div>
                    ) : (
                      <span className="text-muted-foreground">-</span>
                    )}
                  </TableCell>
                  <TableCell>{getStatusBadge(user)}</TableCell>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <Shield className="h-4 w-4 text-muted-foreground" />
                      <span>{getPrimaryRole(user)}</span>
                    </div>
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {formatDateTime(user.created_at)}
                  </TableCell>
                  <TableCell>
                    <DropdownMenu>
                      <DropdownMenuTrigger className="ring-offset-background focus-visible:ring-ring data-[state=open]:bg-accent inline-flex h-8 w-8 items-center justify-center rounded-md hover:bg-accent focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:outline-none">
                        <MoreHorizontal className="h-4 w-4" />
                        <span className="sr-only">Open menu</span>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        {canPerform('user:update') && (
                          <DropdownMenuItem onClick={() => handleEdit(user)}>
                            <Pencil className="mr-2 h-4 w-4" />
                            {commonT('edit')}
                          </DropdownMenuItem>
                        )}

                        {canPerform('user:update') && (
                          <DropdownMenuItem onClick={() => handleToggleStatus(user)}>
                            {user.is_active ? (
                              <>
                                <UserX className="mr-2 h-4 w-4" />
                                {t('deactivate')}
                              </>
                            ) : (
                              <>
                                <UserCheck className="mr-2 h-4 w-4" />
                                {t('activate')}
                              </>
                            )}
                          </DropdownMenuItem>
                        )}

                        {canPerform('user:delete') && (
                          <>
                            <DropdownMenuSeparator />
                            <DropdownMenuItem
                              onClick={() => handleDelete(user)}
                              className="text-destructive focus:text-destructive"
                            >
                              <Trash2 className="mr-2 h-4 w-4" />
                              {commonT('delete')}
                            </DropdownMenuItem>
                          </>
                        )}
                      </DropdownMenuContent>
                    </DropdownMenu>
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
      <UserDialog
        open={userDialogOpen}
        onOpenChange={setUserDialogOpen}
        user={selectedUser}
        onSuccess={handleDialogSuccess}
      />
      
      {/* 删除确认 Dialog */}
      <DeleteUserDialog
        open={deleteDialogOpen}
        onOpenChange={setDeleteDialogOpen}
        user={selectedUser}
        onSuccess={handleDialogSuccess}
      />
      
      {/* 发送邮件 Dialog */}
      <SendEmailDialog
        open={emailDialogOpen}
        onOpenChange={setEmailDialogOpen}
        users={users.filter(u => selectedUsers.has(u.id))}
        onSuccess={() => setSelectedUsers(new Set())}
      />
      
      {/* 批量操作浮动工具栏 */}
      {selectedUsers.size > 0 && (
        <div className="fixed bottom-8 left-1/2 -translate-x-1/2 z-50">
          <div className="flex items-center gap-1 rounded-lg border bg-background px-2 py-1.5 shadow-lg">
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              onClick={() => setSelectedUsers(new Set())}
            >
              <X className="h-4 w-4" />
            </Button>

            <Badge variant="secondary" className="px-2 py-1">
              {selectedUsers.size} {t('usersSelected')}
            </Badge>

            <Tooltip>
              <TooltipTrigger
                onClick={handleBulkEmail}
                render={
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8"
                  >
                    <Mail className="h-4 w-4" />
                  </Button>
                }
              />
              <TooltipContent>{t('sendEmail')}</TooltipContent>
            </Tooltip>

            {canPerform('user:update') && (
              <>
                <Tooltip>
                  <TooltipTrigger
                    onClick={handleBulkActivate}
                    render={
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8"
                      >
                        <UserPlus className="h-4 w-4" />
                      </Button>
                    }
                  />
                  <TooltipContent>{t('activate')}</TooltipContent>
                </Tooltip>

                <Tooltip>
                  <TooltipTrigger
                    onClick={handleBulkDeactivate}
                    render={
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8"
                      >
                        <UserMinus className="h-4 w-4" />
                      </Button>
                    }
                  />
                  <TooltipContent>{t('deactivate')}</TooltipContent>
                </Tooltip>
              </>
            )}

            {canPerform('user:delete') && (
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
            )}
          </div>
        </div>
      )}
      
      {/* 批量删除确认 Dialog */}
      <AlertDialog open={bulkDeleteDialogOpen} onOpenChange={setBulkDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('confirmDelete')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('confirmBulkDelete', { count: selectedUsers.size })}
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
