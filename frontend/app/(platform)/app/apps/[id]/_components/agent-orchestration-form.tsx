'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { useTeam } from '@/contexts/team-context'
import {
  Sparkles,
  HelpCircle,
  ChevronRight,
  Database,
  Wrench,
  Eye,
  Variable,
  FileUp,
} from 'lucide-react'
import {
  knowledgeBasesApi,
  type Agent,
  type KnowledgeBase,
  type ToolConfig,
  type VariableDefinition,
  type AgentKnowledgeBaseConfig,
  type RAGMode,
  type FileUploadConfig,
} from '@/lib/api'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { VariableEditor, AddVariableButton, createNewVariable } from './variable-editor'
import { KnowledgeBaseSelector, AddKnowledgeBaseButton } from './knowledge-base-selector'
import { ToolSelector, AddToolButton, useTools } from './tool-selector'
import { PromptEditor } from './prompt-editor'

interface ConfigCardProps {
  icon: React.ElementType
  iconColor?: string
  title: string
  tooltip?: string
  action?: React.ReactNode
  badge?: React.ReactNode
  children: React.ReactNode
  className?: string
  collapsed?: boolean
  onToggle?: () => void
}

function ConfigCard({
  icon: Icon,
  iconColor = 'text-muted-foreground',
  title,
  tooltip,
  action,
  badge,
  children,
  className,
  collapsed,
  onToggle,
}: ConfigCardProps) {
  return (
    <div className={cn('rounded-xl bg-muted overflow-hidden', className)}>
      <div
        className={cn(
          'flex items-center gap-3 px-4 py-3',
          onToggle && 'cursor-pointer transition-colors'
        )}
        onClick={onToggle}
      >
        <div className={cn('shrink-0', iconColor)}>
          <Icon className="h-4 w-4" />
        </div>
        <div className="flex items-center gap-2 flex-1 min-w-0">
          <span className="font-medium text-sm">{title}</span>
          {tooltip && (
            <Tooltip>
              <TooltipTrigger onClick={(e) => e.stopPropagation()}>
                <HelpCircle className="h-3.5 w-3.5 text-muted-foreground" />
              </TooltipTrigger>
              <TooltipContent>
                <p className="max-w-xs text-xs">{tooltip}</p>
              </TooltipContent>
            </Tooltip>
          )}
          {badge}
        </div>
        <div className="flex items-center gap-2" onClick={(e) => e.stopPropagation()}>
          {action}
          {onToggle && (
            <ChevronRight
              className={cn(
                'h-4 w-4 text-muted-foreground transition-transform',
                !collapsed && 'rotate-90'
              )}
            />
          )}
        </div>
      </div>
      {!collapsed && <div className="px-4 pb-4">{children}</div>}
    </div>
  )
}

interface AgentOrchestrationFormProps {
  agent: Agent
  onUpdate: (data: Partial<Agent> & { knowledge_base_configs?: AgentKnowledgeBaseConfig[]; rag_mode?: RAGMode }) => void
}

export function AgentOrchestrationForm({
  agent,
  onUpdate,
}: AgentOrchestrationFormProps) {
  const t = useTranslations('agents.orchestration')
  const { currentTeam } = useTeam()

  // Form state
  const [systemPrompt, setSystemPrompt] = React.useState(
    agent.system_prompt || ''
  )
  const [variables, setVariables] = React.useState<VariableDefinition[]>(
    agent.variables || []
  )
  const [variableEditingIndex, setVariableEditingIndex] = React.useState<number | null>(null)
  const [isNewVariable, setIsNewVariable] = React.useState(false)
  const [knowledgeBaseConfigs, setKnowledgeBaseConfigs] = React.useState<AgentKnowledgeBaseConfig[]>(
    agent.knowledge_bases.map(akb => ({
      knowledge_base_id: akb.knowledge_base.id,
      retrieval_top_k: akb.retrieval_top_k,
      score_threshold: akb.score_threshold,
    }))
  )
  const [toolsConfig, setToolsConfig] = React.useState<ToolConfig[]>(
    agent.tools_config || []
  )
  const [enableVision, setEnableVision] = React.useState(agent.enable_vision || false)
  const [enableFileUpload, setEnableFileUpload] = React.useState(agent.enable_file_upload || false)
  const [fileUploadConfig, setFileUploadConfig] = React.useState<FileUploadConfig>(
    agent.file_upload_config || {
      parser: { type: 'builtin', name: 'markitdown' },  // default parser
      max_file_size: 10 * 1024 * 1024,
      max_files: 5,
      max_content_length: 100000,
      truncate_strategy: 'end',
      allowed_extensions: ['.pdf', '.docx', '.doc', '.pptx', '.ppt', '.xlsx', '.xls', '.txt', '.md', '.csv', '.json', '.html'],
    }
  )
  const [ragMode, setRagMode] = React.useState<RAGMode>(agent.rag_mode || 'agentic')

  // Collapsed states
  const [variablesCollapsed, setVariablesCollapsed] = React.useState(true)
  const [kbCollapsed, setKbCollapsed] = React.useState(true)
  const [toolsCollapsed, setToolsCollapsed] = React.useState(true)
  const [visionCollapsed, setVisionCollapsed] = React.useState(true)
  const [fileUploadCollapsed, setFileUploadCollapsed] = React.useState(true)

  // Data loading
  const [knowledgeBases, setKnowledgeBases] = React.useState<KnowledgeBase[]>([])
  const [fileParsers, setFileParsers] = React.useState<import('@/lib/api').Tool[]>([])
  const { tools: availableTools } = useTools()

  // Load knowledge bases and file parsers
  React.useEffect(() => {
    const loadData = async () => {
      if (!currentTeam) return

      try {
        const [kbs, parsers] = await Promise.all([
          knowledgeBasesApi.getKnowledgeBases(),
          import('@/lib/api').then(m => m.toolsApi.listFileParsers(currentTeam.id)),
        ])
        setKnowledgeBases(
          kbs.items.filter((kb) => kb.team.id === currentTeam.id)
        )
        setFileParsers(parsers)
      } catch {
        // Ignore errors
      }
    }
    loadData()
  }, [currentTeam])

  // Update parent when values change
  React.useEffect(() => {
    onUpdate({
      system_prompt: systemPrompt || null,
      tools_config: toolsConfig,
      variables: variables,
      knowledge_base_configs: knowledgeBaseConfigs,
      enable_vision: enableVision,
      enable_file_upload: enableFileUpload,
      file_upload_config: enableFileUpload ? fileUploadConfig : null,
      rag_mode: ragMode,
    })
  }, [systemPrompt, toolsConfig, variables, knowledgeBaseConfigs, enableVision, enableFileUpload, fileUploadConfig, ragMode, onUpdate])

  // Character count for prompt
  const promptLength = systemPrompt.length

  return (
    <div className="space-y-3">
      {/* Prompt Section - Always expanded, highlighted */}
      <div className="rounded-xl bg-linear-to-br from-primary/5 to-primary/10 border border-primary/20 overflow-hidden">
        <div className="flex items-center justify-between px-4 py-3">
          <div className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-primary" />
            <span className="font-medium text-sm">{t('prompt.title')}</span>
            <Tooltip>
              <TooltipTrigger>
                <HelpCircle className="h-3.5 w-3.5 text-muted-foreground" />
              </TooltipTrigger>
              <TooltipContent>
                <p className="max-w-xs text-xs">{t('prompt.tooltip')}</p>
              </TooltipContent>
            </Tooltip>
          </div>
          <Button variant="ghost" size="sm" className="h-7 text-xs gap-1.5 cursor-pointer bg-violet-500/10 text-violet-600 hover:bg-violet-500/20 hover:text-violet-700 dark:text-violet-400 dark:hover:text-violet-300">
            <Sparkles className="h-3 w-3" />
            {t('prompt.aiGenerate')}
          </Button>
        </div>
        <div className="px-4 pb-4">
          <PromptEditor
            value={systemPrompt}
            onChange={setSystemPrompt}
            variables={variables}
            onAddVariable={(name, type) => {
              const newVar = createNewVariable(type, variables)
              newVar.name = name
              newVar.label = name
              setVariables([...variables, newVar])
            }}
            placeholder={t('prompt.placeholder')}
            enableFileUpload={enableFileUpload}
          />
          <div className="flex items-center justify-between mt-3 pt-3 border-t border-primary/10">
            <span className="text-xs text-muted-foreground">
              {t('prompt.variableHint')}
            </span>
            <span className="text-xs text-muted-foreground tabular-nums">
              {t('prompt.charCount', { count: promptLength })}
            </span>
          </div>
        </div>
      </div>

      {/* Variables Section */}
      <ConfigCard
        icon={Variable}
        iconColor="text-blue-500"
        title={t('variables.title')}
        tooltip={t('variables.tooltip')}
        badge={
          variables.length > 0 && (
            <span className="text-xs text-muted-foreground">
              {t('variables.requiredCount', { required: variables.filter(v => v.required).length, total: variables.length })}
            </span>
          )
        }
        action={
          <AddVariableButton
            onAdd={(type) => {
              const newVar = createNewVariable(type, variables)
              const newVariables = [...variables, newVar]
              setVariables(newVariables)
              setVariableEditingIndex(newVariables.length - 1)
              setIsNewVariable(true)
              setVariablesCollapsed(false)
            }}
          />
        }
        collapsed={variablesCollapsed}
        onToggle={() => setVariablesCollapsed(!variablesCollapsed)}
      >
        <VariableEditor
          variables={variables}
          onChange={setVariables}
          editingIndex={variableEditingIndex}
          onEditingIndexChange={(index) => {
            setVariableEditingIndex(index)
            if (index === null) setIsNewVariable(false)
          }}
          isNewVariable={isNewVariable}
        />
      </ConfigCard>

      {/* Knowledge Base Section */}
      <ConfigCard
        icon={Database}
        iconColor="text-emerald-500"
        title={t('knowledgeBase.title')}
        tooltip={t('knowledgeBase.tooltip')}
        badge={
          knowledgeBaseConfigs.length > 0 && (
            <span className="text-xs text-muted-foreground">
              {t('knowledgeBase.linkedCount', { count: knowledgeBaseConfigs.length })}
            </span>
          )
        }
        action={
          <div className="flex items-center gap-2">
            {/* RAG Mode Selection */}
            {knowledgeBaseConfigs.length > 0 && (
              <Select value={ragMode} onValueChange={(value) => setRagMode(value as RAGMode)}>
                <SelectTrigger className="h-7 text-xs w-[120px] gap-1 px-2 bg-background">
                  <SelectValue>
                    {ragMode === 'agentic' && t('knowledgeBase.ragMode.agenticShort')}
                    {ragMode === 'auto' && t('knowledgeBase.ragMode.autoShort')}
                    {ragMode === 'off' && t('knowledgeBase.ragMode.offShort')}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="agentic">{t('knowledgeBase.ragMode.agentic')}</SelectItem>
                  <SelectItem value="auto">{t('knowledgeBase.ragMode.auto')}</SelectItem>
                  <SelectItem value="off">{t('knowledgeBase.ragMode.off')}</SelectItem>
                </SelectContent>
              </Select>
            )}
            <AddKnowledgeBaseButton
              knowledgeBases={knowledgeBases}
              selectedIds={knowledgeBaseConfigs.map(c => c.knowledge_base_id)}
              onAdd={(kb) => {
                const newConfig: AgentKnowledgeBaseConfig = {
                  knowledge_base_id: kb.id,
                  retrieval_top_k: 3,
                  score_threshold: 0.5,
                }
                setKnowledgeBaseConfigs([...knowledgeBaseConfigs, newConfig])
                setKbCollapsed(false)
              }}
            />
          </div>
        }
        collapsed={kbCollapsed}
        onToggle={() => setKbCollapsed(!kbCollapsed)}
      >
        <KnowledgeBaseSelector
          configs={knowledgeBaseConfigs}
          availableKnowledgeBases={knowledgeBases}
          onChange={setKnowledgeBaseConfigs}
        />
      </ConfigCard>

      {/* Tools Section */}
      <ConfigCard
        icon={Wrench}
        iconColor="text-orange-500"
        title={t('tools.title')}
        tooltip={t('tools.tooltip')}
        badge={
          toolsConfig.length > 0 && (
            <span className="text-xs text-muted-foreground">
              {t('tools.enabledCount', { count: toolsConfig.length })}
            </span>
          )
        }
        action={
          <AddToolButton
            availableTools={availableTools}
            selectedToolNames={toolsConfig
              .filter(c => c.type === 'builtin')
              .map(c => c.name || '')
              .filter(Boolean)}
            selectedToolIds={toolsConfig
              .filter(c => c.type === 'custom')
              .map(c => c.tool_id)
              .filter(Boolean) as string[]}
            selectedMcpServerIds={toolsConfig
              .filter(c => c.type === 'mcp')
              .map(c => c.server_id)
              .filter(Boolean) as string[]}
            onAdd={(tool) => {
              let newConfig: ToolConfig
              if (tool.type === 'builtin') {
                newConfig = { type: 'builtin', name: tool.name }
              } else if (tool.type === 'mcp') {
                newConfig = { type: 'mcp', server_id: tool.id }
              } else {
                newConfig = { type: 'custom', tool_id: tool.id, name: tool.name }
              }
              setToolsConfig([...toolsConfig, newConfig])
              setToolsCollapsed(false)
            }}
            onRemove={(tool) => {
              setToolsConfig(
                toolsConfig.filter((c) => {
                  if (c.type === 'builtin' && tool.type === 'builtin') {
                    return c.name !== tool.name
                  }
                  if (c.type === 'mcp' && tool.type === 'mcp') {
                    return c.server_id !== tool.id
                  }
                  if (c.type === 'custom' && tool.type === 'custom') {
                    return c.tool_id !== tool.id
                  }
                  return true
                })
              )
            }}
          />
        }
        collapsed={toolsCollapsed}
        onToggle={() => setToolsCollapsed(!toolsCollapsed)}
      >
        <ToolSelector
          toolsConfig={toolsConfig}
          availableTools={availableTools}
          onChange={setToolsConfig}
        />
      </ConfigCard>

      {/* Vision Section */}
      <ConfigCard
        icon={Eye}
        iconColor="text-purple-500"
        title={t('vision.title')}
        tooltip={t('vision.tooltip')}
        action={
          <Switch
            checked={enableVision}
            onCheckedChange={setEnableVision}
          />
        }
        collapsed={visionCollapsed}
        onToggle={() => setVisionCollapsed(!visionCollapsed)}
      >
        <p className="text-xs text-muted-foreground py-2">
          {t('vision.description')}
        </p>
      </ConfigCard>

      {/* File Upload Section */}
      <ConfigCard
        icon={FileUp}
        iconColor="text-cyan-500"
        title={t('fileUpload.title')}
        tooltip={t('fileUpload.tooltip')}
        action={
          <Switch
            checked={enableFileUpload}
            onCheckedChange={setEnableFileUpload}
          />
        }
        collapsed={fileUploadCollapsed}
        onToggle={() => setFileUploadCollapsed(!fileUploadCollapsed)}
      >
        <div className="space-y-4 py-2">
          <p className="text-xs text-muted-foreground">
            {t('fileUpload.description')}
          </p>
          
          {enableFileUpload && (
            <div className="space-y-4 pt-2 border-t">
              {/* Parser Selection */}
              <div className="space-y-2">
                <Label className="text-xs">{t('fileUpload.parser')}</Label>
                <Select
                  value={
                    fileUploadConfig.parser
                      ? fileUploadConfig.parser.type === 'builtin'
                        ? `builtin:${fileUploadConfig.parser.name}`
                        : `custom:${fileUploadConfig.parser.tool_id}`
                      : ''
                  }
                  onValueChange={(value) => {
                    if (!value) {
                      setFileUploadConfig({
                        ...fileUploadConfig,
                        parser: null,
                      })
                    } else {
                      const [type, id] = value.split(':')
                      if (type === 'builtin') {
                        setFileUploadConfig({
                          ...fileUploadConfig,
                          parser: { type: 'builtin', name: id },
                        })
                      } else {
                        setFileUploadConfig({
                          ...fileUploadConfig,
                          parser: { type: 'custom', tool_id: id },
                        })
                      }
                    }
                  }}
                >
                  <SelectTrigger className="w-full h-8 text-sm bg-background">
                    <SelectValue>
                      {(value: string) => {
                        if (!value) {
                          return <span className="text-muted-foreground">{t('fileUpload.selectParser')}</span>
                        }
                        const selectedParser = fileParsers.find(p => 
                          (p.type === 'builtin' ? `builtin:${p.name}` : `custom:${p.id}`) === value
                        )
                        if (!selectedParser) {
                          return <span className="text-muted-foreground">{t('fileUpload.selectParser')}</span>
                        }
                        return (
                          <div className="flex items-center gap-2">
                            <span>{selectedParser.icon}</span>
                            <span>{selectedParser.display_name}</span>
                          </div>
                        )
                      }}
                    </SelectValue>
                  </SelectTrigger>
                  <SelectContent>
                    {fileParsers.map((parser) => (
                      <SelectItem
                        key={parser.type === 'builtin' ? `builtin:${parser.name}` : `custom:${parser.id}`}
                        value={parser.type === 'builtin' ? `builtin:${parser.name}` : `custom:${parser.id}`}
                      >
                        <div className="flex items-center gap-2">
                          <span>{parser.icon}</span>
                          <span>{parser.display_name}</span>
                          {parser.type === 'custom' && (
                            <span className="text-xs text-muted-foreground">(自定义)</span>
                          )}
                        </div>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-xs text-muted-foreground">
                  {t('fileUpload.parserHint')}
                </p>
              </div>

              {/* Max Content Length */}
              <div className="space-y-2">
                <Label className="text-xs">{t('fileUpload.maxContentLength')}</Label>
                <div className="flex items-center gap-2">
                  <Input
                    type="number"
                    value={fileUploadConfig.max_content_length}
                    onChange={(e) => {
                      const val = parseInt(e.target.value) || 100000
                      setFileUploadConfig({
                        ...fileUploadConfig,
                        max_content_length: Math.min(Math.max(val, 1000), 500000),
                      })
                    }}
                    className="w-28 h-8 text-sm bg-background"
                    min={1000}
                    max={500000}
                    step={10000}
                  />
                  <span className="text-xs text-muted-foreground">{t('fileUpload.characters')}</span>
                </div>
                <p className="text-xs text-muted-foreground">
                  {t('fileUpload.maxContentLengthHint')}
                </p>
              </div>

              {/* Truncate Strategy */}
              <div className="space-y-2">
                <Label className="text-xs">{t('fileUpload.truncateStrategy')}</Label>
                <Select
                  value={fileUploadConfig.truncate_strategy}
                  onValueChange={(value) => {
                    if (value && (value === 'end' || value === 'start' || value === 'middle')) {
                      setFileUploadConfig({
                        ...fileUploadConfig,
                        truncate_strategy: value,
                      })
                    }
                  }}
                >
                  <SelectTrigger className="w-48 h-8 text-sm bg-background">
                    <SelectValue>
                      {(value: string) => {
                        if (value === 'end') return t('fileUpload.truncateEnd')
                        if (value === 'start') return t('fileUpload.truncateStart')
                        if (value === 'middle') return t('fileUpload.truncateMiddle')
                        return t('fileUpload.truncateEnd')
                      }}
                    </SelectValue>
                  </SelectTrigger>
                  <SelectContent className="w-48">
                    <SelectItem value="end">{t('fileUpload.truncateEnd')}</SelectItem>
                    <SelectItem value="start">{t('fileUpload.truncateStart')}</SelectItem>
                    <SelectItem value="middle">{t('fileUpload.truncateMiddle')}</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {/* Variable Hint */}
              <div className="p-3 rounded-lg bg-cyan-500/10 border border-cyan-500/20">
                <p className="text-xs text-cyan-700 dark:text-cyan-300">
                  {t('fileUpload.variableHint')}
                </p>
                <code className="mt-1 block text-xs font-mono text-cyan-600 dark:text-cyan-400">
                  {'{{fileContent}}'}
                </code>
              </div>
            </div>
          )}
        </div>
      </ConfigCard>
    </div>
  )
}
