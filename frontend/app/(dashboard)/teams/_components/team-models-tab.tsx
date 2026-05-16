'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { toast } from 'sonner'
import {
  Plus,
  Trash2,
  Settings2,
  Infinity,
  AlertCircle,
  Search,
} from 'lucide-react'
import {
  teamModelsApi,
  type TeamModel,
  type TeamModelUpdateInput,
} from '@/lib/api'
import { modelsApi, type Model } from '@/lib/api/admin/models'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Checkbox } from '@/components/ui/checkbox'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
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
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { PermissionGuard, useCanPerform } from '@/components/permission-guard'

interface TeamModelsTabProps {
  teamId: string
}

// 格式化配额数字
function formatQuota(value: number | null): string {
  if (value === null) return '∞'
  if (value >= 1000000) return `${(value / 1000000).toFixed(1)}M`
  if (value >= 1000) return `${(value / 1000).toFixed(1)}K`
  return value.toString()
}

// 计算使用百分比
function getUsagePercent(used: number, limit: number | null): number | null {
  if (limit === null || limit === 0) return null
  return Math.min(100, Math.round((used / limit) * 100))
}

// 使用进度条
function UsageBar({ used, limit }: { used: number; limit: number | null }) {
  const percent = getUsagePercent(used, limit)
  
  if (percent === null) {
    return (
      <div className="flex items-center gap-1 text-xs text-muted-foreground">
        <span>{formatQuota(used)}</span>
        <span>/</span>
        <Infinity className="h-3 w-3" />
      </div>
    )
  }
  
  return (
    <div className="space-y-0.5">
      <div className="flex justify-between text-xs">
        <span>{formatQuota(used)}</span>
        <span className="text-muted-foreground">{formatQuota(limit)}</span>
      </div>
      <div className="h-1.5 bg-muted rounded-full overflow-hidden">
        <div
          className={`h-full transition-all ${
            percent >= 90 ? 'bg-destructive' : percent >= 70 ? 'bg-yellow-500' : 'bg-primary'
          }`}
          style={{ width: `${percent}%` }}
        />
      </div>
    </div>
  )
}

export function TeamModelsTab({ teamId }: TeamModelsTabProps) {
  const t = useTranslations('teams')
  const modelT = useTranslations('models')
  const commonT = useTranslations('common')
  const { canPerform } = useCanPerform()
  const canManageTeam = canPerform('team:manage')

  // 数据状态
  const [teamModels, setTeamModels] = React.useState<TeamModel[]>([])
  const [allModels, setAllModels] = React.useState<Model[]>([])
  const [isLoading, setIsLoading] = React.useState(true)

  // Dialog 状态
  const [addModelOpen, setAddModelOpen] = React.useState(false)
  const [selectedModelIds, setSelectedModelIds] = React.useState<Set<string>>(new Set())
  const [modelSearch, setModelSearch] = React.useState('')
  const [isAdding, setIsAdding] = React.useState(false)

  const [editDialogOpen, setEditDialogOpen] = React.useState(false)
  const [editingModel, setEditingModel] = React.useState<TeamModel | null>(null)
  const [editForm, setEditForm] = React.useState<TeamModelUpdateInput>({})
  const [isSaving, setIsSaving] = React.useState(false)

  const [deleteDialogOpen, setDeleteDialogOpen] = React.useState(false)
  const [deletingModel, setDeletingModel] = React.useState<TeamModel | null>(null)

  // 加载数据
  const loadData = React.useCallback(async () => {
    setIsLoading(true)
    try {
      const [teamModelsData, allModelsData] = await Promise.all([
        teamModelsApi.getTeamModels(teamId),
        modelsApi.getModels({ pageSize: 100 }),
      ])
      setTeamModels(teamModelsData)
      setAllModels(allModelsData.items)
    } catch {
      // 错误已由 API 客户端处理
    } finally {
      setIsLoading(false)
    }
  }, [teamId])

  React.useEffect(() => {
    loadData()
  }, [loadData])

  // 可添加的模型（排除已授权的）
  const availableModels = React.useMemo(() => {
    const authorizedIds = new Set(teamModels.map((tm) => tm.model_id))
    return allModels.filter((m) => !authorizedIds.has(m.id) && m.is_enabled)
  }, [allModels, teamModels])

  // 过滤模型
  const filteredModels = React.useMemo(() => {
    if (!modelSearch) return availableModels
    const query = modelSearch.toLowerCase()
    return availableModels.filter(
      (m) =>
        m.name.toLowerCase().includes(query) ||
        m.provider.toLowerCase().includes(query) ||
        m.model_id.toLowerCase().includes(query)
    )
  }, [availableModels, modelSearch])

  // 切换模型选择
  const toggleModelSelection = (modelId: string) => {
    setSelectedModelIds((prev) => {
      const next = new Set(prev)
      if (next.has(modelId)) {
        next.delete(modelId)
      } else {
        next.add(modelId)
      }
      return next
    })
  }

  // 全选/取消全选
  const toggleSelectAll = () => {
    if (selectedModelIds.size === filteredModels.length) {
      setSelectedModelIds(new Set())
    } else {
      setSelectedModelIds(new Set(filteredModels.map((m) => m.id)))
    }
  }

  // 批量添加模型授权
  const handleAddModels = async () => {
    if (selectedModelIds.size === 0) return
    setIsAdding(true)
    try {
      await teamModelsApi.batchAddTeamModels(teamId, {
        model_ids: Array.from(selectedModelIds),
      })
      toast.success(t('modelsAuthorized', { count: selectedModelIds.size }))
      setAddModelOpen(false)
      setSelectedModelIds(new Set())
      setModelSearch('')
      loadData()
    } catch {
      // 错误已由 API 客户端处理
    } finally {
      setIsAdding(false)
    }
  }

  // 打开编辑对话框
  const openEditDialog = (teamModel: TeamModel) => {
    setEditingModel(teamModel)
    setEditForm({
      daily_token_limit: teamModel.daily_token_limit,
      monthly_token_limit: teamModel.monthly_token_limit,
      daily_request_limit: teamModel.daily_request_limit,
      monthly_request_limit: teamModel.monthly_request_limit,
      is_enabled: teamModel.is_enabled,
      priority: teamModel.priority,
    })
    setEditDialogOpen(true)
  }

  // 保存编辑
  const handleSaveEdit = async () => {
    if (!editingModel) return
    setIsSaving(true)
    try {
      await teamModelsApi.updateTeamModel(teamId, editingModel.model_id, editForm)
      toast.success(t('modelAuthUpdated'))
      setEditDialogOpen(false)
      setEditingModel(null)
      loadData()
    } catch {
      // 错误已由 API 客户端处理
    } finally {
      setIsSaving(false)
    }
  }

  // 删除授权
  const handleDelete = async () => {
    if (!deletingModel) return
    try {
      await teamModelsApi.removeTeamModel(teamId, deletingModel.model_id)
      toast.success(t('modelAuthRevoked'))
      setDeleteDialogOpen(false)
      setDeletingModel(null)
      loadData()
    } catch {
      // 错误已由 API 客户端处理
    }
  }

  // 快速切换启用状态
  const handleToggleEnabled = async (teamModel: TeamModel) => {
    try {
      await teamModelsApi.updateTeamModel(teamId, teamModel.model_id, {
        is_enabled: !teamModel.is_enabled,
      })
      loadData()
    } catch {
      // 错误已由 API 客户端处理
    }
  }

  if (isLoading) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-10 w-full" />
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="font-medium">
          {t('authorizedModels')} ({teamModels.length})
        </h3>
        <PermissionGuard permission="team:manage">
          <Popover open={addModelOpen} onOpenChange={setAddModelOpen}>
            <PopoverTrigger
              render={
                <Button variant="outline" size="sm">
                  <Plus className="mr-2 h-4 w-4" />
                  {t('addModel')}
                </Button>
              }
            />
            <PopoverContent className="w-80 p-0" align="end">
              <div className="p-3 border-b space-y-2">
                <div className="relative">
                  <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    placeholder={t('searchModels')}
                    value={modelSearch}
                    onChange={(e) => setModelSearch(e.target.value)}
                    className="pl-8"
                  />
                </div>
                {filteredModels.length > 0 && (
                  <div className="flex items-center justify-between text-xs text-muted-foreground">
                    <label className="flex items-center gap-2 cursor-pointer">
                      <Checkbox
                        checked={selectedModelIds.size === filteredModels.length && filteredModels.length > 0}
                        onCheckedChange={toggleSelectAll}
                      />
                      <span>{t('selectAll')}</span>
                    </label>
                    <span>{t('selectedCount', { count: selectedModelIds.size })}</span>
                  </div>
                )}
              </div>
              <ScrollArea className="h-64">
                {filteredModels.length === 0 ? (
                  <div className="p-4 text-center text-muted-foreground text-sm">
                    {availableModels.length === 0
                      ? t('allModelsAuthorized')
                      : t('noModelsFound')}
                  </div>
                ) : (
                  <div className="p-2 space-y-1">
                    {filteredModels.map((model) => (
                      <label
                        key={model.id}
                        className="w-full flex items-center gap-2 px-2 py-1.5 rounded hover:bg-accent cursor-pointer"
                      >
                        <Checkbox
                          checked={selectedModelIds.has(model.id)}
                          onCheckedChange={() => toggleModelSelection(model.id)}
                        />
                        <div className="flex-1 min-w-0">
                          <div className="text-sm font-medium truncate">{model.name}</div>
                          <div className="text-xs text-muted-foreground">
                            {model.provider} / {model.model_id}
                          </div>
                        </div>
                        <Badge variant="outline" className="text-xs shrink-0">
                          {modelT(`types.${model.model_type}`)}
                        </Badge>
                      </label>
                    ))}
                  </div>
                )}
              </ScrollArea>
              {selectedModelIds.size > 0 && (
                <div className="border-t p-3">
                  <Button
                    className="w-full"
                    size="sm"
                    disabled={isAdding}
                    onClick={handleAddModels}
                  >
                    {isAdding ? commonT('loading') : t('authorizeModels', { count: selectedModelIds.size })}
                  </Button>
                </div>
              )}
            </PopoverContent>
          </Popover>
        </PermissionGuard>
      </div>

      {/* Models List */}
      {teamModels.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-8 text-muted-foreground">
          <AlertCircle className="h-8 w-8 mb-2" />
          <p>{t('noModelsAuthorized')}</p>
          <p className="text-sm">{t('addModelHint')}</p>
        </div>
      ) : (
        <div className="border rounded-md overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="min-w-[180px]">{modelT('name')}</TableHead>
                <TableHead className="w-20">{modelT('type')}</TableHead>
                <TableHead className="w-24">{t('dailyQuota')}</TableHead>
                <TableHead className="w-24">{t('monthlyQuota')}</TableHead>
                <TableHead className="w-14">{commonT('status')}</TableHead>
                <TableHead className="w-20"></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {teamModels.map((tm) => (
                <TableRow key={tm.id}>
                  <TableCell>
                    <div>
                      <div className="font-medium">{tm.model.name}</div>
                      <div className="text-xs text-muted-foreground">
                        {tm.model.provider} / {tm.model.model_id}
                      </div>
                    </div>
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline">
                      {modelT(`types.${tm.model.model_type}`)}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <UsageBar used={tm.daily_tokens_used} limit={tm.daily_token_limit} />
                  </TableCell>
                  <TableCell>
                    <UsageBar used={tm.monthly_tokens_used} limit={tm.monthly_token_limit} />
                  </TableCell>
                  <TableCell>
                    {canManageTeam ? (
                      <Switch
                        checked={tm.is_enabled}
                        onCheckedChange={() => handleToggleEnabled(tm)}
                      />
                    ) : null}
                  </TableCell>
                  <TableCell>
                    {canManageTeam && (
                      <div className="flex items-center gap-1">
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8"
                          onClick={() => openEditDialog(tm)}
                        >
                          <Settings2 className="h-4 w-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8 text-destructive hover:text-destructive"
                          onClick={() => {
                            setDeletingModel(tm)
                            setDeleteDialogOpen(true)
                          }}
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      {/* Edit Dialog */}
      <Dialog open={editDialogOpen} onOpenChange={setEditDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('editModelAuth')}</DialogTitle>
            <DialogDescription>
              {editingModel?.model.name} - {t('quotaSettings')}
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>{t('dailyTokenLimit')}</Label>
                <Input
                  placeholder={t('unlimited')}
                  value={editForm.daily_token_limit ?? ''}
                  onChange={(e) =>
                    setEditForm({
                      ...editForm,
                      daily_token_limit: e.target.value ? Number(e.target.value) : null,
                    })
                  }
                />
              </div>
              <div className="space-y-2">
                <Label>{t('monthlyTokenLimit')}</Label>
                <Input
                  placeholder={t('unlimited')}
                  value={editForm.monthly_token_limit ?? ''}
                  onChange={(e) =>
                    setEditForm({
                      ...editForm,
                      monthly_token_limit: e.target.value ? Number(e.target.value) : null,
                    })
                  }
                />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>{t('dailyRequestLimit')}</Label>
                <Input
                  placeholder={t('unlimited')}
                  value={editForm.daily_request_limit ?? ''}
                  onChange={(e) =>
                    setEditForm({
                      ...editForm,
                      daily_request_limit: e.target.value ? Number(e.target.value) : null,
                    })
                  }
                />
              </div>
              <div className="space-y-2">
                <Label>{t('monthlyRequestLimit')}</Label>
                <Input
                  placeholder={t('unlimited')}
                  value={editForm.monthly_request_limit ?? ''}
                  onChange={(e) =>
                    setEditForm({
                      ...editForm,
                      monthly_request_limit: e.target.value ? Number(e.target.value) : null,
                    })
                  }
                />
              </div>
            </div>
            <div className="space-y-2">
              <Label>{t('priority')}</Label>
              <Input
                value={editForm.priority ?? 0}
                onChange={(e) =>
                  setEditForm({
                    ...editForm,
                    priority: Number(e.target.value),
                  })
                }
              />
              <p className="text-xs text-muted-foreground">{t('priorityHint')}</p>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditDialogOpen(false)}>
              {commonT('cancel')}
            </Button>
            <Button onClick={handleSaveEdit} disabled={isSaving}>
              {isSaving ? commonT('loading') : commonT('save')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirm */}
      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('revokeModelAuth')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('revokeModelAuthConfirm', { name: deletingModel?.model.name || '' })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{commonT('cancel')}</AlertDialogCancel>
            <AlertDialogAction variant="destructive" onClick={handleDelete}>
              {t('revoke')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
