'use client'

import * as React from 'react'
import { Search, ChevronDown, Workflow, Check, Loader2, Trash2, ExternalLink } from 'lucide-react'
import { useTranslations } from 'next-intl'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import { useTeam } from '@/contexts/team-context'
import { workflowsApi, type WorkflowListItem } from '@/lib/api/workflows'
import { isValidVariableName } from '../utils'
import { extractVariableDisplayName } from '../types'
import type { AvailableVariable } from '../types'

// 子工作流节点配置
export interface SubWorkflowNodeConfig {
  workflowId?: string           // 选中的工作流 ID
  workflowName?: string         // 工作流名称（显示用）
  workflowDescription?: string  // 工作流描述
  // 输入参数映射
  inputMappings: InputMapping[]
  // 输出变量
  outputVariable: string
}

// 输入参数映射
export interface InputMapping {
  name: string           // 参数名
  type: string           // 参数类型
  required: boolean      // 是否必填
  description?: string   // 参数描述
  // 值来源
  source: 'variable' | 'constant'  // 变量引用或常量
  variableRef?: string   // 变量引用 {{node.var}}
  variableRefNodeLabel?: string
  constantValue?: string // 常量值
}

// 默认配置
export const defaultSubWorkflowNodeConfig: SubWorkflowNodeConfig = {
  inputMappings: [],
  outputVariable: 'result',
}

interface SubWorkflowNodeConfigProps {
  config: SubWorkflowNodeConfig
  variables: AvailableVariable[]
  variableSearch: string
  openVariablePopover: string | null
  onConfigChange: (config: SubWorkflowNodeConfig) => void
  onVariableSearchChange: (search: string) => void
  onOpenVariablePopoverChange: (id: string | null) => void
}

export function SubWorkflowNodeConfig({
  config,
  variables,
  variableSearch,
  openVariablePopover,
  onConfigChange,
  onVariableSearchChange,
  onOpenVariablePopoverChange,
}: SubWorkflowNodeConfigProps) {
  const t = useTranslations('workflow')
  const { currentTeam } = useTeam()
  const [outputOpen, setOutputOpen] = React.useState(true)
  const [paramsOpen, setParamsOpen] = React.useState(true)
  
  // 工作流数据
  const [workflows, setWorkflows] = React.useState<WorkflowListItem[]>([])
  const [isLoadingWorkflows, setIsLoadingWorkflows] = React.useState(false)
  const [selectedWorkflowDetail, setSelectedWorkflowDetail] = React.useState<{ variables: Array<{ name: string; type: string; required: boolean; description?: string | null }> } | null>(null)
  
  // 工作流选择弹窗
  const [workflowSelectorOpen, setWorkflowSelectorOpen] = React.useState(false)
  const [workflowSearch, setWorkflowSearch] = React.useState('')

  // 确保 config 有默认值
  const safeConfig: SubWorkflowNodeConfig = {
    ...defaultSubWorkflowNodeConfig,
    ...config,
    inputMappings: config.inputMappings || [],
  }

  // 加载工作流列表
  React.useEffect(() => {
    const loadWorkflows = async () => {
      if (!currentTeam) return
      
      setIsLoadingWorkflows(true)
      try {
        const response = await workflowsApi.getWorkflows({
          teamId: currentTeam.id,
          status: 'published', // 只显示已发布的工作流
          pageSize: 100,
        })
        setWorkflows(response.items)
      } catch {
        // 忽略错误
      } finally {
        setIsLoadingWorkflows(false)
      }
    }
    loadWorkflows()
  }, [currentTeam])

  // 当选择工作流后，加载其详细信息获取输入变量
  React.useEffect(() => {
    const loadWorkflowDetail = async () => {
      if (!safeConfig.workflowId) {
        setSelectedWorkflowDetail(null)
        return
      }
      
      try {
        const detail = await workflowsApi.getWorkflow(safeConfig.workflowId)
        
        // 优先使用 variables 字段，如果为空则从 definition.nodes 中提取
        let variables = detail.variables || []
        
        // 如果 variables 为空，尝试从开始节点提取参数
        if (variables.length === 0 && detail.definition?.nodes) {
          const startNode = detail.definition.nodes.find((n: { type?: string; data?: { type?: string } }) => 
            n.type === 'user_input' || n.type === 'trigger' || n.type === 'start' ||
            n.data?.type === 'user_input' || n.data?.type === 'trigger' || n.data?.type === 'start'
          )
          
          if (startNode) {
            const nodeData = startNode.data as { parameters?: Array<{
              name: string
              type: string
              required: boolean
              defaultValue?: string
              description?: string
            }> }
            
            const parameters = nodeData?.parameters || []
            variables = parameters.map(p => ({
              name: p.name,
              type: p.type,
              required: p.required,
              default: p.defaultValue,
              description: p.description || null,
            }))
          }
        }
        
        setSelectedWorkflowDetail({
          variables,
        })
        
        // 自动生成输入映射（仅当没有现有映射或工作流变更时）
        if (variables.length > 0) {
          // 保留已有的映射配置（用户可能已经设置了值）
          const existingMappings = safeConfig.inputMappings || []
          const existingMappingMap = new Map(existingMappings.map(m => [m.name, m]))
          
          const mappings: InputMapping[] = variables.map(v => {
            const existing = existingMappingMap.get(v.name)
            if (existing && existing.type === v.type) {
              // 保留用户已配置的值
              return {
                ...existing,
                required: v.required,
                description: v.description || undefined,
              }
            }
            // 新参数或类型变更，使用默认值
            return {
              name: v.name,
              type: v.type,
              required: v.required,
              description: v.description || undefined,
              source: 'constant',
              constantValue: v.default !== undefined ? String(v.default) : '',
            }
          })
          
          // 只有映射有变化时才更新
          const hasChanges = mappings.length !== existingMappings.length ||
            mappings.some((m, i) => m.name !== existingMappings[i]?.name)
          
          if (hasChanges || existingMappings.length === 0) {
            onConfigChange({
              ...safeConfig,
              inputMappings: mappings,
            })
          }
        } else if (safeConfig.inputMappings.length > 0) {
          // 目标工作流没有输入参数，清空映射
          onConfigChange({
            ...safeConfig,
            inputMappings: [],
          })
        }
      } catch {
        setSelectedWorkflowDetail(null)
      }
    }
    loadWorkflowDetail()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [safeConfig.workflowId])

  // 获取当前选中的工作流
  const selectedWorkflow = React.useMemo(() => {
    return workflows.find(w => w.id === safeConfig.workflowId)
  }, [workflows, safeConfig.workflowId])

  // 过滤工作流
  const filteredWorkflows = React.useMemo(() => {
    if (!workflowSearch) return workflows
    const query = workflowSearch.toLowerCase()
    return workflows.filter(w =>
      w.name.toLowerCase().includes(query) ||
      (w.description?.toLowerCase().includes(query) ?? false)
    )
  }, [workflows, workflowSearch])

  // 选择工作流
  const handleSelectWorkflow = (workflow: WorkflowListItem) => {
    onConfigChange({
      ...safeConfig,
      workflowId: workflow.id,
      workflowName: workflow.name,
      workflowDescription: workflow.description || undefined,
      inputMappings: [], // 清空之前的映射，等待加载详情后自动填充
    })
    setWorkflowSelectorOpen(false)
    setWorkflowSearch('')
  }

  // 清除工作流选择
  const handleClearWorkflow = () => {
    onConfigChange({
      ...defaultSubWorkflowNodeConfig,
      outputVariable: safeConfig.outputVariable,
    })
    setSelectedWorkflowDetail(null)
  }

  // 更新参数映射
  const handleUpdateMapping = (name: string, updates: Partial<InputMapping>) => {
    onConfigChange({
      ...safeConfig,
      inputMappings: safeConfig.inputMappings.map(m =>
        m.name === name ? { ...m, ...updates } : m
      ),
    })
  }

  // 过滤变量
  const filterVariables = (search: string) => {
    if (!search) return variables
    return variables.filter(v =>
      v.name.toLowerCase().includes(search.toLowerCase())
    )
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

  // 渲染变量选择器
  const renderVariableSelector = (mapping: InputMapping) => {
    const popoverId = `param-${mapping.name}`

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
            'w-full h-8 flex items-center justify-start gap-1 px-2 text-xs bg-background border border-input rounded-md cursor-pointer hover:bg-accent hover:text-accent-foreground',
          )}
        >
          {mapping.variableRef ? (
            <>
              <span className="text-primary/80 font-mono text-[10px]">{'{x}'}</span>
              <span className="text-[11px] truncate">
                {mapping.variableRefNodeLabel && <span className="text-muted-foreground">{mapping.variableRefNodeLabel} / </span>}
                {extractVariableDisplayName(mapping.variableRef)}
              </span>
            </>
          ) : (
            <span className="text-muted-foreground text-[11px]">{t('configCommon.selectVariable')}</span>
          )}
        </PopoverTrigger>
        <PopoverContent className="w-64 p-0" align="start">
          <div className="p-2 border-b">
            <div className="relative">
              <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3 w-3 text-muted-foreground" />
              <Input
                placeholder={t('configCommon.searchVariable')}
                value={variableSearch}
                onChange={(e) => onVariableSearchChange(e.target.value)}
                className="h-7 pl-7 text-xs"
              />
            </div>
          </div>
          <ScrollArea className="h-48">
            <div className="p-1">
              {(() => {
                const filtered = filterVariables(variableSearch)
                const groupEntries = groupVariables(filtered)

                if (groupEntries.length === 0) {
                  return (
                    <div className="py-4 text-center text-xs text-muted-foreground">
                      {t('configCommon.noMatchingVariables')}
                    </div>
                  )
                }

                return groupEntries.map(([groupId, group]) => (
                  <div key={groupId} className="mb-1">
                    <div className="px-2 py-1 text-[10px] text-muted-foreground font-medium">
                      {group.label}
                    </div>
                    {group.items.map(variable => (
                      <button
                        key={variable.id}
                        className="w-full flex items-center justify-between px-2 py-1 text-xs hover:bg-muted rounded-md"
                        onClick={() => {
                          // 使用 variable.id（格式为 nodeId.paramName）而不是 variable.name
                          handleUpdateMapping(mapping.name, {
                            source: 'variable',
                            variableRef: `{{${variable.id}}}`,
                            variableRefNodeLabel: variable.isSystem ? 'SYSTEM' : variable.groupLabel,
                            constantValue: undefined,
                          })
                          onOpenVariablePopoverChange(null)
                          onVariableSearchChange('')
                        }}
                      >
                        <span className="flex items-center gap-1">
                          <span className={cn(
                            'font-mono text-[10px]',
                            variable.isSystem ? 'text-orange-500' : 'text-primary/80'
                          )}>{'{x}'}</span>
                          <span className="text-[11px]">{variable.name}</span>
                        </span>
                        <span className="text-[10px] text-muted-foreground">{variable.type}</span>
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
      {/* 工作流选择 */}
      <div className="space-y-2">
        <div className="flex items-center gap-1">
          <Label className="text-xs font-medium">{t('configSubWorkflow.selectWorkflow')}</Label>
          <span className="text-destructive">*</span>
        </div>
        
        {safeConfig.workflowId ? (
          // 已选择工作流
          <div className="flex items-center gap-2 p-2.5 rounded-lg border bg-muted/30">
            <div className="shrink-0 w-8 h-8 rounded-lg bg-purple-500/10 flex items-center justify-center">
              <Workflow className="h-4 w-4 text-purple-500" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-1.5">
                <span className="text-sm font-medium truncate">
                  {selectedWorkflow?.name || safeConfig.workflowName || t('configSubWorkflow.unknownWorkflow')}
                </span>
                {selectedWorkflow ? (
                  <Badge variant="outline" className="text-[9px] px-1 py-0 bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300">
                    {t('configCommon.published')}
                  </Badge>
                ) : (
                  <Badge variant="outline" className="text-[9px] px-1 py-0 bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-300">
                    {t('configCommon.unpublished')}
                  </Badge>
                )}
              </div>
              {(selectedWorkflow?.description || safeConfig.workflowDescription) && (
                <p className="text-[10px] text-muted-foreground line-clamp-1">
                  {selectedWorkflow?.description || safeConfig.workflowDescription}
                </p>
              )}
            </div>
            <div className="flex items-center gap-1">
              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6 shrink-0"
                onClick={() => window.open(`/app/apps/workflow/${safeConfig.workflowId}`, '_blank')}
                title={t('configSubWorkflow.viewWorkflow')}
              >
                <ExternalLink className="h-3 w-3 text-muted-foreground" />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6 shrink-0"
                onClick={handleClearWorkflow}
              >
                <Trash2 className="h-3 w-3 text-muted-foreground" />
              </Button>
            </div>
          </div>
        ) : (
          // 未选择工作流
          <Popover open={workflowSelectorOpen} onOpenChange={setWorkflowSelectorOpen}>
            <PopoverTrigger
              className="w-full h-9 flex items-center justify-start gap-2 px-3 text-xs text-muted-foreground bg-background border border-input rounded-md cursor-pointer hover:bg-accent hover:text-accent-foreground"
            >
              {isLoadingWorkflows ? (
                <>
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  {t('configCommon.loading')}
                </>
              ) : (
                <>
                  <Workflow className="h-3.5 w-3.5" />
                  {t('configSubWorkflow.selectWorkflowPlaceholder')}
                </>
              )}
            </PopoverTrigger>
            <PopoverContent className="w-80 p-0" align="start">
              {/* 搜索 */}
              <div className="p-3 border-b">
                <div className="relative">
                  <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
                  <Input
                    placeholder={t('configSubWorkflow.searchWorkflows')}
                    value={workflowSearch}
                    onChange={(e) => setWorkflowSearch(e.target.value)}
                    className="h-8 pl-8 text-xs"
                  />
                </div>
              </div>
              
              {/* 工作流列表 */}
              <ScrollArea className="h-64">
                <div className="p-2 space-y-1">
                  {filteredWorkflows.length === 0 ? (
                    <div className="flex flex-col items-center justify-center py-8 text-muted-foreground">
                      <Workflow className="h-8 w-8 mb-2" />
                      <p className="text-xs">{workflowSearch ? t('configSubWorkflow.noMatchingWorkflows') : t('configSubWorkflow.noPublishedWorkflows')}</p>
                      <p className="text-[10px] mt-1">{t('configSubWorkflow.onlyPublishedHint')}</p>
                    </div>
                  ) : (
                    filteredWorkflows.map(workflow => (
                      <button
                        key={workflow.id}
                        className={cn(
                          'w-full flex items-center gap-2 p-2 rounded-md text-left transition-colors hover:bg-muted',
                          safeConfig.workflowId === workflow.id && 'bg-primary/10 border border-primary/30'
                        )}
                        onClick={() => handleSelectWorkflow(workflow)}
                      >
                        <div className="shrink-0 w-7 h-7 rounded-md bg-purple-500/10 flex items-center justify-center">
                          <Workflow className="h-3.5 w-3.5 text-purple-500" />
                        </div>
                        <div className="flex-1 min-w-0">
                          <span className="text-xs font-medium truncate block">{workflow.name}</span>
                          {workflow.description && (
                            <p className="text-[10px] text-muted-foreground line-clamp-1">{workflow.description}</p>
                          )}
                        </div>
                        {safeConfig.workflowId === workflow.id && (
                          <Check className="h-4 w-4 text-primary shrink-0" />
                        )}
                      </button>
                    ))
                  )}
                </div>
              </ScrollArea>
            </PopoverContent>
          </Popover>
        )}
      </div>

      {/* 输入参数配置 */}
      {safeConfig.workflowId && (
        <Collapsible open={paramsOpen} onOpenChange={setParamsOpen}>
          <CollapsibleTrigger className="flex items-center gap-1 text-xs font-medium w-full py-1">
            <ChevronDown className={cn(
              "h-3.5 w-3.5 transition-transform",
              !paramsOpen && "-rotate-90"
            )} />
            <span>{t('configCommon.inputParameters')}</span>
            <span className="text-muted-foreground ml-1">({safeConfig.inputMappings.length})</span>
          </CollapsibleTrigger>
          <CollapsibleContent className="pt-2 space-y-2">
            {safeConfig.inputMappings.length === 0 ? (
              <div className="bg-muted/30 rounded-lg p-3 text-center">
                <p className="text-xs text-muted-foreground">{t('configSubWorkflow.noInputParams')}</p>
                <p className="text-[10px] text-muted-foreground mt-1">
                  {t('configSubWorkflow.noInputParamsHint')}
                </p>
              </div>
            ) : (
              safeConfig.inputMappings.map(mapping => (
              <div key={mapping.name} className="bg-muted/30 rounded-lg p-2.5 space-y-2">
                {/* 参数头部 */}
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5">
                    <span className="text-xs font-medium">{mapping.name}</span>
                    <span className="text-[10px] text-muted-foreground">{mapping.type}</span>
                    {mapping.required && (
                      <span className="text-[10px] text-destructive">*</span>
                    )}
                  </div>
                </div>
                
                {/* 参数描述 */}
                {mapping.description && (
                  <p className="text-[10px] text-muted-foreground">{mapping.description}</p>
                )}
                
                {/* 值来源选择 */}
                <div className="flex gap-2">
                  <Button
                    variant={mapping.source === 'variable' ? 'default' : 'outline'}
                    size="sm"
                    className="h-6 text-[10px] flex-1"
                    onClick={() => handleUpdateMapping(mapping.name, { source: 'variable' })}
                  >
                    {t('configCommon.variable')}
                  </Button>
                  <Button
                    variant={mapping.source === 'constant' ? 'default' : 'outline'}
                    size="sm"
                    className="h-6 text-[10px] flex-1"
                    onClick={() => handleUpdateMapping(mapping.name, { source: 'constant', variableRef: undefined, variableRefNodeLabel: undefined })}
                  >
                    {t('configCommon.constant')}
                  </Button>
                </div>
                
                {/* 值输入 */}
                {mapping.source === 'variable' ? (
                  renderVariableSelector(mapping)
                ) : (
                  <Input
                    value={mapping.constantValue || ''}
                    onChange={(e) => handleUpdateMapping(mapping.name, { constantValue: e.target.value })}
                    placeholder={t('configCommon.enterValueFor', { name: mapping.name })}
                    className="h-8 text-xs"
                  />
                )}
              </div>
            ))
            )}
          </CollapsibleContent>
        </Collapsible>
      )}

      {/* 输出变量 */}
      <Collapsible open={outputOpen} onOpenChange={setOutputOpen}>
        <CollapsibleTrigger className="flex items-center gap-1 text-xs font-medium w-full py-1">
          <ChevronDown className={cn(
            "h-3.5 w-3.5 transition-transform",
            !outputOpen && "-rotate-90"
          )} />
          <span>{t('configCommon.outputVariables')}</span>
          <span className="text-destructive">*</span>
        </CollapsibleTrigger>
        <CollapsibleContent className="pt-2 space-y-2">
          <Input
            value={safeConfig.outputVariable}
            onChange={(e) => onConfigChange({ ...safeConfig, outputVariable: e.target.value })}
            placeholder="result"
            className={cn(
              'h-9 text-xs font-mono',
              safeConfig.outputVariable && !isValidVariableName(safeConfig.outputVariable) && 'border-destructive!'
            )}
          />
          {safeConfig.outputVariable && !isValidVariableName(safeConfig.outputVariable) && (
            <p className="text-[10px] text-destructive">{t('configCommon.invalidVariableName')}</p>
          )}
          
          {/* 输出预览 */}
          <div className="bg-muted/30 rounded-lg p-2.5">
            <div className="flex items-center gap-2">
              <span className="text-xs font-mono font-medium">{safeConfig.outputVariable || 'result'}</span>
              <span className="text-[10px] text-muted-foreground">Object</span>
            </div>
            <p className="text-[10px] text-muted-foreground mt-1">{t('configSubWorkflow.executionResult')}</p>
          </div>
        </CollapsibleContent>
      </Collapsible>
    </div>
  )
}
