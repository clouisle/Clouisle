'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import {
  Plus,
  Search,
  MoreHorizontal,
  Pencil,
  Trash2,
  UsersRound,
  X,
  Crown,
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  Calendar,
} from 'lucide-react'
import { toast } from 'sonner'
import { formatDateTime } from '@/lib/utils'
import { teamsApi, type Team } from '@/lib/api/admin'
import type { PageData } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Checkbox } from '@/components/ui/checkbox'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
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
import { TeamDialog } from './team-dialog'
import { TeamDetailDialog } from './team-detail-dialog'
import { PermissionGuard, useCanPerform } from '@/components/permission-guard'
import { useUrlSearchState } from '@/hooks/use-url-search-state'

export function TeamsClient() {
  const t = useTranslations('teams')
  const commonT = useTranslations('common')
  const { canPerform } = useCanPerform()
  
  // 数据状态
  const [teams, setTeams] = React.useState<Team[]>([])
  const [isLoading, setIsLoading] = React.useState(true)
  const [page, setPage] = React.useState(1)
  const [pageSize, setPageSize] = React.useState(12)
  const [pageData, setPageData] = React.useState<PageData<Team> | null>(null)
  
  // 筛选状态
  const [searchQuery, setSearchQuery] = useUrlSearchState()
  const [debouncedSearchQuery, setDebouncedSearchQuery] = React.useState('')

  // 防抖搜索
  React.useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearchQuery(searchQuery)
      if (searchQuery !== debouncedSearchQuery) {
        setPage(1) // 搜索时重置到第一页
      }
    }, 500)
    return () => clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchQuery])

  // 选择状态
  const [selectedTeams, setSelectedTeams] = React.useState<Set<string>>(new Set())
  
  // Dialog 状态
  const [teamDialogOpen, setTeamDialogOpen] = React.useState(false)
  const [detailDialogOpen, setDetailDialogOpen] = React.useState(false)
  const [deleteDialogOpen, setDeleteDialogOpen] = React.useState(false)
  const [bulkDeleteDialogOpen, setBulkDeleteDialogOpen] = React.useState(false)
  const [selectedTeam, setSelectedTeam] = React.useState<Team | null>(null)
  
  // 加载团队列表
  const loadTeams = React.useCallback(async () => {
    setIsLoading(true)
    try {
      const data = await teamsApi.getTeams(page, pageSize, debouncedSearchQuery || undefined)
      setTeams(data.items)
      setPageData(data)
    } catch {
      // 错误已由 API 客户端处理
    } finally {
      setIsLoading(false)
    }
  }, [page, pageSize, debouncedSearchQuery])

  React.useEffect(() => {
    loadTeams()
  }, [loadTeams])

  // 可选择的团队（非默认团队）
  const selectableTeams = React.useMemo(() => {
    return teams.filter(team => !team.is_default)
  }, [teams])
  
  const hasFilters = searchQuery !== ''
  
  // 计算分页信息
  const totalPages = pageData ? Math.ceil(pageData.total / pageSize) : 1
  
  // 重置筛选
  const resetFilters = () => {
    setSearchQuery('')
  }
  
  // 全选/取消全选
  const toggleSelectAll = () => {
    if (selectedTeams.size === selectableTeams.length && selectableTeams.length > 0) {
      setSelectedTeams(new Set())
    } else {
      setSelectedTeams(new Set(selectableTeams.map(t => t.id)))
    }
  }
  
  // 切换单个选择
  const toggleSelectTeam = (teamId: string, e: React.MouseEvent) => {
    e.stopPropagation()
    const newSelected = new Set(selectedTeams)
    if (newSelected.has(teamId)) {
      newSelected.delete(teamId)
    } else {
      newSelected.add(teamId)
    }
    setSelectedTeams(newSelected)
  }
  
  // 打开创建 Dialog
  const handleCreate = () => {
    setSelectedTeam(null)
    setTeamDialogOpen(true)
  }
  
  // 打开编辑 Dialog
  const handleEdit = (team: Team, e?: React.MouseEvent) => {
    e?.stopPropagation()
    setSelectedTeam(team)
    setTeamDialogOpen(true)
  }
  
  // 打开详情 Dialog
  const handleDetail = (team: Team) => {
    setSelectedTeam(team)
    setDetailDialogOpen(true)
  }
  
  // 打开删除 Dialog
  const handleDelete = (team: Team, e?: React.MouseEvent) => {
    e?.stopPropagation()
    setSelectedTeam(team)
    setDeleteDialogOpen(true)
  }
  
  // 确认删除
  const confirmDelete = async () => {
    if (!selectedTeam) return
    try {
      await teamsApi.deleteTeam(selectedTeam.id)
      toast.success(t('teamDeleted'))
      loadTeams()
    } catch {
      // 错误已由 API 客户端处理
    } finally {
      setDeleteDialogOpen(false)
      setSelectedTeam(null)
    }
  }
  
  // 打开批量删除 Dialog
  const handleBulkDelete = () => {
    setBulkDeleteDialogOpen(true)
  }
  
  // 确认批量删除
  const confirmBulkDelete = async () => {
    try {
      const promises = Array.from(selectedTeams).map(id => teamsApi.deleteTeam(id))
      await Promise.all(promises)
      toast.success(t('bulkDeleted', { count: selectedTeams.size }))
      setSelectedTeams(new Set())
      loadTeams()
    } catch {
      // 错误已由 API 客户端处理
    } finally {
      setBulkDeleteDialogOpen(false)
    }
  }
  
  // Dialog 成功回调
  const handleDialogSuccess = () => {
    loadTeams()
    setSelectedTeams(new Set())
  }
  
  // 获取团队首字母
  const getTeamInitials = (name: string) => {
    return name.slice(0, 2).toUpperCase()
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
          <PermissionGuard permission="admin:team:create">
            <Button onClick={handleCreate}>
              <Plus className="mr-2 h-4 w-4" />
              {t('createTeam')}
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
              placeholder={t('filterTeams')}
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
        
        {selectableTeams.length > 0 && (
          <div className="flex items-center gap-2">
            <Checkbox
              checked={selectedTeams.size === selectableTeams.length && selectableTeams.length > 0}
              onCheckedChange={toggleSelectAll}
            />
            <span className="text-sm text-muted-foreground">{t('selectAll')}</span>
          </div>
        )}
      </div>
      
      {/* 团队卡片网格 */}
      {isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {[...Array(8)].map((_, i) => (
            <div key={i} className="rounded-xl border bg-card p-5 animate-pulse">
              <div className="flex items-start gap-4">
                <div className="h-12 w-12 rounded-full bg-muted" />
                <div className="flex-1 space-y-2">
                  <div className="h-5 w-24 rounded bg-muted" />
                  <div className="h-4 w-32 rounded bg-muted" />
                </div>
              </div>
              <div className="mt-4 pt-4 border-t space-y-2">
                <div className="h-4 w-20 rounded bg-muted" />
                <div className="h-4 w-28 rounded bg-muted" />
              </div>
            </div>
          ))}
        </div>
      ) : teams.length === 0 ? (
        <div className="flex flex-col items-center justify-center h-64 text-muted-foreground">
          <UsersRound className="h-12 w-12 mb-4 opacity-50" />
          <p className="text-lg font-medium">{t('noTeams')}</p>
          <p className="text-sm">{t('createTeamHint')}</p>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {teams.map((team) => (
            <div
              key={team.id}
              className={`group relative rounded-xl border bg-card p-5 cursor-pointer transition-all hover:shadow-md hover:border-primary/50 ${
                selectedTeams.has(team.id) ? 'ring-2 ring-primary border-primary' : ''
              }`}
              onClick={() => handleDetail(team)}
            >
              {/* 选择框 */}
              {!team.is_default && (
                <div
                  className="absolute top-4 left-4 z-10 opacity-0 group-hover:opacity-100 transition-opacity"
                  onClick={(e) => toggleSelectTeam(team.id, e)}
                >
                  <Checkbox
                    checked={selectedTeams.has(team.id)}
                    className="bg-background shadow-sm"
                  />
                </div>
              )}
              
              {/* 操作菜单 */}
              {(canPerform('admin:team:update') || canPerform('admin:team:delete')) && (
                <div className="absolute top-4 right-4 z-10 opacity-0 group-hover:opacity-100 transition-opacity">
                  <DropdownMenu>
                    <DropdownMenuTrigger
                      onClick={(e) => e.stopPropagation()}
                      className="ring-offset-background focus-visible:ring-ring data-[state=open]:bg-accent inline-flex h-8 w-8 items-center justify-center rounded-md hover:bg-accent focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:outline-none bg-background/90 shadow-sm"
                    >
                      <MoreHorizontal className="h-4 w-4" />
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                      {canPerform('admin:team:update') && (
                        <DropdownMenuItem onClick={(e) => { e.stopPropagation(); handleEdit(team) }}>
                          <Pencil className="mr-2 h-4 w-4" />
                          {commonT('edit')}
                        </DropdownMenuItem>
                      )}

                      {!team.is_default && canPerform('admin:team:delete') && (
                        <>
                          {canPerform('admin:team:update') && <DropdownMenuSeparator />}
                          <DropdownMenuItem
                            onClick={(e) => { e.stopPropagation(); handleDelete(team) }}
                            className="text-destructive focus:text-destructive"
                          >
                            <Trash2 className="mr-2 h-4 w-4" />
                            {commonT('delete')}
                          </DropdownMenuItem>
                        </>
                      )}
                    </DropdownMenuContent>
                  </DropdownMenu>
                </div>
              )}
              
              {/* 卡片内容 */}
              <div className="flex items-start gap-4">
                <Avatar className="h-12 w-12 ring-2 ring-background shadow-sm">
                  <AvatarImage src={team.avatar_url || undefined} />
                  <AvatarFallback className="bg-gradient-to-br from-primary to-primary/60 text-primary-foreground font-semibold">
                    {getTeamInitials(team.name)}
                  </AvatarFallback>
                </Avatar>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <h3 className="font-semibold truncate">{team.name}</h3>
                    {team.is_default && (
                      <Badge variant="secondary" className="text-xs shrink-0">
                        {t('defaultTeam')}
                      </Badge>
                    )}
                  </div>
                  <p className="text-sm text-muted-foreground truncate mt-0.5">
                    {team.description || t('noDescription')}
                  </p>
                </div>
              </div>
              
              {/* 卡片底部信息 */}
              <div className="mt-4 pt-4 border-t flex items-center justify-between text-sm text-muted-foreground">
                <div className="flex items-center gap-1.5">
                  <Crown className="h-4 w-4 text-yellow-500" />
                  <span className="truncate max-w-[100px]">{team.owner?.username || '-'}</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <Calendar className="h-4 w-4" />
                  <span>{formatDateTime(team.created_at)}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
      
      {/* 分页 */}
      {pageData && pageData.total > 0 && (
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Select value={String(pageSize)} onValueChange={(v) => { setPageSize(Number(v)); setPage(1) }}>
              <SelectTrigger size="sm" className="w-[70px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent side="top" alignItemWithTrigger={false}>
                <SelectItem value="8">8</SelectItem>
                <SelectItem value="12">12</SelectItem>
                <SelectItem value="24">24</SelectItem>
                <SelectItem value="48">48</SelectItem>
              </SelectContent>
            </Select>
            <span>{t('rowsPerPage')}</span>
          </div>
          
          <div className="flex items-center gap-4">
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
      <TeamDialog
        open={teamDialogOpen}
        onOpenChange={setTeamDialogOpen}
        team={selectedTeam}
        onSuccess={handleDialogSuccess}
      />
      
      {/* 详情 Dialog */}
      <TeamDetailDialog
        open={detailDialogOpen}
        onOpenChange={setDetailDialogOpen}
        teamId={selectedTeam?.id || null}
        onEdit={() => {
          setDetailDialogOpen(false)
          setTeamDialogOpen(true)
        }}
        onDeleted={handleDialogSuccess}
      />
      
      {/* 删除确认 Dialog */}
      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('confirmDelete')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('deleteTeamConfirm', { name: selectedTeam?.name || '' })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{commonT('cancel')}</AlertDialogCancel>
            <AlertDialogAction variant="destructive" onClick={confirmDelete}>
              {commonT('delete')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
      
      {/* 批量操作浮动工具栏 */}
      {selectedTeams.size > 0 && canPerform('admin:team:delete') && (
        <div className="fixed bottom-8 left-1/2 -translate-x-1/2 z-50">
          <div className="flex items-center gap-1 rounded-lg border bg-background px-2 py-1.5 shadow-lg">
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              onClick={() => setSelectedTeams(new Set())}
            >
              <X className="h-4 w-4" />
            </Button>

            <Badge variant="secondary" className="px-2 py-1">
              {selectedTeams.size} {t('teamsSelected')}
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
              {t('confirmBulkDelete', { count: selectedTeams.size })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{commonT('cancel')}</AlertDialogCancel>
            <AlertDialogAction variant="destructive" onClick={confirmBulkDelete}>
              {commonT('delete')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
