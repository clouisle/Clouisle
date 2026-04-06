'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { Bot, Search, X } from 'lucide-react'
import { useTeam } from '@/contexts/team-context'
import { useRequireTeam } from '@/hooks/use-require-team'
import { teamModelsApi, type TeamModel } from '@/lib/api'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { DataTableFacetedFilter } from '@/components/ui/data-table-faceted-filter'
import { ModelCard, ModelCardSkeleton, ModelDetailDialog } from './_components'

// 模型类型列表
const MODEL_TYPES = [
  'chat',
  'embedding', 
  'rerank',
  'tts',
  'stt',
  'text_to_image',
  'text_to_video',
] as const

export default function ModelsPage() {
  const t = useTranslations('platform')
  const modelsT = useTranslations('models')
  const commonT = useTranslations('common')
  const { currentTeam } = useTeam()

  // 没有团队时重定向到首页
  useRequireTeam()
  
  const [teamModels, setTeamModels] = React.useState<TeamModel[]>([])
  const [isLoading, setIsLoading] = React.useState(true)
  const [searchQuery, setSearchQuery] = React.useState('')
  const [typeFilter, setTypeFilter] = React.useState<Set<string>>(new Set())
  const [providerFilter, setProviderFilter] = React.useState<Set<string>>(new Set())
  const [statusFilter, setStatusFilter] = React.useState<Set<string>>(new Set())
  
  // 详情弹窗状态
  const [detailDialogOpen, setDetailDialogOpen] = React.useState(false)
  const [selectedModel, setSelectedModel] = React.useState<TeamModel | null>(null)

  // 加载团队已授权的模型
  const fetchTeamModels = React.useCallback(async () => {
    if (!currentTeam) return
    
    try {
      setIsLoading(true)
      const models = await teamModelsApi.getTeamModels(currentTeam.id)
      setTeamModels(models)
    } catch (error) {
      console.error('Failed to fetch team models:', error)
    } finally {
      setIsLoading(false)
    }
  }, [currentTeam])

  React.useEffect(() => {
    fetchTeamModels()
  }, [fetchTeamModels])

  // 获取供应商选项（只显示存在的）
  const providerOptions = React.useMemo(() => {
    const providers = new Set(teamModels.map(tm => tm.model.provider))
    return Array.from(providers).map(p => ({
      value: p,
      label: modelsT(`providers.${p}`),
    }))
  }, [teamModels, modelsT])

  // 获取类型选项（只显示存在的）
  const typeOptions = React.useMemo(() => {
    const types = new Set(teamModels.map(tm => tm.model.model_type))
    return MODEL_TYPES
      .filter(type => types.has(type))
      .map(type => ({
        value: type,
        label: modelsT(`modelTypes.${type}`),
      }))
  }, [teamModels, modelsT])

  // 状态选项
  const statusOptions = [
    { value: 'enabled', label: modelsT('enabled') },
    { value: 'disabled', label: modelsT('disabled') },
  ]

  // 检查是否有筛选
  const isFiltered = searchQuery || typeFilter.size > 0 || providerFilter.size > 0 || statusFilter.size > 0

  // 重置筛选
  const resetFilters = () => {
    setSearchQuery('')
    setTypeFilter(new Set())
    setProviderFilter(new Set())
    setStatusFilter(new Set())
  }

  // 筛选模型
  const filteredModels = React.useMemo(() => {
    return teamModels.filter((tm) => {
      // 搜索过滤
      if (searchQuery) {
        const query = searchQuery.toLowerCase()
        if (
          !tm.model.name.toLowerCase().includes(query) &&
          !tm.model.model_id.toLowerCase().includes(query) &&
          !tm.model.provider.toLowerCase().includes(query)
        ) {
          return false
        }
      }
      // 类型过滤
      if (typeFilter.size > 0 && !typeFilter.has(tm.model.model_type)) {
        return false
      }
      // 供应商过滤
      if (providerFilter.size > 0 && !providerFilter.has(tm.model.provider)) {
        return false
      }
      // 状态过滤
      if (statusFilter.size > 0) {
        const isEnabled = tm.is_enabled
        if (statusFilter.has('enabled') && !isEnabled) return false
        if (statusFilter.has('disabled') && isEnabled) return false
        if (statusFilter.size === 2) return true // 两个都选等于不筛选
      }
      return true
    })
  }, [teamModels, searchQuery, typeFilter, providerFilter, statusFilter])

  // 按类型分组
  const groupedModels = React.useMemo(() => {
    const groups: Record<string, TeamModel[]> = {}
    filteredModels.forEach((tm) => {
      const type = tm.model.model_type
      if (!groups[type]) groups[type] = []
      groups[type].push(tm)
    })
    // 按优先级排序
    Object.values(groups).forEach((group) => {
      group.sort((a, b) => b.priority - a.priority)
    })
    return groups
  }, [filteredModels])

  // 处理模型卡片点击
  const handleModelClick = (teamModel: TeamModel) => {
    setSelectedModel(teamModel)
    setDetailDialogOpen(true)
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
        </div>
        <div className="flex items-center gap-2 mb-6">
          <Skeleton className="h-9 w-50" />
          <Skeleton className="h-9 w-28" />
          <Skeleton className="h-9 w-28" />
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
          {[...Array(8)].map((_, i) => (
            <ModelCardSkeleton key={i} />
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
          <h1 className="text-3xl font-bold tracking-tight">{t('models.title')}</h1>
          <p className="text-muted-foreground mt-1">
            {t('models.description')}
          </p>
        </div>
      </div>

      {/* 筛选栏 */}
      <div className="flex items-center gap-2 mb-6">
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder={modelsT('filterModels')}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-8 w-50 h-9"
          />
        </div>
        
        <DataTableFacetedFilter
          title={modelsT('provider')}
          options={providerOptions}
          selectedValues={providerFilter}
          onSelectionChange={setProviderFilter}
        />
        
        <DataTableFacetedFilter
          title={modelsT('modelType')}
          options={typeOptions}
          selectedValues={typeFilter}
          onSelectionChange={setTypeFilter}
        />
        
        <DataTableFacetedFilter
          title={modelsT('status')}
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

      {/* 模型卡片网格 */}
      {teamModels.length === 0 ? (
        // 空状态
        <div className="text-center py-12 text-muted-foreground">
          <Bot className="h-12 w-12 mx-auto mb-4 opacity-50" />
          <p>{t('models.noModels')}</p>
          <p className="text-sm mt-1">{t('models.createModelHint')}</p>
        </div>
      ) : filteredModels.length === 0 ? (
        // 筛选无结果
        <div className="text-center py-12 text-muted-foreground">
          <Search className="h-12 w-12 mx-auto mb-4 opacity-50" />
          <p>{modelsT('noModels')}</p>
          <Button variant="outline" className="mt-4" onClick={resetFilters}>
            <X className="mr-2 h-4 w-4" />
            {commonT('clearFilters')}
          </Button>
        </div>
      ) : typeFilter.size === 0 ? (
        // 按类型分组显示（没有类型筛选时）
        <div className="space-y-8">
          {MODEL_TYPES.filter(type => groupedModels[type]?.length > 0).map((type) => (
            <div key={type}>
              <h2 className="text-lg font-semibold mb-3 flex items-center gap-2">
                {modelsT(`modelTypes.${type}`)}
                <span className="text-sm font-normal text-muted-foreground">
                  ({groupedModels[type].length})
                </span>
              </h2>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
                {groupedModels[type].map((tm) => (
                  <ModelCard
                    key={tm.id}
                    teamModel={tm}
                    onClick={() => handleModelClick(tm)}
                  />
                ))}
              </div>
            </div>
          ))}
        </div>
      ) : (
        // 平铺显示（有类型筛选时）
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
          {filteredModels.map((tm) => (
            <ModelCard
              key={tm.id}
              teamModel={tm}
              onClick={() => handleModelClick(tm)}
            />
          ))}
        </div>
      )}

      {/* 模型详情弹窗 */}
      <ModelDetailDialog
        open={detailDialogOpen}
        onOpenChange={setDetailDialogOpen}
        teamModel={selectedModel}
      />
    </div>
  )
}
