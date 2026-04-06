'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { useRouter } from 'next/navigation'
import {
  Plus,
  Search,
  MoreHorizontal,
  Pencil,
  Trash2,
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  X,
  Database,
  FileText,
  Power,
  PowerOff,
} from 'lucide-react'
import { toast } from 'sonner'
import { knowledgeBasesApi, type KnowledgeBase, type PageData } from '@/lib/api'
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
import { KnowledgeBaseDialog } from './knowledge-base-dialog'
import { DeleteKnowledgeBaseDialog } from './delete-knowledge-base-dialog'
import { PermissionGuard, useCanPerform } from '@/components/permission-guard'

export function KnowledgeBasesClient() {
  const t = useTranslations('knowledgeBases')
  const commonT = useTranslations('common')
  const router = useRouter()
  const { canPerform } = useCanPerform()
  
  // 数据状态
  const [knowledgeBases, setKnowledgeBases] = React.useState<KnowledgeBase[]>([])
  const [isLoading, setIsLoading] = React.useState(true)
  const [page, setPage] = React.useState(1)
  const [pageSize, setPageSize] = React.useState(10)
  const [pageData, setPageData] = React.useState<PageData<KnowledgeBase> | null>(null)
  
  // 筛选状态
  const [searchQuery, setSearchQuery] = React.useState('')
  const [statusFilter, setStatusFilter] = React.useState<Set<string>>(new Set())
  
  // 选择状态
  const [selectedKbs, setSelectedKbs] = React.useState<Set<string>>(new Set())
  
  // Dialog 状态
  const [kbDialogOpen, setKbDialogOpen] = React.useState(false)
  const [deleteDialogOpen, setDeleteDialogOpen] = React.useState(false)
  const [bulkDeleteDialogOpen, setBulkDeleteDialogOpen] = React.useState(false)
  const [selectedKb, setSelectedKb] = React.useState<KnowledgeBase | null>(null)
  
  // 加载知识库列表
  const loadKnowledgeBases = React.useCallback(async () => {
    setIsLoading(true)
    try {
      const params: {
        page: number
        pageSize: number
        search?: string
        status?: string[]
      } = { page, pageSize }
      
      if (searchQuery) {
        params.search = searchQuery
      }
      
      if (statusFilter.size > 0) {
        params.status = Array.from(statusFilter)
      }
      
      const data = await knowledgeBasesApi.getKnowledgeBases(params)
      setKnowledgeBases(data.items)
      setPageData(data)
    } catch {
      // 错误已由 API 客户端处理
    } finally {
      setIsLoading(false)
    }
  }, [page, pageSize, searchQuery, statusFilter])
  
  React.useEffect(() => {
    loadKnowledgeBases()
  }, [loadKnowledgeBases])
  
  // 筛选
  const filteredKbs = knowledgeBases
  
  // 检查是否有筛选条件
  const isFiltered = searchQuery || statusFilter.size > 0
  
  // 重置筛选
  const resetFilters = () => {
    setSearchQuery('')
    setStatusFilter(new Set())
    setPage(1)
  }
  
  // 筛选条件变化时重置到第一页
  React.useEffect(() => {
    setPage(1)
  }, [searchQuery, statusFilter])
  
  // 状态选项
  const statusOptions = [
    { value: 'active', label: t('active') },
    { value: 'archived', label: t('archived') },
  ]
  
  // 计算分页信息
  const totalPages = pageData ? Math.ceil(pageData.total / pageSize) : 1
  
  // 选择操作
  const toggleSelectAll = () => {
    if (selectedKbs.size === filteredKbs.length) {
      setSelectedKbs(new Set())
    } else {
      setSelectedKbs(new Set(filteredKbs.map(kb => kb.id)))
    }
  }
  
  const toggleSelectKb = (kbId: string) => {
    const newSelected = new Set(selectedKbs)
    if (newSelected.has(kbId)) {
      newSelected.delete(kbId)
    } else {
      newSelected.add(kbId)
    }
    setSelectedKbs(newSelected)
  }
  
  // 打开创建 Dialog
  const handleCreate = () => {
    setSelectedKb(null)
    setKbDialogOpen(true)
  }
  
  // 打开编辑 Dialog
  const handleEdit = (kb: KnowledgeBase) => {
    setSelectedKb(kb)
    setKbDialogOpen(true)
  }
  
  // 打开详情页
  const handleView = (kb: KnowledgeBase) => {
    router.push(`/knowledge-bases/${kb.id}`)
  }
  
  // 打开删除 Dialog
  const handleDelete = (kb: KnowledgeBase) => {
    setSelectedKb(kb)
    setDeleteDialogOpen(true)
  }
  
  // 切换状态
  const handleToggleStatus = async (kb: KnowledgeBase) => {
    try {
      const newStatus = kb.status === 'active' ? 'archived' : 'active'
      await knowledgeBasesApi.updateKnowledgeBase(kb.id, { status: newStatus })
      toast.success(kb.status === 'active' ? t('kbDeactivated') : t('kbActivated'))
      loadKnowledgeBases()
    } catch {
      // 错误已由 API 客户端处理
    }
  }
  
  // Dialog 成功回调
  const handleDialogSuccess = () => {
    loadKnowledgeBases()
    setSelectedKbs(new Set())
  }
  
  // 批量删除
  const handleBulkDelete = () => {
    setBulkDeleteDialogOpen(true)
  }
  
  // 确认批量删除
  const confirmBulkDelete = async () => {
    try {
      const promises = Array.from(selectedKbs).map(id => knowledgeBasesApi.deleteKnowledgeBase(id))
      await Promise.all(promises)
      toast.success(t('bulkDeleted', { count: selectedKbs.size }))
      setSelectedKbs(new Set())
      loadKnowledgeBases()
    } catch {
      // 错误已由 API 客户端处理
    } finally {
      setBulkDeleteDialogOpen(false)
    }
  }
  
  // 获取状态 Badge
  const getStatusBadge = (kb: KnowledgeBase) => {
    if (kb.status === 'active') {
      return <Badge variant="default" className="bg-emerald-500/10 text-emerald-500 hover:bg-emerald-500/20">{t('active')}</Badge>
    }
    return <Badge variant="outline" className="text-muted-foreground">{t('archived')}</Badge>
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
          <PermissionGuard permission="kb:create">
            <Button onClick={handleCreate}>
              <Plus className="mr-2 h-4 w-4" />
              {t('createKb')}
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
              placeholder={t('filterKbs')}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-8 w-50 h-9"
            />
          </div>
          
          <DataTableFacetedFilter
            title={t('status')}
            options={statusOptions}
            selectedValues={statusFilter}
            onSelectionChange={setStatusFilter}
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
              <TableHead className="w-10">
                <Checkbox
                  checked={selectedKbs.size === filteredKbs.length && filteredKbs.length > 0}
                  onCheckedChange={toggleSelectAll}
                />
              </TableHead>
              <TableHead>{t('name')}</TableHead>
              <TableHead>{t('team')}</TableHead>
              <TableHead>{t('documents')}</TableHead>
              <TableHead>{t('chunks')}</TableHead>
              <TableHead>{t('status')}</TableHead>
              <TableHead>{t('createdAt')}</TableHead>
              <TableHead className="w-12"></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableRow>
                <TableCell colSpan={8} className="h-24 text-center">
                  {commonT('loading')}
                </TableCell>
              </TableRow>
            ) : filteredKbs.length === 0 ? (
              <TableRow>
                <TableCell colSpan={8} className="h-24 text-center text-muted-foreground">
                  <div className="flex flex-col items-center gap-2">
                    <Database className="h-8 w-8 text-muted-foreground/50" />
                    <p>{t('noKbs')}</p>
                    <p className="text-sm">{t('createKbHint')}</p>
                  </div>
                </TableCell>
              </TableRow>
            ) : (
              filteredKbs.map((kb) => (
                <TableRow 
                  key={kb.id} 
                  data-state={selectedKbs.has(kb.id) ? 'selected' : undefined}
                  className="cursor-pointer"
                  onClick={() => handleView(kb)}
                >
                  <TableCell onClick={(e) => e.stopPropagation()}>
                    <Checkbox
                      checked={selectedKbs.has(kb.id)}
                      onCheckedChange={() => toggleSelectKb(kb.id)}
                    />
                  </TableCell>
                  <TableCell>
                    <div className="flex flex-col">
                      <span className="font-medium">{kb.name}</span>
                      {kb.description && (
                        <span className="text-sm text-muted-foreground line-clamp-1">
                          {kb.description}
                        </span>
                      )}
                    </div>
                  </TableCell>
                  <TableCell>
                    <span className="text-muted-foreground">{kb.team?.name}</span>
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-1.5">
                      <FileText className="h-4 w-4 text-muted-foreground" />
                      <span>{kb.document_count}</span>
                    </div>
                  </TableCell>
                  <TableCell>
                    <span className="text-muted-foreground">{kb.total_chunks.toLocaleString()}</span>
                  </TableCell>
                  <TableCell>{getStatusBadge(kb)}</TableCell>
                  <TableCell className="text-muted-foreground">
                    {formatDateTime(kb.created_at)}
                  </TableCell>
                  <TableCell onClick={(e) => e.stopPropagation()}>
                    {(canPerform('kb:update') || canPerform('kb:delete')) && (
                      <DropdownMenu>
                        <DropdownMenuTrigger className="ring-offset-background focus-visible:ring-ring data-[state=open]:bg-accent inline-flex h-8 w-8 items-center justify-center rounded-md hover:bg-accent focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:outline-none">
                          <MoreHorizontal className="h-4 w-4" />
                          <span className="sr-only">{t('common.openMenu')}</span>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          {canPerform('kb:update') && (
                            <DropdownMenuItem onClick={() => handleEdit(kb)}>
                              <Pencil className="mr-2 h-4 w-4" />
                              {commonT('edit')}
                            </DropdownMenuItem>
                          )}

                          {canPerform('kb:update') && (
                            <DropdownMenuItem onClick={() => handleToggleStatus(kb)}>
                              {kb.status === 'active' ? (
                                <>
                                  <PowerOff className="mr-2 h-4 w-4" />
                                  {t('deactivate')}
                                </>
                              ) : (
                                <>
                                  <Power className="mr-2 h-4 w-4" />
                                  {t('activate')}
                                </>
                              )}
                            </DropdownMenuItem>
                          )}

                          {canPerform('kb:delete') && (
                            <>
                              <DropdownMenuSeparator />
                              <DropdownMenuItem
                                variant="destructive"
                                onClick={() => handleDelete(kb)}
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
      {pageData && pageData.total > 0 && (
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Select value={String(pageSize)} onValueChange={(v) => { if (v) { setPageSize(Number(v)); setPage(1) } }}>
              <SelectTrigger size="sm" className="w-17.5">
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
      <KnowledgeBaseDialog
        open={kbDialogOpen}
        onOpenChange={setKbDialogOpen}
        knowledgeBase={selectedKb}
        onSuccess={handleDialogSuccess}
      />
      
      {/* 删除确认 Dialog */}
      <DeleteKnowledgeBaseDialog
        open={deleteDialogOpen}
        onOpenChange={setDeleteDialogOpen}
        knowledgeBase={selectedKb}
        onSuccess={handleDialogSuccess}
      />
      
      {/* 批量操作浮动工具栏 */}
      {selectedKbs.size > 0 && canPerform('kb:delete') && (
        <div className="fixed bottom-8 left-1/2 -translate-x-1/2 z-50">
          <div className="flex items-center gap-1 rounded-lg border bg-background px-2 py-1.5 shadow-lg">
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              onClick={() => setSelectedKbs(new Set())}
            >
              <X className="h-4 w-4" />
            </Button>

            <Badge variant="secondary" className="px-2 py-1">
              {selectedKbs.size} {t('kbsSelected')}
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
              {t('confirmBulkDelete', { count: selectedKbs.size })}
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
