'use client'

import * as React from 'react'
import { Plus, Trash2, Search, GripVertical, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue, SelectEmpty } from '@/components/ui/select'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Textarea } from '@/components/ui/textarea'
import { cn } from '@/lib/utils'
import { useTeam } from '@/contexts/team-context'
import { teamModelsApi, type TeamModel } from '@/lib/api'
import { isValidVariableName } from '../utils'
import { extractVariableDisplayName } from '../types'
import type { AvailableVariable } from '../types'
import { 
  QuestionClassifierConfig, 
  ClassifierCategory,
  defaultQuestionClassifierConfig,
} from '../../nodes/question-classifier-node'

interface QuestionClassifierNodeConfigProps {
  config: QuestionClassifierConfig
  variables: AvailableVariable[]
  variableSearch: string
  openVariablePopover: string | null
  onConfigChange: (config: QuestionClassifierConfig) => void
  onVariableSearchChange: (search: string) => void
  onOpenVariablePopoverChange: (id: string | null) => void
}

export function QuestionClassifierNodeConfig({
  config,
  variables,
  variableSearch,
  openVariablePopover,
  onConfigChange,
  onVariableSearchChange,
  onOpenVariablePopoverChange,
}: QuestionClassifierNodeConfigProps) {
  const { currentTeam } = useTeam()
  
  // 模型数据
  const [teamChatModels, setTeamChatModels] = React.useState<TeamModel[]>([])
  const [isLoadingModels, setIsLoadingModels] = React.useState(false)

  // 确保 config 有默认值
  const safeConfig: QuestionClassifierConfig = {
    ...defaultQuestionClassifierConfig,
    ...config,
    categories: config.categories || [],
  }

  // 加载模型列表
  React.useEffect(() => {
    const loadModels = async () => {
      if (!currentTeam) return
      
      setIsLoadingModels(true)
      try {
        const models = await teamModelsApi.getTeamModels(currentTeam.id, 'chat')
        setTeamChatModels(models.filter(m => m.is_enabled))
      } catch {
        // 忽略错误
      } finally {
        setIsLoadingModels(false)
      }
    }
    loadModels()
  }, [currentTeam])

  // 获取选中的模型名称
  const selectedModelName = React.useMemo(() => {
    if (!safeConfig.modelId) return null
    const tm = teamChatModels.find(m => m.id === safeConfig.modelId)
    if (tm) return tm.model.name
    return safeConfig.modelName || safeConfig.modelId
  }, [safeConfig.modelId, safeConfig.modelName, teamChatModels])

  // 过滤变量（只显示 String 类型）
  const filterVariables = (search: string) => {
    let filtered = variables.filter(v => v.type === 'String')
    if (search) {
      filtered = filtered.filter(v => 
        v.name.toLowerCase().includes(search.toLowerCase())
      )
    }
    return filtered
  }

  // 分组变量
  const groupVariables = (vars: AvailableVariable[]) => {
    const groups = vars.reduce((acc, v) => {
      if (!acc[v.group]) {
        acc[v.group] = { label: v.groupLabel, isSystem: v.isSystem, items: [] }
      }
      acc[v.group].items.push(v)
      return acc
    }, {} as Record<string, { label: string; isSystem: boolean; items: AvailableVariable[] }>)
    
    const entries = Object.entries(groups)
    entries.sort((a, b) => {
      if (a[1].isSystem && !b[1].isSystem) return 1
      if (!a[1].isSystem && b[1].isSystem) return -1
      return 0
    })
    
    return entries
  }

  // 添加类别
  const handleAddCategory = () => {
    const newCategory: ClassifierCategory = {
      id: `cat_${Date.now()}`,
      name: `类别${safeConfig.categories.length + 1}`,
      description: '',
    }
    onConfigChange({
      ...safeConfig,
      categories: [...safeConfig.categories, newCategory],
    })
  }

  // 更新类别
  const handleUpdateCategory = (id: string, updates: Partial<ClassifierCategory>) => {
    onConfigChange({
      ...safeConfig,
      categories: safeConfig.categories.map(c => 
        c.id === id ? { ...c, ...updates } : c
      ),
    })
  }

  // 删除类别
  const handleDeleteCategory = (id: string) => {
    onConfigChange({
      ...safeConfig,
      categories: safeConfig.categories.filter(c => c.id !== id),
    })
  }

  // 渲染源变量选择器
  const renderSourceVariableSelector = () => {
    const popoverId = 'source-var'
    
    return (
      <Popover 
        open={openVariablePopover === popoverId}
        onOpenChange={(isOpen) => {
          onOpenVariablePopoverChange(isOpen ? popoverId : null)
          if (!isOpen) onVariableSearchChange('')
        }}
      >
        <PopoverTrigger
          className={cn(
            'w-full h-9 flex items-center justify-start gap-1 px-3 text-sm bg-background border border-input rounded-md cursor-pointer hover:bg-accent hover:text-accent-foreground',
          )}
        >
          {safeConfig.sourceVariable ? (
            <>
              <span className="text-primary/80 font-mono text-xs">{'{x}'}</span>
              <span className="text-xs truncate">
                {safeConfig.sourceNodeLabel && <span className="text-muted-foreground">{safeConfig.sourceNodeLabel} / </span>}
                {extractVariableDisplayName(safeConfig.sourceVariable)}
              </span>
            </>
          ) : (
            <span className="text-muted-foreground text-xs">选择问题变量...</span>
          )}
        </PopoverTrigger>
        <PopoverContent className="w-72 p-0" align="start">
          <div className="p-2 border-b">
            <div className="relative">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
              <Input
                placeholder="搜索变量"
                value={variableSearch}
                onChange={(e) => onVariableSearchChange(e.target.value)}
                className="h-8 pl-8 text-xs"
              />
            </div>
          </div>
          <ScrollArea className="h-50">
            <div className="p-1">
              {(() => {
                const filtered = filterVariables(variableSearch)
                const groupEntries = groupVariables(filtered)
                
                if (groupEntries.length === 0) {
                  return (
                    <div className="py-4 text-center text-xs text-muted-foreground">
                      未找到匹配的变量
                    </div>
                  )
                }
                
                return groupEntries.map(([groupId, group]) => (
                  <div key={groupId} className="mb-1">
                    <div className="px-2 py-1 text-xs text-muted-foreground font-medium">
                      {group.label}
                    </div>
                    {group.items.map(variable => (
                      <button
                        key={variable.id}
                        className="w-full flex items-center justify-between px-2 py-1.5 text-xs hover:bg-muted rounded-md"
                        onClick={() => {
                          // 使用 variable.id（格式为 nodeId.paramName）而不是 variable.name
                          onConfigChange({
                            ...safeConfig,
                            sourceVariable: `{{${variable.id}}}`,
                            sourceNodeLabel: variable.isSystem ? 'SYSTEM' : variable.groupLabel,
                          })
                          onOpenVariablePopoverChange(null)
                          onVariableSearchChange('')
                        }}
                      >
                        <span className="flex items-center gap-1.5">
                          <span className={cn(
                            'font-mono',
                            variable.isSystem ? 'text-orange-500' : 'text-primary/80'
                          )}>{'{x}'}</span>
                          <span>{variable.name}</span>
                        </span>
                        <span className="text-muted-foreground">{variable.type}</span>
                      </button>
                    ))}
                  </div>
                ))
              })()}
            </div>
          </ScrollArea>
        </PopoverContent>
      </Popover>
    )
  }

  return (
    <div className="space-y-4">
      {/* 模型选择 */}
      <div className="space-y-2">
        <div className="flex items-center gap-1">
          <Label className="text-xs font-medium">模型</Label>
          <span className="text-destructive">*</span>
        </div>
        <Select
          value={safeConfig.modelId || ''}
          onValueChange={(v) => {
            const model = teamChatModels.find(m => m.id === v)
            onConfigChange({ 
              ...safeConfig, 
              modelId: v || undefined,
              modelName: model?.model.name,
            })
          }}
          disabled={isLoadingModels}
        >
          <SelectTrigger className="w-full h-9 text-xs">
            <SelectValue>
              {isLoadingModels ? (
                <span className="flex items-center gap-2 text-muted-foreground">
                  <Loader2 className="h-3 w-3 animate-spin" />
                  加载中...
                </span>
              ) : (
                selectedModelName || '选择模型...'
              )}
            </SelectValue>
          </SelectTrigger>
          <SelectContent>
            {teamChatModels.length > 0 ? (
              teamChatModels.map((tm) => (
                <SelectItem key={tm.id} value={tm.id} className="text-xs">
                  {tm.model.name}
                </SelectItem>
              ))
            ) : (
              <SelectEmpty>暂无可用模型</SelectEmpty>
            )}
          </SelectContent>
        </Select>
      </div>

      {/* 源变量（问题文本） */}
      <div className="space-y-2">
        <div className="flex items-center gap-1">
          <Label className="text-xs font-medium">问题变量</Label>
          <span className="text-destructive">*</span>
        </div>
        {renderSourceVariableSelector()}
        <p className="text-[10px] text-muted-foreground">选择需要分类的问题文本变量</p>
      </div>

      {/* 分类指令 */}
      <div className="space-y-2">
        <Label className="text-xs font-medium">分类指令（可选）</Label>
        <Textarea
          value={safeConfig.instruction || ''}
          onChange={(e) => onConfigChange({ ...safeConfig, instruction: e.target.value })}
          placeholder="为分类任务提供额外的指导说明..."
          className="min-h-[60px] text-xs resize-none"
        />
        <p className="text-[10px] text-muted-foreground">提供额外的分类规则或注意事项</p>
      </div>

      {/* 分类类别 */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1">
            <Label className="text-xs font-medium">分类类别</Label>
            <span className="text-destructive">*</span>
          </div>
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6"
            onClick={handleAddCategory}
          >
            <Plus className="h-3 w-3" />
          </Button>
        </div>
        
        {safeConfig.categories.length === 0 ? (
          <p className="text-xs text-muted-foreground py-4 text-center bg-muted/30 rounded-md">
            暂无类别，点击 + 添加
          </p>
        ) : (
          <div className="space-y-2">
            {safeConfig.categories.map((category, index) => (
              <div
                key={category.id}
                className="bg-muted/30 rounded-lg p-3 space-y-2"
              >
                {/* 头部：序号 + 删除 */}
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <GripVertical className="h-3.5 w-3.5 text-muted-foreground cursor-grab" />
                    <span className="text-xs font-medium text-violet-500">
                      类别 {index + 1}
                    </span>
                  </div>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-6 w-6 text-muted-foreground hover:text-destructive"
                    onClick={() => handleDeleteCategory(category.id)}
                  >
                    <Trash2 className="h-3 w-3" />
                  </Button>
                </div>
                
                {/* 类别名称 */}
                <div className="space-y-1">
                  <Label className="text-[10px] text-muted-foreground">名称</Label>
                  <Input
                    value={category.name}
                    onChange={(e) => handleUpdateCategory(category.id, { name: e.target.value })}
                    placeholder="类别名称"
                    className={cn(
                      'h-8 text-xs',
                      category.name && !isValidVariableName(category.name) && 'border-destructive!'
                    )}
                  />
                </div>
                
                {/* 类别描述 */}
                <div className="space-y-1">
                  <Label className="text-[10px] text-muted-foreground">描述（帮助模型理解）</Label>
                  <Textarea
                    value={category.description}
                    onChange={(e) => handleUpdateCategory(category.id, { description: e.target.value })}
                    placeholder="描述该类别的特征，帮助模型准确分类..."
                    className="min-h-[50px] text-xs resize-none"
                  />
                </div>
              </div>
            ))}
          </div>
        )}
        
        {/* 类别名称校验提示 */}
        {safeConfig.categories.some(c => c.name && !isValidVariableName(c.name)) && (
          <p className="text-[10px] text-destructive">类别名称格式无效（只能包含字母、数字、下划线，不能以数字开头）</p>
        )}
        {(() => {
          const names = safeConfig.categories.map(c => c.name).filter(Boolean)
          const hasDuplicates = new Set(names).size !== names.length
          return hasDuplicates && (
            <p className="text-[10px] text-destructive">存在重复的类别名称</p>
          )
        })()}
        
        <p className="text-[10px] text-muted-foreground">
          每个类别对应一个输出分支，模型会根据问题内容选择最匹配的类别
        </p>
      </div>
    </div>
  )
}
