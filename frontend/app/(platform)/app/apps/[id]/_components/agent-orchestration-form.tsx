'use client'

import * as React from 'react'
import { useTranslations, useLocale } from 'next-intl'
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
  MessageSquare,
  Brain,
  ImageIcon,
  Clapperboard,
} from 'lucide-react'
import {
  teamModelsApi,
  knowledgeBasesApi,
  type Agent,
  type KnowledgeBase,
  type TeamModel,
  type ToolConfig,
  type VariableDefinition,
  type AgentKnowledgeBaseConfig,
  type RAGMode,
  type FileUploadConfig,
  type PromptGenerateContext,
  type ImageGenerationConfig,
  type VideoGenerationConfig,
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
import { PromptGenerateDialog } from '@/components/ai-elements/prompt-generate-dialog'

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

const DEFAULT_IMAGE_GENERATION_CONFIG: ImageGenerationConfig = {
  default_model_ref: null,
  default_width: 1024,
  default_height: 1024,
  max_images: 4,
  allow_reference_images: true,
  allowed_providers: [],
  require_confirmation: false,
}

const DEFAULT_VIDEO_GENERATION_CONFIG: VideoGenerationConfig = {
  default_model_ref: null,
  default_duration: 5,
  max_duration: 10,
  default_aspect_ratio: '16:9',
  poll_interval_ms: 3000,
  poll_timeout_s: 120,
  allowed_providers: [],
  require_confirmation: false,
}

const DEFAULT_MEDIA_MODEL_VALUE = '__default__'

function getMediaModelOptionLabel(teamModel: TeamModel) {
  return teamModel.model.name
}

function getMediaModelSelectLabel(
  modelRef: string | null,
  teamModels: TeamModel[],
  defaultLabel: string
) {
  if (!modelRef) {
    return defaultLabel
  }

  const matchedModel = teamModels.find((teamModel) => teamModel.model.id === modelRef)
  return matchedModel ? getMediaModelOptionLabel(matchedModel) : modelRef
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
  const locale = useLocale()
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
      search_mode: akb.search_mode || 'hybrid',
    }))
  )
  const [toolsConfig, setToolsConfig] = React.useState<ToolConfig[]>(
    agent.tools_config || []
  )
  const [enableVision, setEnableVision] = React.useState(agent.enable_vision || false)
  const [enableFileUpload, setEnableFileUpload] = React.useState(agent.enable_file_upload || false)
  const [enableUserInputRequest, setEnableUserInputRequest] = React.useState(agent.enable_user_input_request || false)
  const [enableMemory, setEnableMemory] = React.useState(agent.enable_memory || false)
  const [memoryConfig, setMemoryConfig] = React.useState(
    agent.memory_config || {
      max_memories_per_retrieval: 10,
      auto_extract: true,
      importance_threshold: 'medium' as const,
    }
  )
  const [enableImageGeneration, setEnableImageGeneration] = React.useState(
    agent.enable_image_generation || false
  )
  const [imageGenerationConfig, setImageGenerationConfig] = React.useState<ImageGenerationConfig>(
    agent.image_generation_config || DEFAULT_IMAGE_GENERATION_CONFIG
  )
  const [enableVideoGeneration, setEnableVideoGeneration] = React.useState(
    agent.enable_video_generation || false
  )
  const [videoGenerationConfig, setVideoGenerationConfig] = React.useState<VideoGenerationConfig>(
    agent.video_generation_config || DEFAULT_VIDEO_GENERATION_CONFIG
  )
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

  // Sync state with agent prop when it changes
  React.useEffect(() => {
    setSystemPrompt(agent.system_prompt || '')
    setVariables(agent.variables || [])
    setKnowledgeBaseConfigs(
      agent.knowledge_bases.map(akb => ({
        knowledge_base_id: akb.knowledge_base.id,
        retrieval_top_k: akb.retrieval_top_k,
        score_threshold: akb.score_threshold,
        search_mode: akb.search_mode || 'hybrid',
      }))
    )
    setToolsConfig(agent.tools_config || [])
    setEnableVision(agent.enable_vision || false)
    setEnableFileUpload(agent.enable_file_upload || false)
    setEnableUserInputRequest(agent.enable_user_input_request || false)
    setEnableMemory(agent.enable_memory || false)
    setMemoryConfig(
      agent.memory_config || {
        max_memories_per_retrieval: 10,
        auto_extract: true,
        importance_threshold: 'medium' as const,
      }
    )
    setEnableImageGeneration(agent.enable_image_generation || false)
    setImageGenerationConfig(
      agent.image_generation_config || DEFAULT_IMAGE_GENERATION_CONFIG
    )
    setEnableVideoGeneration(agent.enable_video_generation || false)
    setVideoGenerationConfig(
      agent.video_generation_config || DEFAULT_VIDEO_GENERATION_CONFIG
    )
    setFileUploadConfig(
      agent.file_upload_config || {
        parser: { type: 'builtin', name: 'markitdown' },
        max_file_size: 10 * 1024 * 1024,
        max_files: 5,
        max_content_length: 100000,
        truncate_strategy: 'end',
        allowed_extensions: ['.pdf', '.docx', '.doc', '.pptx', '.ppt', '.xlsx', '.xls', '.txt', '.md', '.csv', '.json', '.html'],
      }
    )
    setRagMode(agent.rag_mode || 'agentic')
  }, [agent])

  // Collapsed states
  const [variablesCollapsed, setVariablesCollapsed] = React.useState(true)
  const [kbCollapsed, setKbCollapsed] = React.useState(true)
  const [toolsCollapsed, setToolsCollapsed] = React.useState(true)
  const [visionCollapsed, setVisionCollapsed] = React.useState(true)
  const [fileUploadCollapsed, setFileUploadCollapsed] = React.useState(true)
  const [userInputRequestCollapsed, setUserInputRequestCollapsed] = React.useState(true)
  const [memoryCollapsed, setMemoryCollapsed] = React.useState(true)
  const [imageGenerationCollapsed, setImageGenerationCollapsed] = React.useState(true)
  const [videoGenerationCollapsed, setVideoGenerationCollapsed] = React.useState(true)

  // Prompt generate dialog state
  const [showPromptGenerator, setShowPromptGenerator] = React.useState(false)

  // Data loading
  const [knowledgeBases, setKnowledgeBases] = React.useState<KnowledgeBase[]>([])
  const [fileParsers, setFileParsers] = React.useState<import('@/lib/api').Tool[]>([])
  const [imageModels, setImageModels] = React.useState<TeamModel[]>([])
  const [videoModels, setVideoModels] = React.useState<TeamModel[]>([])
  const { tools: availableTools } = useTools()
  const imageDefaultModelLabel = getMediaModelSelectLabel(
    imageGenerationConfig.default_model_ref ?? null,
    imageModels,
    t('imageGeneration.defaultModel')
  )
  const videoDefaultModelLabel = getMediaModelSelectLabel(
    videoGenerationConfig.default_model_ref ?? null,
    videoModels,
    t('videoGeneration.defaultModel')
  )

  // Load knowledge bases and file parsers
  React.useEffect(() => {
    const loadData = async () => {
      if (!currentTeam) return

      try {
        const [kbs, parsers, imageTeamModels, videoTeamModels] = await Promise.all([
          knowledgeBasesApi.getKnowledgeBases(),
          import('@/lib/api').then(m => m.toolsApi.listFileParsers(currentTeam.id)),
          teamModelsApi.getTeamModels(currentTeam.id, 'text_to_image'),
          teamModelsApi.getTeamModels(currentTeam.id, 'text_to_video'),
        ])
        setKnowledgeBases(
          kbs.items.filter((kb) => kb.team.id === currentTeam.id)
        )
        setFileParsers(parsers)
        setImageModels(imageTeamModels)
        setVideoModels(videoTeamModels)
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
      enable_user_input_request: enableUserInputRequest,
      enable_memory: enableMemory,
      memory_config: enableMemory ? memoryConfig : null,
      enable_image_generation: enableImageGeneration,
      image_generation_config: enableImageGeneration ? imageGenerationConfig : null,
      enable_video_generation: enableVideoGeneration,
      video_generation_config: enableVideoGeneration ? videoGenerationConfig : null,
      file_upload_config: enableFileUpload ? fileUploadConfig : null,
      rag_mode: ragMode,
    })
  }, [systemPrompt, toolsConfig, variables, knowledgeBaseConfigs, enableVision, enableFileUpload, enableUserInputRequest, enableMemory, memoryConfig, enableImageGeneration, imageGenerationConfig, enableVideoGeneration, videoGenerationConfig, fileUploadConfig, ragMode, onUpdate])

  // Character count for prompt
  const promptLength = systemPrompt.length

  // Build context for prompt generator
  const promptGenerateContext: PromptGenerateContext = React.useMemo(() => ({
    agent_name: agent.name,
    agent_description: agent.description,
    tools: toolsConfig.map((tc) => {
      const tool = availableTools.find(
        (t) =>
          (tc.type === 'builtin' && t.name === tc.name) ||
          (tc.type === 'custom' && t.id === tc.tool_id) ||
          (tc.type === 'mcp' && t.id === tc.server_id) ||
          (tc.type === 'skill' && t.id === tc.skill_id)
      )
      return {
        name: tc.name || tool?.name,
        display_name: tool?.display_name ?? tc.name ?? undefined,
      }
    }).filter((t) => t.name),
    knowledge_bases: knowledgeBases
      .filter((kb) =>
        knowledgeBaseConfigs.some((c) => c.knowledge_base_id === kb.id)
      )
      .map((kb) => ({
        name: kb.name,
        description: kb.description ?? undefined,
      })),
    variables: variables.map((v) => ({
      name: v.name,
      label: v.label ?? undefined,
    })),
  }), [agent.name, agent.description, toolsConfig, availableTools, knowledgeBases, knowledgeBaseConfigs, variables])

  return (
    <div className="space-y-3">
      {/* Prompt Generate Dialog */}
      <PromptGenerateDialog
        open={showPromptGenerator}
        onOpenChange={setShowPromptGenerator}
        context={promptGenerateContext}
        onApply={(generatedPrompt) => {
          setSystemPrompt(generatedPrompt)
        }}
        language={locale as 'en' | 'zh'}
      />

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
          <Button
            variant="ghost"
            size="sm"
            className="h-7 text-xs gap-1.5 cursor-pointer bg-violet-500/10 text-violet-600 hover:bg-violet-500/20 hover:text-violet-700 dark:text-violet-400 dark:hover:text-violet-300"
            onClick={() => setShowPromptGenerator(true)}
          >
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
              const newVar = createNewVariable(type, variables, [
                t('variables.defaultOptions.option1'),
                t('variables.defaultOptions.option2'),
              ])
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
              const newVar = createNewVariable(type, variables, [
                t('variables.defaultOptions.option1'),
                t('variables.defaultOptions.option2'),
              ])
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
                <SelectTrigger size="xs" className="text-xs w-[120px] gap-1 px-2 bg-background">
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
                  score_threshold: 0.3,
                  search_mode: 'hybrid',
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
            selectedSkillIds={toolsConfig
              .filter(c => c.type === 'skill')
              .map(c => c.skill_id)
              .filter(Boolean) as string[]}
            onAdd={(tool) => {
              let newConfig: ToolConfig
              if (tool.type === 'builtin') {
                newConfig = { type: 'builtin', name: tool.name }
              } else if (tool.type === 'mcp') {
                newConfig = { type: 'mcp', server_id: tool.id }
              } else if (tool.type === 'skill') {
                newConfig = { type: 'skill', skill_id: tool.id, name: tool.name }
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
                  if (c.type === 'skill' && tool.type === 'skill') {
                    return c.skill_id !== tool.id
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
                  <SelectTrigger size="sm" className="w-full text-sm bg-background">
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
                            <span className="text-xs text-muted-foreground">{t('fileUpload.customParser')}</span>
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
                  <SelectTrigger size="sm" className="w-48 text-sm bg-background">
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

              <div className="p-3 rounded-lg bg-cyan-500/10 border border-cyan-500/20">
                <p className="text-xs text-cyan-700 dark:text-cyan-300">
                  {t('fileUpload.contextHint')}
                </p>
              </div>
            </div>
          )}
        </div>
      </ConfigCard>

      {/* User Input Request Section */}
      <ConfigCard
        icon={MessageSquare}
        iconColor="text-purple-500"
        title={t('userInputRequest.title')}
        tooltip={t('userInputRequest.tooltip')}
        action={
          <Switch
            checked={enableUserInputRequest}
            onCheckedChange={setEnableUserInputRequest}
          />
        }
        collapsed={userInputRequestCollapsed}
        onToggle={() => setUserInputRequestCollapsed(!userInputRequestCollapsed)}
      >
        <div className="space-y-4 py-2">
          <p className="text-xs text-muted-foreground">
            {t('userInputRequest.description')}
          </p>
        </div>
      </ConfigCard>

      {/* Memory Section */}
      <ConfigCard
        icon={Brain}
        iconColor="text-pink-500"
        title={t('memory.title')}
        tooltip={t('memory.tooltip')}
        action={
          <Switch
            checked={enableMemory}
            onCheckedChange={setEnableMemory}
          />
        }
        collapsed={memoryCollapsed}
        onToggle={() => setMemoryCollapsed(!memoryCollapsed)}
      >
        <div className="space-y-4 py-2">
          <p className="text-xs text-muted-foreground">
            {t('memory.description')}
          </p>

          {enableMemory && (
            <div className="space-y-4 pt-2 border-t">
              {/* Max Memories Per Retrieval */}
              <div className="space-y-2">
                <Label className="text-xs">{t('memory.maxMemoriesPerRetrieval')}</Label>
                <div className="flex items-center gap-2">
                  <Input
                    type="number"
                    value={memoryConfig.max_memories_per_retrieval}
                    onChange={(e) => {
                      const val = parseInt(e.target.value) || 10
                      setMemoryConfig({
                        ...memoryConfig,
                        max_memories_per_retrieval: Math.min(Math.max(val, 1), 50),
                      })
                    }}
                    className="w-28 h-8 text-sm bg-background"
                    min={1}
                    max={50}
                    step={1}
                  />
                  <span className="text-xs text-muted-foreground">{t('memory.memories')}</span>
                </div>
                <p className="text-xs text-muted-foreground">
                  {t('memory.maxMemoriesPerRetrievalHint')}
                </p>
              </div>

              {/* Auto Extract */}
              <div className="flex items-center justify-between p-3 rounded-lg bg-background border">
                <div className="space-y-0.5">
                  <Label className="text-xs font-medium">{t('memory.autoExtract')}</Label>
                  <p className="text-xs text-muted-foreground">
                    {t('memory.autoExtractHint')}
                  </p>
                </div>
                <Switch
                  checked={memoryConfig.auto_extract}
                  onCheckedChange={(checked) => {
                    setMemoryConfig({
                      ...memoryConfig,
                      auto_extract: checked,
                    })
                  }}
                />
              </div>
            </div>
          )}
        </div>
      </ConfigCard>

      {/* Image Generation Section */}
      <ConfigCard
        icon={ImageIcon}
        iconColor="text-amber-500"
        title={t('imageGeneration.title')}
        tooltip={t('imageGeneration.tooltip')}
        action={
          <Switch
            checked={enableImageGeneration}
            onCheckedChange={setEnableImageGeneration}
          />
        }
        collapsed={imageGenerationCollapsed}
        onToggle={() => setImageGenerationCollapsed(!imageGenerationCollapsed)}
      >
        <div className="space-y-4 py-2">
          <p className="text-xs text-muted-foreground">
            {t('imageGeneration.description')}
          </p>

          {enableImageGeneration && (
            <div className="space-y-4 pt-2 border-t">
              <div className="space-y-2">
                <Label className="text-xs">{t('imageGeneration.defaultModel')}</Label>
                <Select
                  value={imageGenerationConfig.default_model_ref || DEFAULT_MEDIA_MODEL_VALUE}
                  onValueChange={(value) => {
                    setImageGenerationConfig({
                      ...imageGenerationConfig,
                      default_model_ref: value === DEFAULT_MEDIA_MODEL_VALUE ? null : value,
                    })
                  }}
                >
                  <SelectTrigger size="sm" className="w-56 text-sm bg-background">
                    <SelectValue>{imageDefaultModelLabel}</SelectValue>
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={DEFAULT_MEDIA_MODEL_VALUE}>
                      {t('imageGeneration.defaultModel')}
                    </SelectItem>
                    {imageModels.map((teamModel) => (
                      <SelectItem key={teamModel.id} value={teamModel.model.id}>
                        {getMediaModelOptionLabel(teamModel)}
                      </SelectItem>
                    ))}
                    {imageGenerationConfig.default_model_ref &&
                    !imageModels.some((teamModel) => teamModel.model.id === imageGenerationConfig.default_model_ref) ? (
                      <SelectItem value={imageGenerationConfig.default_model_ref}>
                        {imageGenerationConfig.default_model_ref}
                      </SelectItem>
                    ) : null}
                  </SelectContent>
                </Select>
              </div>

              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label className="text-xs">{t('imageGeneration.defaultWidth')}</Label>
                  <Input
                    type="number"
                    value={imageGenerationConfig.default_width}
                    onChange={(e) => {
                      const value = parseInt(e.target.value) || 1024
                      setImageGenerationConfig({
                        ...imageGenerationConfig,
                        default_width: Math.min(Math.max(value, 256), 4096),
                      })
                    }}
                    className="h-8 text-sm bg-background"
                    min={256}
                    max={4096}
                  />
                </div>
                <div className="space-y-2">
                  <Label className="text-xs">{t('imageGeneration.defaultHeight')}</Label>
                  <Input
                    type="number"
                    value={imageGenerationConfig.default_height}
                    onChange={(e) => {
                      const value = parseInt(e.target.value) || 1024
                      setImageGenerationConfig({
                        ...imageGenerationConfig,
                        default_height: Math.min(Math.max(value, 256), 4096),
                      })
                    }}
                    className="h-8 text-sm bg-background"
                    min={256}
                    max={4096}
                  />
                </div>
              </div>

              <div className="space-y-2">
                <Label className="text-xs">{t('imageGeneration.maxImages')}</Label>
                <Input
                  type="number"
                  value={imageGenerationConfig.max_images}
                  onChange={(e) => {
                    const value = parseInt(e.target.value) || 4
                    setImageGenerationConfig({
                      ...imageGenerationConfig,
                      max_images: Math.min(Math.max(value, 1), 10),
                    })
                  }}
                  className="h-8 w-28 text-sm bg-background"
                  min={1}
                  max={10}
                />
              </div>

              <div className="flex items-center justify-between rounded-lg border bg-background p-3">
                <div className="space-y-0.5">
                  <Label className="text-xs font-medium">{t('imageGeneration.allowReferenceImages')}</Label>
                  <p className="text-xs text-muted-foreground">
                    {t('imageGeneration.allowReferenceImagesHint')}
                  </p>
                </div>
                <Switch
                  checked={imageGenerationConfig.allow_reference_images}
                  onCheckedChange={(checked) => {
                    setImageGenerationConfig({
                      ...imageGenerationConfig,
                      allow_reference_images: checked,
                    })
                  }}
                />
              </div>
            </div>
          )}
        </div>
      </ConfigCard>

      {/* Video Generation Section */}
      <ConfigCard
        icon={Clapperboard}
        iconColor="text-rose-500"
        title={t('videoGeneration.title')}
        tooltip={t('videoGeneration.tooltip')}
        action={
          <Switch
            checked={enableVideoGeneration}
            onCheckedChange={setEnableVideoGeneration}
          />
        }
        collapsed={videoGenerationCollapsed}
        onToggle={() => setVideoGenerationCollapsed(!videoGenerationCollapsed)}
      >
        <div className="space-y-4 py-2">
          <p className="text-xs text-muted-foreground">
            {t('videoGeneration.description')}
          </p>

          {enableVideoGeneration && (
            <div className="space-y-4 pt-2 border-t">
              <div className="space-y-2">
                <Label className="text-xs">{t('videoGeneration.defaultModel')}</Label>
                <Select
                  value={videoGenerationConfig.default_model_ref || DEFAULT_MEDIA_MODEL_VALUE}
                  onValueChange={(value) => {
                    setVideoGenerationConfig({
                      ...videoGenerationConfig,
                      default_model_ref: value === DEFAULT_MEDIA_MODEL_VALUE ? null : value,
                    })
                  }}
                >
                  <SelectTrigger size="sm" className="w-56 text-sm bg-background">
                    <SelectValue>{videoDefaultModelLabel}</SelectValue>
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={DEFAULT_MEDIA_MODEL_VALUE}>
                      {t('videoGeneration.defaultModel')}
                    </SelectItem>
                    {videoModels.map((teamModel) => (
                      <SelectItem key={teamModel.id} value={teamModel.model.id}>
                        {getMediaModelOptionLabel(teamModel)}
                      </SelectItem>
                    ))}
                    {videoGenerationConfig.default_model_ref &&
                    !videoModels.some((teamModel) => teamModel.model.id === videoGenerationConfig.default_model_ref) ? (
                      <SelectItem value={videoGenerationConfig.default_model_ref}>
                        {videoGenerationConfig.default_model_ref}
                      </SelectItem>
                    ) : null}
                  </SelectContent>
                </Select>
              </div>

              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label className="text-xs">{t('videoGeneration.defaultDuration')}</Label>
                  <Input
                    type="number"
                    value={videoGenerationConfig.default_duration}
                    onChange={(e) => {
                      const value = parseFloat(e.target.value) || 5
                      setVideoGenerationConfig({
                        ...videoGenerationConfig,
                        default_duration: Math.min(Math.max(value, 1), 30),
                      })
                    }}
                    className="h-8 text-sm bg-background"
                    min={1}
                    max={30}
                    step={0.5}
                  />
                </div>
                <div className="space-y-2">
                  <Label className="text-xs">{t('videoGeneration.maxDuration')}</Label>
                  <Input
                    type="number"
                    value={videoGenerationConfig.max_duration}
                    onChange={(e) => {
                      const value = parseFloat(e.target.value) || 10
                      setVideoGenerationConfig({
                        ...videoGenerationConfig,
                        max_duration: Math.min(Math.max(value, 1), 30),
                      })
                    }}
                    className="h-8 text-sm bg-background"
                    min={1}
                    max={30}
                    step={0.5}
                  />
                </div>
              </div>

              <div className="space-y-2">
                <Label className="text-xs">{t('videoGeneration.aspectRatio')}</Label>
                <Select
                  value={videoGenerationConfig.default_aspect_ratio}
                  onValueChange={(value) => {
                    setVideoGenerationConfig({
                      ...videoGenerationConfig,
                      default_aspect_ratio: value || '16:9',
                    })
                  }}
                >
                  <SelectTrigger size="sm" className="w-36 text-sm bg-background">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="16:9">16:9</SelectItem>
                    <SelectItem value="9:16">9:16</SelectItem>
                    <SelectItem value="1:1">1:1</SelectItem>
                    <SelectItem value="4:3">4:3</SelectItem>
                    <SelectItem value="21:9">21:9</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label className="text-xs">{t('videoGeneration.pollInterval')}</Label>
                  <Input
                    type="number"
                    value={videoGenerationConfig.poll_interval_ms}
                    onChange={(e) => {
                      const value = parseInt(e.target.value) || 3000
                      setVideoGenerationConfig({
                        ...videoGenerationConfig,
                        poll_interval_ms: Math.min(Math.max(value, 500), 30000),
                      })
                    }}
                    className="h-8 text-sm bg-background"
                    min={500}
                    max={30000}
                    step={500}
                  />
                </div>
                <div className="space-y-2">
                  <Label className="text-xs">{t('videoGeneration.pollTimeout')}</Label>
                  <Input
                    type="number"
                    value={videoGenerationConfig.poll_timeout_s}
                    onChange={(e) => {
                      const value = parseInt(e.target.value) || 120
                      setVideoGenerationConfig({
                        ...videoGenerationConfig,
                        poll_timeout_s: Math.min(Math.max(value, 5), 600),
                      })
                    }}
                    className="h-8 text-sm bg-background"
                    min={5}
                    max={600}
                    step={5}
                  />
                </div>
              </div>

            </div>
          )}
        </div>
      </ConfigCard>
    </div>
  )
}
