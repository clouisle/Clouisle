'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
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
  Star,
  Power,
  PowerOff,
  TestTube,
} from 'lucide-react'
import { toast } from 'sonner'
import { modelsApi, type Model } from '@/lib/api/admin/models'
import { modelsApi as platformModelsApi } from '@/lib/api/models'
import type { PageData, ProviderInfo, ModelTypeInfo } from '@/lib/api/models'
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
import { ModelDialog } from './model-dialog'
import { DeleteModelDialog } from './delete-model-dialog'
import { PermissionGuard, useCanPerform } from '@/components/permission-guard'

export function ModelsClient() {
  const t = useTranslations('models')
  const commonT = useTranslations('common')
  const { canPerform } = useCanPerform()
  
  // 数据状态
  const [models, setModels] = React.useState<Model[]>([])
  const [providers, setProviders] = React.useState<ProviderInfo[]>([])
  const [modelTypes, setModelTypes] = React.useState<ModelTypeInfo[]>([])
  const [isLoading, setIsLoading] = React.useState(true)
  const [page, setPage] = React.useState(1)
  const [pageSize, setPageSize] = React.useState(10)
  const [pageData, setPageData] = React.useState<PageData<Model> | null>(null)
  
  // 筛选状态
  const [searchQuery, setSearchQuery] = React.useState('')
  const [providerFilter, setProviderFilter] = React.useState<Set<string>>(new Set())
  const [typeFilter, setTypeFilter] = React.useState<Set<string>>(new Set())
  const [statusFilter, setStatusFilter] = React.useState<Set<string>>(new Set())
  
  // 选择状态
  const [selectedModels, setSelectedModels] = React.useState<Set<string>>(new Set())
  
  // Dialog 状态
  const [modelDialogOpen, setModelDialogOpen] = React.useState(false)
  const [deleteDialogOpen, setDeleteDialogOpen] = React.useState(false)
  const [bulkDeleteDialogOpen, setBulkDeleteDialogOpen] = React.useState(false)
  const [selectedModel, setSelectedModel] = React.useState<Model | null>(null)
  
  // 加载供应商和类型列表
  React.useEffect(() => {
    const loadMetadata = async () => {
      try {
        const [providersData, typesData] = await Promise.all([
          platformModelsApi.getProviders(),
          platformModelsApi.getModelTypes(),
        ])
        setProviders(providersData)
        setModelTypes(typesData)
      } catch {
        // 忽略错误
      }
    }
    loadMetadata()
  }, [])
  
  // 加载模型列表
  const loadModels = React.useCallback(async () => {
    setIsLoading(true)
    try {
      // 构建筛选参数
      const params: {
        page: number
        pageSize: number
        provider?: string
        model_type?: string
        is_enabled?: boolean
        search?: string
      } = { page, pageSize }
      
      // 搜索关键词
      if (searchQuery) {
        params.search = searchQuery
      }
      
      // 供应商筛选（只支持单选，取第一个）
      if (providerFilter.size > 0) {
        params.provider = Array.from(providerFilter)[0]
      }
      
      // 类型筛选（只支持单选，取第一个）
      if (typeFilter.size > 0) {
        params.model_type = Array.from(typeFilter)[0]
      }
      
      // 状态筛选
      if (statusFilter.size === 1) {
        params.is_enabled = statusFilter.has('enabled')
      }
      
      const data = await modelsApi.getModels(params)
      setModels(data.items)
      setPageData(data)
    } catch {
      // 错误已由 API 客户端处理
    } finally {
      setIsLoading(false)
    }
  }, [page, pageSize, searchQuery, providerFilter, typeFilter, statusFilter])
  
  React.useEffect(() => {
    loadModels()
  }, [loadModels])
  
  // 筛选由服务端处理，models 已经是筛选后的结果
  const filteredModels = models
  
  // 检查是否有筛选条件
  const isFiltered = searchQuery || providerFilter.size > 0 || typeFilter.size > 0 || statusFilter.size > 0
  
  // 重置所有筛选
  const resetFilters = () => {
    setSearchQuery('')
    setProviderFilter(new Set())
    setTypeFilter(new Set())
    setStatusFilter(new Set())
    setPage(1) // 重置到第一页
  }
  
  // 筛选条件变化时重置到第一页
  React.useEffect(() => {
    setPage(1)
  }, [searchQuery, providerFilter, typeFilter, statusFilter])
  
  // 供应商选项 - 只显示模型列表中存在的供应商
  const providerOptions = React.useMemo(() => {
    const existingProviders = new Set(models.map(m => m.provider))
    return providers
      .filter(p => existingProviders.has(p.code))
      .map(p => ({
        value: p.code,
        label: t(`providers.${p.code}`),
      }))
  }, [providers, models, t])
  
  // 类型选项 - 只显示模型列表中存在的类型
  const typeOptions = React.useMemo(() => {
    const existingTypes = new Set(models.map(m => m.model_type))
    return modelTypes
      .filter(mt => existingTypes.has(mt.code))
      .map(mt => ({
        value: mt.code,
        label: t(`modelTypes.${mt.code}`),
      }))
  }, [modelTypes, models, t])
  
  // 状态选项
  const statusOptions = [
    { value: 'enabled', label: t('enabled') },
    { value: 'disabled', label: t('disabled') },
  ]
  
  // 计算分页信息
  const totalPages = pageData ? Math.ceil(pageData.total / pageSize) : 1
  
  // 选择操作
  const toggleSelectAll = () => {
    if (selectedModels.size === filteredModels.length) {
      setSelectedModels(new Set())
    } else {
      setSelectedModels(new Set(filteredModels.map(m => m.id)))
    }
  }
  
  const toggleSelectModel = (modelId: string) => {
    const newSelected = new Set(selectedModels)
    if (newSelected.has(modelId)) {
      newSelected.delete(modelId)
    } else {
      newSelected.add(modelId)
    }
    setSelectedModels(newSelected)
  }
  
  // 打开创建 Dialog
  const handleCreate = () => {
    setSelectedModel(null)
    setModelDialogOpen(true)
  }
  
  // 打开编辑 Dialog
  const handleEdit = (model: Model) => {
    setSelectedModel(model)
    setModelDialogOpen(true)
  }
  
  // 打开删除 Dialog
  const handleDelete = (model: Model) => {
    setSelectedModel(model)
    setDeleteDialogOpen(true)
  }
  
  // 切换模型启用状态
  const handleToggleStatus = async (model: Model) => {
    try {
      await modelsApi.updateModel(model.id, { is_enabled: !model.is_enabled })
      toast.success(model.is_enabled ? t('modelDisabled') : t('modelEnabled'))
      loadModels()
    } catch {
      // 错误已由 API 客户端处理
    }
  }
  
  // 设为默认模型
  const handleSetDefault = async (model: Model) => {
    try {
      await modelsApi.setDefault(model.id)
      toast.success(t('modelSetDefault'))
      loadModels()
    } catch {
      // 错误已由 API 客户端处理
    }
  }
  
  // 测试连接
  const handleTestConnection = async (model: Model) => {
    const toastId = toast.loading(t('testing'))
    try {
      const result = await modelsApi.testConnection(model.id)
      if (result.success) {
        const latencyInfo = result.latency_ms ? ` (${result.latency_ms}ms)` : ''
        toast.success(`${t('testSuccess')}${latencyInfo}`, { id: toastId })
      } else {
        toast.error(result.message || t('testFailed'), { id: toastId })
      }
    } catch {
      toast.dismiss(toastId)
      // 错误已由 API 客户端处理
    }
  }
  
  // Dialog 成功回调
  const handleDialogSuccess = () => {
    loadModels()
    setSelectedModels(new Set())
  }
  
  // 批量删除
  const handleBulkDelete = () => {
    setBulkDeleteDialogOpen(true)
  }
  
  // 确认批量删除
  const confirmBulkDelete = async () => {
    try {
      const promises = Array.from(selectedModels).map(id => modelsApi.deleteModel(id))
      await Promise.all(promises)
      toast.success(t('bulkDeleted', { count: selectedModels.size }))
      setSelectedModels(new Set())
      loadModels()
    } catch {
      // 错误已由 API 客户端处理
    } finally {
      setBulkDeleteDialogOpen(false)
    }
  }
  
  // 获取供应商名称
  const getProviderName = (code: string) => {
    return t(`providers.${code}`)
  }
  
  // 获取类型名称
  const getTypeName = (code: string) => {
    return t(`modelTypes.${code}`)
  }
  
  // 获取状态 Badge
  const getStatusBadge = (model: Model) => {
    if (model.is_enabled) {
      return <Badge variant="default" className="bg-emerald-500/10 text-emerald-500 hover:bg-emerald-500/20">{t('enabled')}</Badge>
    }
    return <Badge variant="outline" className="text-muted-foreground">{t('disabled')}</Badge>
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
          <PermissionGuard permission="admin:model:create">
            <Button onClick={handleCreate}>
              <Plus className="mr-2 h-4 w-4" />
              {t('createModel')}
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
              placeholder={t('filterModels')}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-8 w-50 h-9"
            />
          </div>
          
          <DataTableFacetedFilter
            title={t('provider')}
            options={providerOptions}
            selectedValues={providerFilter}
            onSelectionChange={setProviderFilter}
          />
          
          <DataTableFacetedFilter
            title={t('modelType')}
            options={typeOptions}
            selectedValues={typeFilter}
            onSelectionChange={setTypeFilter}
          />
          
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
                  checked={selectedModels.size === filteredModels.length && filteredModels.length > 0}
                  onCheckedChange={toggleSelectAll}
                />
              </TableHead>
              <TableHead>{t('modelName')}</TableHead>
              <TableHead>{t('provider')}</TableHead>
              <TableHead>{t('modelType')}</TableHead>
              <TableHead>{t('modelId')}</TableHead>
              <TableHead>{t('status')}</TableHead>
              <TableHead>{t('apiKey')}</TableHead>
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
            ) : filteredModels.length === 0 ? (
              <TableRow>
                <TableCell colSpan={8} className="h-24 text-center text-muted-foreground">
                  {t('noModels')}
                </TableCell>
              </TableRow>
            ) : (
              filteredModels.map((model) => (
                <TableRow key={model.id} data-state={selectedModels.has(model.id) ? 'selected' : undefined}>
                  <TableCell>
                    <Checkbox
                      checked={selectedModels.has(model.id)}
                      onCheckedChange={() => toggleSelectModel(model.id)}
                    />
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <span className="font-medium">{model.name}</span>
                      {model.is_default && (
                        <Badge variant="secondary" className="gap-1">
                          <Star className="h-3 w-3 fill-current" />
                          {t('default')}
                        </Badge>
                      )}
                    </div>
                  </TableCell>
                  <TableCell>{getProviderName(model.provider)}</TableCell>
                  <TableCell>
                    <Badge variant="outline">{getTypeName(model.model_type)}</Badge>
                  </TableCell>
                  <TableCell className="font-mono text-sm text-muted-foreground">
                    {model.model_id}
                  </TableCell>
                  <TableCell>{getStatusBadge(model)}</TableCell>
                  <TableCell>
                    {model.has_api_key ? (
                      <Badge variant="default" className="bg-blue-500/10 text-blue-500">
                        {t('configured')}
                      </Badge>
                    ) : (
                      <Badge variant="outline" className="text-muted-foreground">
                        {t('notConfigured')}
                      </Badge>
                    )}
                  </TableCell>
                  <TableCell>
                    {(canPerform('admin:model:update') || canPerform('admin:model:delete')) && (
                      <DropdownMenu>
                        <DropdownMenuTrigger className="ring-offset-background focus-visible:ring-ring data-[state=open]:bg-accent inline-flex h-8 w-8 items-center justify-center rounded-md hover:bg-accent focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:outline-none">
                          <MoreHorizontal className="h-4 w-4" />
                          <span className="sr-only">{t('common.openMenu')}</span>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          {canPerform('admin:model:update') && (
                            <>
                              <DropdownMenuItem onClick={() => handleEdit(model)}>
                                <Pencil className="mr-2 h-4 w-4" />
                                {commonT('edit')}
                              </DropdownMenuItem>

                              <DropdownMenuItem onClick={() => handleToggleStatus(model)}>
                                {model.is_enabled ? (
                                  <>
                                    <PowerOff className="mr-2 h-4 w-4" />
                                    {t('disable')}
                                  </>
                                ) : (
                                  <>
                                    <Power className="mr-2 h-4 w-4" />
                                    {t('enable')}
                                  </>
                                )}
                              </DropdownMenuItem>

                              {!model.is_default && (
                                <DropdownMenuItem onClick={() => handleSetDefault(model)}>
                                  <Star className="mr-2 h-4 w-4" />
                                  {t('setDefault')}
                                </DropdownMenuItem>
                              )}

                              {model.has_api_key && (
                                <DropdownMenuItem onClick={() => handleTestConnection(model)}>
                                  <TestTube className="mr-2 h-4 w-4" />
                                  {t('testConnection')}
                                </DropdownMenuItem>
                              )}
                            </>
                          )}

                          {canPerform('admin:model:delete') && (
                            <>
                              <DropdownMenuSeparator />
                              <DropdownMenuItem
                                onClick={() => handleDelete(model)}
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
      <ModelDialog
        open={modelDialogOpen}
        onOpenChange={setModelDialogOpen}
        model={selectedModel}
        providers={providers}
        modelTypes={modelTypes}
        onSuccess={handleDialogSuccess}
      />
      
      {/* 删除确认 Dialog */}
      <DeleteModelDialog
        open={deleteDialogOpen}
        onOpenChange={setDeleteDialogOpen}
        model={selectedModel}
        onSuccess={handleDialogSuccess}
      />
      
      {/* 批量操作浮动工具栏 */}
      {selectedModels.size > 0 && canPerform('admin:model:delete') && (
        <div className="fixed bottom-8 left-1/2 -translate-x-1/2 z-50">
          <div className="flex items-center gap-1 rounded-lg border bg-background px-2 py-1.5 shadow-lg">
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              onClick={() => setSelectedModels(new Set())}
            >
              <X className="h-4 w-4" />
            </Button>

            <Badge variant="secondary" className="px-2 py-1">
              {selectedModels.size} {t('modelsSelected')}
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
              {t('confirmBulkDelete', { count: selectedModels.size })}
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
