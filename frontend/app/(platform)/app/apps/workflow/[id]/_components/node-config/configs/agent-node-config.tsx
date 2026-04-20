'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { Search, ChevronDown, Bot, Check, Loader2, Trash2, ExternalLink } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import { useTeam } from '@/contexts/team-context'
import { agentsApi, type AgentListItem, type VariableDefinition } from '@/lib/api/agents'
import { isValidVariableName } from '../utils'
import { extractVariableDisplayName } from '../types'
import type { AvailableVariable } from '../types'

// Agent 节点配置
export interface AgentNodeConfig {
  agentId?: string              // 选中的 Agent ID
  agentName?: string            // Agent 名称（显示用）
  agentDescription?: string     // Agent 描述
  agentIcon?: string            // Agent 图标
  // 输入参数映射 - 基于 Agent 的 variables
  inputMappings: AgentInputMapping[]
  // 消息输入来源
  messageSource: 'variable' | 'constant'
  messageVariableRef?: string   // 消息变量引用
  messageVariableRefNodeLabel?: string
  messageConstantValue?: string // 消息常量值
  // 输出变量
  outputVariable: string
}

// 输入参数映射
export interface AgentInputMapping {
  name: string           // 参数名
  type: string           // 参数类型
  label?: string         // 参数标签
  required: boolean      // 是否必填
  description?: string   // 参数描述
  // 值来源
  source: 'variable' | 'constant'  // 变量引用或常量
  variableRef?: string   // 变量引用 {{node.var}}
  variableRefNodeLabel?: string
  constantValue?: string // 常量值
}

// 默认配置
export const defaultAgentNodeConfig: AgentNodeConfig = {
  inputMappings: [],
  messageSource: 'variable',
  outputVariable: 'response',
}

interface AgentNodeConfigProps {
  config: AgentNodeConfig
  variables: AvailableVariable[]
  variableSearch: string
  openVariablePopover: string | null
  onConfigChange: (config: AgentNodeConfig) => void
  onVariableSearchChange: (search: string) => void
  onOpenVariablePopoverChange: (id: string | null) => void
}

export function AgentNodeConfig({
  config,
  variables,
  variableSearch,
  openVariablePopover,
  onConfigChange,
  onVariableSearchChange,
  onOpenVariablePopoverChange,
}: AgentNodeConfigProps) {
  const t = useTranslations('workflow')
  const { currentTeam } = useTeam()
  const [outputOpen, setOutputOpen] = React.useState(true)
  const [paramsOpen, setParamsOpen] = React.useState(true)
  const [messageOpen, setMessageOpen] = React.useState(true)
  
  // Agent 数据
  const [agents, setAgents] = React.useState<AgentListItem[]>([])
  const [isLoadingAgents, setIsLoadingAgents] = React.useState(false)
  
  // Agent 选择弹窗
  const [agentSelectorOpen, setAgentSelectorOpen] = React.useState(false)
  const [agentSearch, setAgentSearch] = React.useState('')

  // 确保 config 有默认值
  const safeConfig: AgentNodeConfig = {
    ...defaultAgentNodeConfig,
    ...config,
    inputMappings: config.inputMappings || [],
  }

  // 加载 Agent 列表
  React.useEffect(() => {
    const loadAgents = async () => {
      if (!currentTeam) return
      
      setIsLoadingAgents(true)
      try {
        const response = await agentsApi.getAgents({
          teamId: currentTeam.id,
          status: 'published', // 只显示已发布的 Agent
          pageSize: 100,
        })
        setAgents(response.items)
      } catch {
        // 忽略错误
      } finally {
        setIsLoadingAgents(false)
      }
    }
    loadAgents()
  }, [currentTeam])

  // 当选择 Agent 后，加载其详细信息获取变量定义
  React.useEffect(() => {
    const loadAgentDetail = async () => {
      if (!safeConfig.agentId) {
        return
      }

      try {
        const detail = await agentsApi.getAgent(safeConfig.agentId)
        
        // 自动生成输入映射
        if (detail.variables && detail.variables.length > 0) {
          const mappings: AgentInputMapping[] = detail.variables.map((v: VariableDefinition) => ({
            name: v.name,
            type: v.type,
            label: v.label || undefined,
            required: v.required,
            description: v.description || undefined,
            source: 'constant',
            constantValue: v.default || '',
          }))
          
          onConfigChange({
            ...safeConfig,
            inputMappings: mappings,
          })
        }
      } catch {
        // ignore error
      }
    }
    loadAgentDetail()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [safeConfig.agentId])

  // 获取当前选中的 Agent
  const selectedAgent = React.useMemo(() => {
    return agents.find(a => a.id === safeConfig.agentId)
  }, [agents, safeConfig.agentId])

  // 过滤 Agent
  const filteredAgents = React.useMemo(() => {
    if (!agentSearch) return agents
    const query = agentSearch.toLowerCase()
    return agents.filter(a =>
      a.name.toLowerCase().includes(query) ||
      (a.description?.toLowerCase().includes(query) ?? false)
    )
  }, [agents, agentSearch])

  // 选择 Agent
  const handleSelectAgent = (agent: AgentListItem) => {
    onConfigChange({
      ...safeConfig,
      agentId: agent.id,
      agentName: agent.name,
      agentDescription: agent.description || undefined,
      agentIcon: agent.icon || agent.avatar_url || undefined,
      inputMappings: [], // 清空之前的映射，等待加载详情后自动填充
    })
    setAgentSelectorOpen(false)
    setAgentSearch('')
  }

  // 清除 Agent 选择
  const handleClearAgent = () => {
    onConfigChange({
      ...defaultAgentNodeConfig,
      outputVariable: safeConfig.outputVariable,
    })
  }

  // 更新参数映射
  const handleUpdateMapping = (name: string, updates: Partial<AgentInputMapping>) => {
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

  // 渲染变量选择器（通用）
  const renderVariableSelector = (
    popoverId: string,
    currentRef?: string,
    currentLabel?: string,
    onSelect: (variableRef: string, label: string) => void = () => {}
  ) => {
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
          {currentRef ? (
            <>
              <span className="text-primary/80 font-mono text-[10px]">{'{x}'}</span>
              <span className="text-[11px] truncate">
                {currentLabel && <span className="text-muted-foreground">{currentLabel} / </span>}
                {extractVariableDisplayName(currentRef)}
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
                          onSelect(
                            `{{${variable.id}}}`,
                            variable.isSystem ? t('nodesCommon.system') : variable.groupLabel
                          )
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

  // 渲染参数映射的变量选择器
  const renderMappingVariableSelector = (mapping: AgentInputMapping) => {
    const popoverId = `param-${mapping.name}`
    return renderVariableSelector(
      popoverId,
      mapping.variableRef,
      mapping.variableRefNodeLabel,
      (variableRef, label) => {
        handleUpdateMapping(mapping.name, {
          source: 'variable',
          variableRef,
          variableRefNodeLabel: label,
          constantValue: undefined,
        })
      }
    )
  }

  return (
    <div className="space-y-4">
      {/* Agent 选择 */}
      <div className="space-y-2">
        <div className="flex items-center gap-1">
          <Label className="text-xs font-medium">{t('configAgent.selectAgent')}</Label>
          <span className="text-destructive">*</span>
        </div>
        
        {selectedAgent ? (
          // 已选择 Agent
          <div className="flex items-center gap-2 p-2.5 rounded-lg border bg-muted/30">
            <div className="shrink-0 w-8 h-8 rounded-lg bg-indigo-500/10 flex items-center justify-center overflow-hidden">
              {selectedAgent.icon || selectedAgent.avatar_url ? (
                <img 
                  src={selectedAgent.icon || selectedAgent.avatar_url || ''} 
                  alt={selectedAgent.name}
                  className="w-full h-full object-cover"
                />
              ) : (
                <Bot className="h-4 w-4 text-indigo-500" />
              )}
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-1.5">
                <span className="text-sm font-medium truncate">{selectedAgent.name}</span>
                <Badge variant="outline" className="text-[9px] px-1 py-0 bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300">
                  {t('configCommon.published')}
                </Badge>
              </div>
              {selectedAgent.description && (
                <p className="text-[10px] text-muted-foreground line-clamp-1">{selectedAgent.description}</p>
              )}
            </div>
            <div className="flex items-center gap-1">
              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6 shrink-0"
                onClick={() => window.open(`/app/apps/${selectedAgent.id}`, '_blank')}
                title={t('configAgent.viewAgent')}
              >
                <ExternalLink className="h-3 w-3 text-muted-foreground" />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6 shrink-0"
                onClick={handleClearAgent}
              >
                <Trash2 className="h-3 w-3 text-muted-foreground" />
              </Button>
            </div>
          </div>
        ) : (
          // 未选择 Agent
          <Popover open={agentSelectorOpen} onOpenChange={setAgentSelectorOpen}>
            <PopoverTrigger
              className="w-full h-9 flex items-center justify-start gap-2 px-3 text-xs text-muted-foreground bg-background border border-input rounded-md cursor-pointer hover:bg-accent hover:text-accent-foreground"
            >
              {isLoadingAgents ? (
                <>
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  {t('configCommon.loading')}
                </>
              ) : (
                <>
                  <Bot className="h-3.5 w-3.5" />
                  {t('configAgent.selectAgentPlaceholder')}
                </>
              )}
            </PopoverTrigger>
            <PopoverContent className="w-80 p-0" align="start">
              {/* 搜索 */}
              <div className="p-3 border-b">
                <div className="relative">
                  <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
                  <Input
                    placeholder={t('configAgent.searchAgent')}
                    value={agentSearch}
                    onChange={(e) => setAgentSearch(e.target.value)}
                    className="h-8 pl-8 text-xs"
                  />
                </div>
              </div>
              
              {/* Agent 列表 */}
              <ScrollArea className="h-64">
                <div className="p-2 space-y-1">
                  {filteredAgents.length === 0 ? (
                    <div className="flex flex-col items-center justify-center py-8 text-muted-foreground">
                      <Bot className="h-8 w-8 mb-2" />
                      <p className="text-xs">{agentSearch ? t('configAgent.noMatchingAgents') : t('configAgent.noPublishedAgents')}</p>
                      <p className="text-[10px] mt-1">{t('configAgent.onlyPublishedAgents')}</p>
                    </div>
                  ) : (
                    filteredAgents.map(agent => (
                      <button
                        key={agent.id}
                        className={cn(
                          'w-full flex items-center gap-2 p-2 rounded-md text-left transition-colors hover:bg-muted',
                          safeConfig.agentId === agent.id && 'bg-primary/10 border border-primary/30'
                        )}
                        onClick={() => handleSelectAgent(agent)}
                      >
                        <div className="shrink-0 w-7 h-7 rounded-md bg-indigo-500/10 flex items-center justify-center overflow-hidden">
                          {agent.icon || agent.avatar_url ? (
                            <img 
                              src={agent.icon || agent.avatar_url || ''} 
                              alt={agent.name}
                              className="w-full h-full object-cover"
                            />
                          ) : (
                            <Bot className="h-3.5 w-3.5 text-indigo-500" />
                          )}
                        </div>
                        <div className="flex-1 min-w-0">
                          <span className="text-xs font-medium truncate block">{agent.name}</span>
                          {agent.description && (
                            <p className="text-[10px] text-muted-foreground line-clamp-1">{agent.description}</p>
                          )}
                        </div>
                        {safeConfig.agentId === agent.id && (
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

      {/* 消息输入 */}
      {selectedAgent && (
        <Collapsible open={messageOpen} onOpenChange={setMessageOpen}>
          <CollapsibleTrigger className="flex items-center gap-1 text-xs font-medium w-full py-1">
            <ChevronDown className={cn(
              "h-3.5 w-3.5 transition-transform",
              !messageOpen && "-rotate-90"
            )} />
            <span>{t('configAgent.messageInput')}</span>
            <span className="text-destructive">*</span>
          </CollapsibleTrigger>
          <CollapsibleContent className="pt-2 space-y-2">
            <p className="text-[10px] text-muted-foreground">{t('configAgent.messageInputDesc')}</p>
            
            {/* 值来源选择 */}
            <div className="flex gap-2">
              <Button
                variant={safeConfig.messageSource === 'variable' ? 'default' : 'outline'}
                size="sm"
                className="h-6 text-[10px] flex-1"
                onClick={() => onConfigChange({ ...safeConfig, messageSource: 'variable' })}
              >
                {t('configCommon.variable')}
              </Button>
              <Button
                variant={safeConfig.messageSource === 'constant' ? 'default' : 'outline'}
                size="sm"
                className="h-6 text-[10px] flex-1"
                onClick={() => onConfigChange({
                  ...safeConfig,
                  messageSource: 'constant',
                  messageVariableRef: undefined,
                  messageVariableRefNodeLabel: undefined,
                })}
              >
                {t('configCommon.constant')}
              </Button>
            </div>
            
            {/* 值输入 */}
            {safeConfig.messageSource === 'variable' ? (
              renderVariableSelector(
                'message-input',
                safeConfig.messageVariableRef,
                safeConfig.messageVariableRefNodeLabel,
                (variableRef, label) => {
                  onConfigChange({
                    ...safeConfig,
                    messageVariableRef: variableRef,
                    messageVariableRefNodeLabel: label,
                  })
                }
              )
            ) : (
              <Input
                value={safeConfig.messageConstantValue || ''}
                onChange={(e) => onConfigChange({ ...safeConfig, messageConstantValue: e.target.value })}
                placeholder={t('configAgent.enterMessageContent')}
                className="h-8 text-xs"
              />
            )}
          </CollapsibleContent>
        </Collapsible>
      )}

      {/* 输入参数配置（来自 Agent 的 variables） */}
      {selectedAgent && safeConfig.inputMappings.length > 0 && (
        <Collapsible open={paramsOpen} onOpenChange={setParamsOpen}>
          <CollapsibleTrigger className="flex items-center gap-1 text-xs font-medium w-full py-1">
            <ChevronDown className={cn(
              "h-3.5 w-3.5 transition-transform",
              !paramsOpen && "-rotate-90"
            )} />
            <span>{t('configAgent.variableConfig')}</span>
            <span className="text-muted-foreground ml-1">({safeConfig.inputMappings.length})</span>
          </CollapsibleTrigger>
          <CollapsibleContent className="pt-2 space-y-2">
            {safeConfig.inputMappings.map(mapping => (
              <div key={mapping.name} className="bg-muted/30 rounded-lg p-2.5 space-y-2">
                {/* 参数头部 */}
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5">
                    <span className="text-xs font-medium">{mapping.label || mapping.name}</span>
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
                  renderMappingVariableSelector(mapping)
                ) : (
                  <Input
                    value={mapping.constantValue || ''}
                    onChange={(e) => handleUpdateMapping(mapping.name, { constantValue: e.target.value })}
                    placeholder={t('configCommon.enterValueFor', { name: mapping.label || mapping.name })}
                    className="h-8 text-xs"
                  />
                )}
              </div>
            ))}
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
          <span>{t('configCommon.outputVariable')}</span>
          <span className="text-destructive">*</span>
        </CollapsibleTrigger>
        <CollapsibleContent className="pt-2 space-y-2">
          <Input
            value={safeConfig.outputVariable}
            onChange={(e) => onConfigChange({ ...safeConfig, outputVariable: e.target.value })}
            placeholder="response"
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
              <span className="text-xs font-mono font-medium">{safeConfig.outputVariable || 'response'}</span>
              <span className="text-[10px] text-muted-foreground">String</span>
            </div>
            <p className="text-[10px] text-muted-foreground mt-1">{t('configAgent.agentResponseContent')}</p>
          </div>
        </CollapsibleContent>
      </Collapsible>
    </div>
  )
}
