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
} from 'lucide-react'
import {
  knowledgeBasesApi,
  type Agent,
  type KnowledgeBase,
  type ToolConfig,
  type VariableDefinition,
  type AgentKnowledgeBaseConfig,
  type RAGMode,
} from '@/lib/api'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
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
  const [ragMode, setRagMode] = React.useState<RAGMode>(agent.rag_mode || 'agentic')

  // Collapsed states
  const [variablesCollapsed, setVariablesCollapsed] = React.useState(true)
  const [kbCollapsed, setKbCollapsed] = React.useState(true)
  const [toolsCollapsed, setToolsCollapsed] = React.useState(true)
  const [visionCollapsed, setVisionCollapsed] = React.useState(true)

  // Data loading
  const [knowledgeBases, setKnowledgeBases] = React.useState<KnowledgeBase[]>([])
  const { tools: availableTools } = useTools()

  // Load knowledge bases
  React.useEffect(() => {
    const loadData = async () => {
      if (!currentTeam) return

      try {
        const kbs = await knowledgeBasesApi.getKnowledgeBases()
        setKnowledgeBases(
          kbs.items.filter((kb) => kb.team.id === currentTeam.id)
        )
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
      rag_mode: ragMode,
    })
  }, [systemPrompt, toolsConfig, variables, knowledgeBaseConfigs, enableVision, ragMode, onUpdate])

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
    </div>
  )
}
