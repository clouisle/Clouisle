'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { Search, ChevronDown, Database, Check, Loader2, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Slider } from '@/components/ui/slider'
import { cn } from '@/lib/utils'
import { useTeam } from '@/contexts/team-context'
import { knowledgeBasesApi } from '@/lib/api/knowledge-bases'
import { isValidVariableName } from '../utils'
import { extractVariableDisplayName } from '../types'
import type { AvailableVariable } from '../types'

// 知识库检索节点配置
export interface KnowledgeRetrievalNodeConfig {
  knowledgeBaseId?: string
  knowledgeBaseName?: string
  // 查询输入
  querySource: 'variable' | 'constant'
  queryVariableRef?: string
  queryVariableRefNodeLabel?: string
  queryConstantValue?: string
  // 检索配置
  searchMode: 'vector' | 'fulltext' | 'hybrid'
  topK: number
  threshold: number
  // 输出变量
  outputVariable: string
}

export const defaultKnowledgeRetrievalNodeConfig: KnowledgeRetrievalNodeConfig = {
  querySource: 'variable',
  searchMode: 'hybrid',
  topK: 5,
  threshold: 0.0,
  outputVariable: 'results',
}

interface KnowledgeRetrievalNodeConfigProps {
  config: KnowledgeRetrievalNodeConfig
  variables: AvailableVariable[]
  variableSearch: string
  openVariablePopover: string | null
  onConfigChange: (config: KnowledgeRetrievalNodeConfig) => void
  onVariableSearchChange: (search: string) => void
  onOpenVariablePopoverChange: (id: string | null) => void
}

export function KnowledgeRetrievalNodeConfig({
  config,
  variables,
  variableSearch,
  openVariablePopover,
  onConfigChange,
  onVariableSearchChange,
  onOpenVariablePopoverChange,
}: KnowledgeRetrievalNodeConfigProps) {
  const t = useTranslations('workflow')
  const { currentTeam } = useTeam()
  const [outputOpen, setOutputOpen] = React.useState(true)
  const [queryOpen, setQueryOpen] = React.useState(true)
  const [settingsOpen, setSettingsOpen] = React.useState(true)

  // 知识库数据
  const [knowledgeBases, setKnowledgeBases] = React.useState<any[]>([])
  const [isLoadingKbs, setIsLoadingKbs] = React.useState(false)

  // 知识库选择弹窗
  const [kbSelectorOpen, setKbSelectorOpen] = React.useState(false)
  const [kbSearch, setKbSearch] = React.useState('')

  // 确保 config 有默认值
  const safeConfig: KnowledgeRetrievalNodeConfig = {
    ...defaultKnowledgeRetrievalNodeConfig,
    ...config,
  }

  // 加载知识库列表
  React.useEffect(() => {
    const loadKnowledgeBases = async () => {
      if (!currentTeam) return

      setIsLoadingKbs(true)
      try {
        const response = await knowledgeBasesApi.getKnowledgeBases({
          teamId: currentTeam.id,
          pageSize: 100,
        })
        setKnowledgeBases(response.items || [])
      } catch {
        // 忽略错误
      } finally {
        setIsLoadingKbs(false)
      }
    }
    loadKnowledgeBases()
  }, [currentTeam])

  // 获取当前选中的知识库
  const selectedKb = React.useMemo(() => {
    return knowledgeBases.find(kb => kb.id === safeConfig.knowledgeBaseId)
  }, [knowledgeBases, safeConfig.knowledgeBaseId])

  // 过滤知识库
  const filteredKbs = React.useMemo(() => {
    if (!kbSearch) return knowledgeBases
    const query = kbSearch.toLowerCase()
    return knowledgeBases.filter(kb =>
      kb.name.toLowerCase().includes(query) ||
      (kb.description?.toLowerCase().includes(query) ?? false)
    )
  }, [knowledgeBases, kbSearch])

  // 选择知识库
  const handleSelectKb = (kb: any) => {
    onConfigChange({
      ...safeConfig,
      knowledgeBaseId: kb.id,
      knowledgeBaseName: kb.name,
    })
    setKbSelectorOpen(false)
    setKbSearch('')
  }

  // 清除知识库选择
  const handleClearKb = () => {
    onConfigChange({
      ...safeConfig,
      knowledgeBaseId: undefined,
      knowledgeBaseName: undefined,
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
  const renderVariableSelector = () => {
    const popoverId = 'query-input'

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
          {safeConfig.queryVariableRef ? (
            <>
              <span className="text-primary/80 font-mono text-[10px]">{'{x}'}</span>
              <span className="text-[11px] truncate">
                {safeConfig.queryVariableRefNodeLabel && <span className="text-muted-foreground">{safeConfig.queryVariableRefNodeLabel} / </span>}
                {extractVariableDisplayName(safeConfig.queryVariableRef)}
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
                          onConfigChange({
                            ...safeConfig,
                            querySource: 'variable',
                            queryVariableRef: `{{${variable.id}}}`,
                            queryVariableRefNodeLabel: variable.isSystem ? 'SYSTEM' : variable.groupLabel,
                            queryConstantValue: undefined,
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
      {/* 知识库选择 */}
      <div className="space-y-2">
        <div className="flex items-center gap-1">
          <Label className="text-xs font-medium">{t('configKnowledgeRetrieval.selectKnowledgeBase')}</Label>
          <span className="text-destructive">*</span>
        </div>

        {selectedKb ? (
          // 已选择知识库
          <div className="flex items-center gap-2 p-2.5 rounded-lg border bg-muted/30">
            <div className="shrink-0 w-8 h-8 rounded-lg bg-purple-500/10 flex items-center justify-center">
              <Database className="h-4 w-4 text-purple-500" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-1.5">
                <span className="text-sm font-medium truncate">{selectedKb.name}</span>
              </div>
              {selectedKb.description && (
                <p className="text-[10px] text-muted-foreground line-clamp-1">{selectedKb.description}</p>
              )}
            </div>
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6 shrink-0"
              onClick={handleClearKb}
            >
              <Trash2 className="h-3 w-3 text-muted-foreground" />
            </Button>
          </div>
        ) : (
          // 未选择知识库
          <Popover open={kbSelectorOpen} onOpenChange={setKbSelectorOpen}>
            <PopoverTrigger
              className="w-full h-9 flex items-center justify-start gap-2 px-3 text-xs text-muted-foreground bg-background border border-input rounded-md cursor-pointer hover:bg-accent hover:text-accent-foreground"
            >
              {isLoadingKbs ? (
                <>
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  {t('configCommon.loading')}
                </>
              ) : (
                <>
                  <Database className="h-3.5 w-3.5" />
                  {t('configKnowledgeRetrieval.selectKnowledgeBase')}
                </>
              )}
            </PopoverTrigger>
            <PopoverContent className="w-80 p-0" align="start">
              {/* 搜索 */}
              <div className="p-3 border-b">
                <div className="relative">
                  <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
                  <Input
                    placeholder={t('configKnowledgeRetrieval.searchKnowledgeBase')}
                    value={kbSearch}
                    onChange={(e) => setKbSearch(e.target.value)}
                    className="h-8 pl-8 text-xs"
                  />
                </div>
              </div>

              {/* 知识库列表 */}
              <ScrollArea className="h-64">
                <div className="p-2 space-y-1">
                  {filteredKbs.length === 0 ? (
                    <div className="flex flex-col items-center justify-center py-8 text-muted-foreground">
                      <Database className="h-8 w-8 mb-2" />
                      <p className="text-xs">{kbSearch ? t('configKnowledgeRetrieval.noMatchingKnowledgeBases') : t('configKnowledgeRetrieval.noKnowledgeBase')}</p>
                    </div>
                  ) : (
                    filteredKbs.map(kb => (
                      <button
                        key={kb.id}
                        className={cn(
                          'w-full flex items-center gap-2 p-2 rounded-md text-left transition-colors hover:bg-muted',
                          safeConfig.knowledgeBaseId === kb.id && 'bg-primary/10 border border-primary/30'
                        )}
                        onClick={() => handleSelectKb(kb)}
                      >
                        <div className="shrink-0 w-7 h-7 rounded-md bg-purple-500/10 flex items-center justify-center">
                          <Database className="h-3.5 w-3.5 text-purple-500" />
                        </div>
                        <div className="flex-1 min-w-0">
                          <span className="text-xs font-medium truncate block">{kb.name}</span>
                          {kb.description && (
                            <p className="text-[10px] text-muted-foreground line-clamp-1">{kb.description}</p>
                          )}
                        </div>
                        {safeConfig.knowledgeBaseId === kb.id && (
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

      {/* 查询输入 */}
      {selectedKb && (
        <Collapsible open={queryOpen} onOpenChange={setQueryOpen}>
          <CollapsibleTrigger className="flex items-center gap-1 text-xs font-medium w-full py-1">
            <ChevronDown className={cn(
              "h-3.5 w-3.5 transition-transform",
              !queryOpen && "-rotate-90"
            )} />
            <span>{t('configKnowledgeRetrieval.query')}</span>
            <span className="text-destructive">*</span>
          </CollapsibleTrigger>
          <CollapsibleContent className="pt-2 space-y-2">
            <p className="text-[10px] text-muted-foreground">{t('configKnowledgeRetrieval.queryDescription')}</p>

            {/* 值来源选择 */}
            <div className="flex gap-2">
              <Button
                variant={safeConfig.querySource === 'variable' ? 'default' : 'outline'}
                size="sm"
                className="h-6 text-[10px] flex-1"
                onClick={() => onConfigChange({ ...safeConfig, querySource: 'variable' })}
              >
                {t('configCommon.variable')}
              </Button>
              <Button
                variant={safeConfig.querySource === 'constant' ? 'default' : 'outline'}
                size="sm"
                className="h-6 text-[10px] flex-1"
                onClick={() => onConfigChange({
                  ...safeConfig,
                  querySource: 'constant',
                  queryVariableRef: undefined,
                  queryVariableRefNodeLabel: undefined,
                })}
              >
                {t('configCommon.constant')}
              </Button>
            </div>

            {/* 值输入 */}
            {safeConfig.querySource === 'variable' ? (
              renderVariableSelector()
            ) : (
              <Input
                value={safeConfig.queryConstantValue || ''}
                onChange={(e) => onConfigChange({ ...safeConfig, queryConstantValue: e.target.value })}
                placeholder={t('configKnowledgeRetrieval.queryPlaceholder')}
                className="h-8 text-xs"
              />
            )}
          </CollapsibleContent>
        </Collapsible>
      )}

      {/* 检索设置 */}
      {selectedKb && (
        <Collapsible open={settingsOpen} onOpenChange={setSettingsOpen}>
          <CollapsibleTrigger className="flex items-center gap-1 text-xs font-medium w-full py-1">
            <ChevronDown className={cn(
              "h-3.5 w-3.5 transition-transform",
              !settingsOpen && "-rotate-90"
            )} />
            <span>{t('configKnowledgeRetrieval.retrievalSettings')}</span>
          </CollapsibleTrigger>
          <CollapsibleContent className="pt-2 space-y-3">
            {/* 检索模式 */}
            <div className="space-y-2">
              <Label className="text-xs">{t('configKnowledgeRetrieval.searchMode')}</Label>
              <Select
                value={safeConfig.searchMode}
                onValueChange={(value: 'vector' | 'fulltext' | 'hybrid') =>
                  onConfigChange({ ...safeConfig, searchMode: value })
                }
              >
                <SelectTrigger className="h-8 text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="vector" className="text-xs">{t('configKnowledgeRetrieval.searchModeVector')}</SelectItem>
                  <SelectItem value="fulltext" className="text-xs">{t('configKnowledgeRetrieval.searchModeFulltext')}</SelectItem>
                  <SelectItem value="hybrid" className="text-xs">{t('configKnowledgeRetrieval.searchModeHybrid')}</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {/* Top K */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label className="text-xs">{t('configKnowledgeRetrieval.topK')}</Label>
                <span className="text-xs text-muted-foreground">{safeConfig.topK}</span>
              </div>
              <Slider
                value={[safeConfig.topK]}
                onValueChange={([value]) => onConfigChange({ ...safeConfig, topK: value })}
                min={1}
                max={20}
                step={1}
                className="w-full"
              />
            </div>

            {/* 相似度阈值 */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label className="text-xs">{t('configKnowledgeRetrieval.threshold')}</Label>
                <span className="text-xs text-muted-foreground">{safeConfig.threshold.toFixed(1)}</span>
              </div>
              <Slider
                value={[safeConfig.threshold]}
                onValueChange={([value]) => onConfigChange({ ...safeConfig, threshold: value })}
                min={0}
                max={1}
                step={0.1}
                className="w-full"
              />
            </div>
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
            placeholder="results"
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
              <span className="text-xs font-mono font-medium">{safeConfig.outputVariable || 'results'}</span>
              <span className="text-[10px] text-muted-foreground">Array</span>
            </div>
            <p className="text-[10px] text-muted-foreground mt-1">{t('configKnowledgeRetrieval.resultsDescription')}</p>
          </div>
        </CollapsibleContent>
      </Collapsible>
    </div>
  )
}
