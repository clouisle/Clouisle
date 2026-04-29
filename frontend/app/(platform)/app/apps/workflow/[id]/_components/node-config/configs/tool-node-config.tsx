'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { Trash2, Search, ChevronDown, Wrench, Check, AlertCircle, Loader2, Clock3, Calculator, Globe, FolderOpen, Code2, Link, ChartColumn } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { Badge } from '@/components/ui/badge'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { cn } from '@/lib/utils'
import { useTeam } from '@/contexts/team-context'
import { toolsApi, type Tool, type ToolType, type ToolCategory, type McpToolInfo } from '@/lib/api'
import { isValidVariableName } from '../utils'
import { extractVariableDisplayName } from '../types'
import type { AvailableVariable } from '../types'

// 工具节点配置
export interface ToolNodeConfig {
  toolId?: string              // 工具 ID（custom/mcp 服务器）
  toolName?: string            // 工具名称（builtin）
  toolType: ToolType           // 工具类型
  toolDisplayName?: string     // 工具显示名称
  toolDescription?: string     // 工具描述
  toolIcon?: string            // 工具图标
  toolCategory?: ToolCategory  // 工具分类
  // MCP 特有：服务器中的具体工具
  mcpToolName?: string         // MCP 服务器中的工具名称
  mcpToolDescription?: string  // MCP 工具描述
  // 参数映射
  parameterMappings: ParameterMapping[]
  // 输出变量
  outputVariable: string
}

// 参数映射
export interface ParameterMapping {
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
export const defaultToolNodeConfig: ToolNodeConfig = {
  toolType: 'builtin',
  parameterMappings: [],
  outputVariable: 'result',
}

// 分类图标和颜色
const categoryConfig: Record<ToolCategory, { icon: React.ReactNode; color: string }> = {
  time: { icon: <Clock3 className="h-4 w-4" />, color: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-300' },
  math: { icon: <Calculator className="h-4 w-4" />, color: 'bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-300' },
  search: { icon: <Search className="h-4 w-4" />, color: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300' },
  web: { icon: <Globe className="h-4 w-4" />, color: 'bg-cyan-100 text-cyan-800 dark:bg-cyan-900 dark:text-cyan-300' },
  file: { icon: <FolderOpen className="h-4 w-4" />, color: 'bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-300' },
  code: { icon: <Code2 className="h-4 w-4" />, color: 'bg-pink-100 text-pink-800 dark:bg-pink-900 dark:text-pink-300' },
  api: { icon: <Link className="h-4 w-4" />, color: 'bg-indigo-100 text-indigo-800 dark:bg-indigo-900 dark:text-indigo-300' },
  data: { icon: <ChartColumn className="h-4 w-4" />, color: 'bg-teal-100 text-teal-800 dark:bg-teal-900 dark:text-teal-300' },
  other: { icon: <Wrench className="h-4 w-4" />, color: 'bg-gray-100 text-gray-800 dark:bg-gray-900 dark:text-gray-300' },
}

// 类型标签配置 - 颜色部分
const typeColorConfig: Record<ToolType, string> = {
  builtin: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900 dark:text-emerald-300',
  custom: 'bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-300',
  mcp: 'bg-violet-100 text-violet-800 dark:bg-violet-900 dark:text-violet-300',
  skill: 'bg-sky-100 text-sky-800 dark:bg-sky-900 dark:text-sky-300',
}

// 获取类型标签（需要 t 函数）
function getTypeLabels(t: (key: string) => string): Record<ToolType, string> {
  return {
    builtin: t('configTool.typeBuiltin'),
    custom: t('configTool.typeCustom'),
    mcp: 'MCP',
    skill: 'Skill',
  }
}

interface ToolNodeConfigProps {
  config: ToolNodeConfig
  variables: AvailableVariable[]
  variableSearch: string
  openVariablePopover: string | null
  onConfigChange: (config: ToolNodeConfig) => void
  onVariableSearchChange: (search: string) => void
  onOpenVariablePopoverChange: (id: string | null) => void
}

export function ToolNodeConfig({
  config,
  variables,
  variableSearch,
  openVariablePopover,
  onConfigChange,
  onVariableSearchChange,
  onOpenVariablePopoverChange,
}: ToolNodeConfigProps) {
  const t = useTranslations('workflow')
  const { currentTeam } = useTeam()
  const [outputOpen, setOutputOpen] = React.useState(true)
  const [paramsOpen, setParamsOpen] = React.useState(true)

  // 获取类型标签
  const typeLabels = React.useMemo(() => getTypeLabels(t), [t])
  
  // 工具数据
  const [tools, setTools] = React.useState<Tool[]>([])
  const [isLoadingTools, setIsLoadingTools] = React.useState(false)
  
  // 工具选择弹窗
  const [toolSelectorOpen, setToolSelectorOpen] = React.useState(false)
  const [toolSearch, setToolSearch] = React.useState('')
  const [toolFilter, setToolFilter] = React.useState<'all' | ToolType>('all')
  
  // MCP 工具选择
  const [mcpTools, setMcpTools] = React.useState<McpToolInfo[]>([])
  const [isLoadingMcpTools, setIsLoadingMcpTools] = React.useState(false)
  const [mcpToolSelectorOpen, setMcpToolSelectorOpen] = React.useState(false)
  const [mcpToolSearch, setMcpToolSearch] = React.useState('')

  // 确保 config 有默认值
  const safeConfig: ToolNodeConfig = {
    ...defaultToolNodeConfig,
    ...config,
    parameterMappings: config.parameterMappings || [],
  }

  // 加载工具列表
  React.useEffect(() => {
    const loadTools = async () => {
      if (!currentTeam) return
      
      setIsLoadingTools(true)
      try {
        const response = await toolsApi.list(currentTeam.id)
        const allTools = [...response.builtin, ...response.custom, ...response.mcp]
        setTools(allTools.filter(t => t.is_enabled))
      } catch {
        // 忽略错误
      } finally {
        setIsLoadingTools(false)
      }
    }
    loadTools()
  }, [currentTeam])

  // 获取当前选中的工具信息
  const selectedTool: Tool | undefined = React.useMemo(() => {
    if (!safeConfig.toolId && !safeConfig.toolName) return undefined
    
    return tools.find(t => {
      if (safeConfig.toolType === 'builtin' && t.type === 'builtin') {
        return t.name === safeConfig.toolName
      }
      return t.id === safeConfig.toolId
    })
  }, [safeConfig.toolId, safeConfig.toolName, safeConfig.toolType, tools])

  // 过滤工具
  const filteredTools = React.useMemo(() => {
    let result = tools

    if (toolSearch) {
      const query = toolSearch.toLowerCase()
      result = result.filter(t =>
        t.name.toLowerCase().includes(query) ||
        t.display_name.toLowerCase().includes(query) ||
        t.description.toLowerCase().includes(query)
      )
    }

    if (toolFilter !== 'all') {
      result = result.filter(t => t.type === toolFilter)
    }

    return result
  }, [tools, toolSearch, toolFilter])

  // 按分类分组
  const groupedTools = React.useMemo(() => {
    const groups: Record<string, Tool[]> = {}
    filteredTools.forEach(tool => {
      const category = tool.category
      if (!groups[category]) groups[category] = []
      groups[category].push(tool)
    })
    return groups
  }, [filteredTools])

  // 统计各类型数量
  const typeCounts = React.useMemo(() => ({
    all: tools.length,
    builtin: tools.filter(t => t.type === 'builtin').length,
    custom: tools.filter(t => t.type === 'custom').length,
    mcp: tools.filter(t => t.type === 'mcp').length,
  }), [tools])

  // 当选择 MCP 服务器后，加载其工具列表
  React.useEffect(() => {
    const loadMcpTools = async () => {
      // 只有选择了 MCP 类型且有 mcp_config 时才加载
      if (safeConfig.toolType !== 'mcp' || !selectedTool?.mcp_config) {
        setMcpTools([])
        return
      }
      
      setIsLoadingMcpTools(true)
      try {
        const response = await toolsApi.listMcpTools(selectedTool.mcp_config)
        setMcpTools(response.tools)
      } catch {
        setMcpTools([])
      } finally {
        setIsLoadingMcpTools(false)
      }
    }
    loadMcpTools()
  }, [safeConfig.toolType, safeConfig.toolId, selectedTool?.mcp_config])

  // 过滤 MCP 工具
  const filteredMcpTools = React.useMemo(() => {
    if (!mcpToolSearch) return mcpTools
    const query = mcpToolSearch.toLowerCase()
    return mcpTools.filter(t =>
      t.name.toLowerCase().includes(query) ||
      (t.description?.toLowerCase().includes(query) ?? false)
    )
  }, [mcpTools, mcpToolSearch])

  // 选择工具（内置/自定义）
  const handleSelectTool = (tool: Tool) => {
    if (tool.type === 'mcp') {
      // MCP 工具：先选择服务器，稍后选择具体工具
      onConfigChange({
        ...safeConfig,
        toolId: tool.id,
        toolName: tool.name,
        toolType: tool.type,
        toolDisplayName: tool.display_name,
        toolDescription: tool.description,
        toolIcon: tool.icon,
        toolCategory: tool.category,
        // 清除之前的 MCP 工具选择和参数
        mcpToolName: undefined,
        mcpToolDescription: undefined,
        parameterMappings: [],
      })
      setToolSelectorOpen(false)
      setToolSearch('')
      // 打开 MCP 工具选择器
      setMcpToolSelectorOpen(true)
    } else {
      // 内置/自定义工具：直接使用工具的参数
      const mappings: ParameterMapping[] = tool.parameters.map(p => ({
        name: p.name,
        type: p.type,
        required: p.required,
        description: p.description,
        source: 'constant',
        constantValue: p.default !== undefined ? String(p.default) : '',
      }))

      onConfigChange({
        ...safeConfig,
        toolId: tool.id,
        toolName: tool.name,
        toolType: tool.type,
        toolDisplayName: tool.display_name,
        toolDescription: tool.description,
        toolIcon: tool.icon,
        toolCategory: tool.category,
        mcpToolName: undefined,
        mcpToolDescription: undefined,
        parameterMappings: mappings,
      })
      
      setToolSelectorOpen(false)
      setToolSearch('')
    }
  }

  // 选择 MCP 服务器中的具体工具
  const handleSelectMcpTool = (mcpTool: McpToolInfo) => {
    // 从 MCP 工具的 parameters JSON Schema 中提取参数
    const properties = (mcpTool.parameters as { properties?: Record<string, { type?: string; description?: string }> })?.properties || {}
    const required = (mcpTool.parameters as { required?: string[] })?.required || []
    
    const mappings: ParameterMapping[] = Object.entries(properties).map(([name, schema]) => ({
      name,
      type: schema.type || 'string',
      required: required.includes(name),
      description: schema.description,
      source: 'constant',
      constantValue: '',
    }))

    onConfigChange({
      ...safeConfig,
      mcpToolName: mcpTool.name,
      mcpToolDescription: mcpTool.description,
      parameterMappings: mappings,
    })
    
    setMcpToolSelectorOpen(false)
    setMcpToolSearch('')
  }

  // 清除工具选择
  const handleClearTool = () => {
    onConfigChange({
      ...defaultToolNodeConfig,
      outputVariable: safeConfig.outputVariable,
    })
  }

  // 更新参数映射
  const handleUpdateMapping = (name: string, updates: Partial<ParameterMapping>) => {
    onConfigChange({
      ...safeConfig,
      parameterMappings: safeConfig.parameterMappings.map(m =>
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
  const renderVariableSelector = (mapping: ParameterMapping) => {
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
                            variableRefNodeLabel: variable.isSystem ? t('nodesCommon.system') : variable.groupLabel,
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
      {/* 工具选择 */}
      <div className="space-y-2">
        <div className="flex items-center gap-1">
          <Label className="text-xs font-medium">{t('configTool.tool')}</Label>
          <span className="text-destructive">*</span>
        </div>
        
        {selectedTool ? (
          // 已选择工具
          <div className="flex items-center gap-2 p-2.5 rounded-lg border bg-muted/30">
            <div className="shrink-0 w-8 h-8 rounded-lg bg-emerald-500/10 flex items-center justify-center text-lg">
              {selectedTool.icon || categoryConfig[selectedTool.category]?.icon || '⚙️'}
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-1.5">
                <span className="text-sm font-medium truncate">{selectedTool.display_name}</span>
                <Badge variant="outline" className={cn('text-[9px] px-1 py-0', typeColorConfig[selectedTool.type])}>
                  {typeLabels[selectedTool.type]}
                </Badge>
              </div>
              <p className="text-[10px] text-muted-foreground line-clamp-1">{selectedTool.description}</p>
            </div>
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6 shrink-0"
              onClick={handleClearTool}
            >
              <Trash2 className="h-3 w-3 text-muted-foreground" />
            </Button>
          </div>
        ) : (
          // 未选择工具
          <Popover open={toolSelectorOpen} onOpenChange={setToolSelectorOpen}>
            <PopoverTrigger
              className="w-full h-9 flex items-center justify-start gap-2 px-3 text-xs text-muted-foreground bg-background border border-input rounded-md cursor-pointer hover:bg-accent hover:text-accent-foreground"
            >
              {isLoadingTools ? (
                <>
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  {t('configCommon.loading')}
                </>
              ) : (
                <>
                  <Wrench className="h-3.5 w-3.5" />
                  {t('configTool.selectTool')}
                </>
              )}
            </PopoverTrigger>
            <PopoverContent className="w-96 p-0" align="start">
              {/* 搜索和过滤 */}
              <div className="p-3 border-b space-y-2">
                <div className="relative">
                  <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
                  <Input
                    placeholder={t('configTool.searchTools')}
                    value={toolSearch}
                    onChange={(e) => setToolSearch(e.target.value)}
                    className="h-8 pl-8 text-xs"
                  />
                </div>
                <Tabs value={toolFilter} onValueChange={(v) => setToolFilter(v as 'all' | ToolType)}>
                  <TabsList className="h-7">
                    <TabsTrigger value="all" className="text-[10px] h-5 px-2">{t('configTool.filterAll')} ({typeCounts.all})</TabsTrigger>
                    <TabsTrigger value="builtin" className="text-[10px] h-5 px-2">{t('configTool.filterBuiltin')} ({typeCounts.builtin})</TabsTrigger>
                    <TabsTrigger value="custom" className="text-[10px] h-5 px-2" disabled={typeCounts.custom === 0}>{t('configTool.filterCustom')} ({typeCounts.custom})</TabsTrigger>
                    <TabsTrigger value="mcp" className="text-[10px] h-5 px-2" disabled={typeCounts.mcp === 0}>MCP ({typeCounts.mcp})</TabsTrigger>
                  </TabsList>
                </Tabs>
              </div>
              
              {/* 工具列表 */}
              <ScrollArea className="h-72">
                <div className="p-2 space-y-3">
                  {Object.keys(groupedTools).length === 0 ? (
                    <div className="flex flex-col items-center justify-center py-8 text-muted-foreground">
                      <Wrench className="h-8 w-8 mb-2" />
                      <p className="text-xs">{toolSearch ? t('configTool.noMatchingTools') : t('configTool.noAvailableTools')}</p>
                    </div>
                  ) : (
                    Object.entries(groupedTools).map(([category, categoryTools]: [string, Tool[]]) => {
                      // 创建局部引用避免 TypeScript 闭包类型推断问题
                      const currentSelectedTool = selectedTool as Tool | undefined
                      return (
                      <div key={category}>
                        <div className="text-[10px] font-medium text-muted-foreground mb-1 flex items-center gap-1">
                          <span>{categoryConfig[category as ToolCategory]?.icon || '⚙️'}</span>
                          {category}
                        </div>
                        <div className="space-y-1">
                          {categoryTools.map((tool: Tool) => {
                            const isSelected = currentSelectedTool?.id === tool.id || 
                              (tool.type === 'builtin' && currentSelectedTool?.name === tool.name)
                            
                            return (
                              <button
                                key={tool.id || tool.name}
                                className={cn(
                                  'w-full flex items-center gap-2 p-2 rounded-md text-left transition-colors',
                                  isSelected ? 'bg-primary/10 border border-primary/30' : 'hover:bg-muted'
                                )}
                                onClick={() => handleSelectTool(tool)}
                              >
                                <div className="shrink-0 w-7 h-7 rounded-md bg-muted flex items-center justify-center text-sm">
                                  {tool.icon || categoryConfig[tool.category]?.icon || '⚙️'}
                                </div>
                                <div className="flex-1 min-w-0">
                                  <div className="flex items-center gap-1">
                                    <span className="text-xs font-medium truncate">{tool.display_name}</span>
                                    {tool.requires_config && (
                                      <AlertCircle className="h-3 w-3 text-amber-500 shrink-0" />
                                    )}
                                  </div>
                                  <p className="text-[10px] text-muted-foreground line-clamp-1">{tool.description}</p>
                                </div>
                                {isSelected && (
                                  <Check className="h-4 w-4 text-primary shrink-0" />
                                )}
                              </button>
                            )
                          })}
                        </div>
                      </div>
                      )
                    })
                  )}
                </div>
              </ScrollArea>
            </PopoverContent>
          </Popover>
        )}
      </div>

      {/* MCP 工具选择（仅 MCP 类型显示）*/}
      {selectedTool?.type === 'mcp' && (
        <div className="space-y-2">
          <div className="flex items-center gap-1">
            <Label className="text-xs font-medium">{t('configTool.mcpTool')}</Label>
            <span className="text-destructive">*</span>
          </div>
          
          {safeConfig.mcpToolName ? (
            // 已选择 MCP 工具
            <div className="flex items-center gap-2 p-2.5 rounded-lg border bg-violet-500/5 border-violet-500/20">
              <div className="shrink-0 w-7 h-7 rounded-md bg-violet-500/10 flex items-center justify-center text-sm">
                🔧
              </div>
              <div className="flex-1 min-w-0">
                <span className="text-sm font-medium">{safeConfig.mcpToolName}</span>
                {safeConfig.mcpToolDescription && (
                  <p className="text-[10px] text-muted-foreground line-clamp-1">{safeConfig.mcpToolDescription}</p>
                )}
              </div>
              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6 shrink-0"
                onClick={() => {
                  onConfigChange({
                    ...safeConfig,
                    mcpToolName: undefined,
                    mcpToolDescription: undefined,
                    parameterMappings: [],
                  })
                }}
              >
                <Trash2 className="h-3 w-3 text-muted-foreground" />
              </Button>
            </div>
          ) : (
            // 未选择 MCP 工具
            <Popover open={mcpToolSelectorOpen} onOpenChange={setMcpToolSelectorOpen}>
              <PopoverTrigger
                className="w-full h-9 flex items-center justify-start gap-2 px-3 text-xs text-muted-foreground bg-background border border-input rounded-md cursor-pointer hover:bg-accent hover:text-accent-foreground"
              >
                {isLoadingMcpTools ? (
                  <>
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    {t('configTool.connectingMcpServer')}
                  </>
                ) : (
                  <>
                    <Wrench className="h-3.5 w-3.5" />
                    {t('configTool.selectMcpTool', { count: mcpTools.length })}
                  </>
                )}
              </PopoverTrigger>
              <PopoverContent className="w-80 p-0" align="start">
                <div className="p-3 border-b">
                  <div className="relative">
                    <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
                    <Input
                      placeholder={t('configTool.searchMcpTools')}
                      value={mcpToolSearch}
                      onChange={(e) => setMcpToolSearch(e.target.value)}
                      className="h-8 pl-8 text-xs"
                    />
                  </div>
                </div>
                <ScrollArea className="h-64">
                  <div className="p-2 space-y-1">
                    {filteredMcpTools.length === 0 ? (
                      <div className="flex flex-col items-center justify-center py-8 text-muted-foreground">
                        <Wrench className="h-8 w-8 mb-2" />
                        <p className="text-xs">{mcpToolSearch ? t('configTool.noMatchingTools') : t('configTool.noAvailableTools')}</p>
                      </div>
                    ) : (
                      filteredMcpTools.map(mcpTool => (
                        <button
                          key={mcpTool.name}
                          className={cn(
                            'w-full flex items-center gap-2 p-2 rounded-md text-left transition-colors hover:bg-muted',
                            safeConfig.mcpToolName === mcpTool.name && 'bg-primary/10 border border-primary/30'
                          )}
                          onClick={() => handleSelectMcpTool(mcpTool)}
                        >
                          <div className="shrink-0 w-7 h-7 rounded-md bg-violet-500/10 flex items-center justify-center text-sm">
                            🔧
                          </div>
                          <div className="flex-1 min-w-0">
                            <span className="text-xs font-medium">{mcpTool.name}</span>
                            {mcpTool.description && (
                              <p className="text-[10px] text-muted-foreground line-clamp-1">{mcpTool.description}</p>
                            )}
                          </div>
                          {safeConfig.mcpToolName === mcpTool.name && (
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
      )}

      {/* 参数配置 - MCP 类型需要选择具体工具后才显示 */}
      {selectedTool && safeConfig.parameterMappings.length > 0 && 
       (selectedTool.type !== 'mcp' || safeConfig.mcpToolName) && (
        <Collapsible open={paramsOpen} onOpenChange={setParamsOpen}>
          <CollapsibleTrigger className="flex items-center gap-1 text-xs font-medium w-full py-1">
            <ChevronDown className={cn(
              "h-3.5 w-3.5 transition-transform",
              !paramsOpen && "-rotate-90"
            )} />
            <span>{t('configTool.parameterConfig')}</span>
            <span className="text-muted-foreground ml-1">({safeConfig.parameterMappings.length})</span>
          </CollapsibleTrigger>
          <CollapsibleContent className="pt-2 space-y-2">
            {safeConfig.parameterMappings.map(mapping => (
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
              <span className="text-[10px] text-muted-foreground">Any</span>
            </div>
            <p className="text-[10px] text-muted-foreground mt-1">{t('configTool.executionResult')}</p>
          </div>
        </CollapsibleContent>
      </Collapsible>
    </div>
  )
}
