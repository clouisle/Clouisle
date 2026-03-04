'use client'

import * as React from 'react'
import { useRouter } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { toast } from 'sonner'
import { agentsApi, type Agent, type AgentVisibility, type VariableDefinition, type AgentKnowledgeBaseConfig, type RAGMode, type ToolConfig, type FileUploadConfig, type MemoryConfig } from '@/lib/api'
import { ApiError } from '@/lib/api/client'
import { Skeleton } from '@/components/ui/skeleton'
import { ScrollArea } from '@/components/ui/scroll-area'
import { AgentSidebar } from './_components/agent-sidebar'
import { AgentToolbar } from './_components/agent-toolbar'
import { AgentOrchestrationForm } from './_components/agent-orchestration-form'
import { AgentPreviewPanel } from './_components/agent-preview-panel'
import { AgentSettingsDrawer } from './_components/agent-settings-drawer'

interface AgentConfigPageProps {
  params: Promise<{ id: string }>
}

export default function AgentConfigPage({ params }: AgentConfigPageProps) {
  const t = useTranslations('agents')
  const router = useRouter()

  const [agent, setAgent] = React.useState<Agent | null>(null)
  const [isLoading, setIsLoading] = React.useState(true)
  const [isSaving, setIsSaving] = React.useState(false)
  const [showSettings, setShowSettings] = React.useState(false)
  const [sidebarCollapsed, setSidebarCollapsed] = React.useState(false)

  // Form state
  const [name, setName] = React.useState('')
  const [description, setDescription] = React.useState('')
  const [icon, setIcon] = React.useState('')
  const [modelId, setModelId] = React.useState<string | null>(null)
  const [systemPrompt, setSystemPrompt] = React.useState('')
  const [maxIterations, setMaxIterations] = React.useState(5)
  const [openingMessage, setOpeningMessage] = React.useState('')
  const [suggestedQuestions, setSuggestedQuestions] = React.useState<string[]>([])
  const [visibility, setVisibility] = React.useState<AgentVisibility>('private')
  const [toolsConfig, setToolsConfig] = React.useState<ToolConfig[]>([])
  const [variables, setVariables] = React.useState<VariableDefinition[]>([])
  const [knowledgeBaseConfigs, setKnowledgeBaseConfigs] = React.useState<AgentKnowledgeBaseConfig[]>([])
  const [ragMode, setRagMode] = React.useState<RAGMode>('agentic')
  const [enableVision, setEnableVision] = React.useState(false)
  const [enableFileUpload, setEnableFileUpload] = React.useState(false)
  const [enableUserInputRequest, setEnableUserInputRequest] = React.useState(false)
  const [enableMemory, setEnableMemory] = React.useState(false)
  const [memoryConfig, setMemoryConfig] = React.useState<MemoryConfig | null>(null)
  const [fileUploadConfig, setFileUploadConfig] = React.useState<FileUploadConfig | null>(null)

  // Unwrap params
  const [resolvedParams, setResolvedParams] = React.useState<{ id: string } | null>(null)

  React.useEffect(() => {
    params.then(setResolvedParams)
  }, [params])

  // Fetch agent data
  const fetchAgent = React.useCallback(async () => {
    if (!resolvedParams) return

    try {
      setIsLoading(true)
      const data = await agentsApi.getAgent(resolvedParams.id)
      setAgent(data)
      // Initialize form state
      setName(data.name)
      setDescription(data.description || '')
      setIcon(data.icon || '')
      setModelId(data.model_id || null)
      setSystemPrompt(data.system_prompt || '')
      setMaxIterations(data.max_iterations || 5)
      setOpeningMessage(data.opening_message || '')
      setSuggestedQuestions(data.suggested_questions || [])
      setVisibility(data.visibility)
      setToolsConfig(data.tools_config || [])
      setVariables(data.variables || [])
      setKnowledgeBaseConfigs(data.knowledge_bases.map(akb => ({
        knowledge_base_id: akb.knowledge_base.id,
        retrieval_top_k: akb.retrieval_top_k,
        score_threshold: akb.score_threshold,
      })))
      setRagMode(data.rag_mode || 'agentic')
      setEnableVision(data.enable_vision || false)
      setEnableFileUpload(data.enable_file_upload || false)
      setEnableUserInputRequest(data.enable_user_input_request || false)
      setEnableMemory(data.enable_memory || false)
      setMemoryConfig(data.memory_config || null)
      setFileUploadConfig(data.file_upload_config || null)
    } catch {
      router.push('/app/apps')
    } finally {
      setIsLoading(false)
    }
  }, [resolvedParams, router])

  React.useEffect(() => {
    fetchAgent()
  }, [fetchAgent])

  // Manual save
  const handleSave = React.useCallback(async () => {
    if (!agent || isSaving) return

    setIsSaving(true)
    try {
      const updated = await agentsApi.updateAgent(agent.id, {
        name,
        description: description || null,
        icon: icon || null,
        model_id: modelId,
        system_prompt: systemPrompt || null,
        max_iterations: maxIterations,
        opening_message: openingMessage || null,
        suggested_questions: suggestedQuestions.filter((q) => q.trim()),
        visibility,
        tools_config: toolsConfig,
        variables: variables,
        knowledge_base_configs: knowledgeBaseConfigs,
        rag_mode: ragMode,
        enable_vision: enableVision,
        enable_file_upload: enableFileUpload,
        enable_user_input_request: enableUserInputRequest,
        enable_memory: enableMemory,
        memory_config: enableMemory ? memoryConfig : null,
        file_upload_config: enableFileUpload ? fileUploadConfig : null,
      })
      setAgent(updated)
      toast.success(t('agentSaved'))
    } catch (err) {
      // 验证错误需要手动显示 toast（API client 默认不显示）
      if (err instanceof ApiError && err.isValidationError()) {
        const fieldErrors = err.getFieldErrors()
        const errorMsg = Object.values(fieldErrors).flat().join(', ') || err.message
        toast.error(errorMsg)
      }
      // 其他错误由 API client 自动处理
    } finally {
      setIsSaving(false)
    }
  }, [
    agent,
    isSaving,
    name,
    description,
    icon,
    modelId,
    systemPrompt,
    maxIterations,
    openingMessage,
    suggestedQuestions,
    visibility,
    toolsConfig,
    variables,
    knowledgeBaseConfigs,
    ragMode,
    enableVision,
    enableFileUpload,
    enableUserInputRequest,
    enableMemory,
    memoryConfig,
    fileUploadConfig,
    t,
  ])

  // Handle publish
  const handlePublish = async () => {
    if (!agent) return

    try {
      if (agent.status === 'draft') {
        const updated = await agentsApi.publishAgent(agent.id)
        setAgent(updated)
        toast.success(t('agentPublished'))
      } else {
        const updated = await agentsApi.unpublishAgent(agent.id)
        setAgent(updated)
        toast.success(t('agentUnpublished'))
      }
    } catch {
      // Error handled by API client
    }
  }

  // Handle orchestration form update
  const handleOrchestrationUpdate = (data: Partial<Agent> & { knowledge_base_configs?: AgentKnowledgeBaseConfig[]; rag_mode?: RAGMode }) => {
    if (data.system_prompt !== undefined) {
      setSystemPrompt(data.system_prompt || '')
    }
    if (data.tools_config !== undefined) {
      setToolsConfig(data.tools_config || [])
    }
    if (data.variables !== undefined) {
      setVariables(data.variables || [])
    }
    if (data.knowledge_base_configs !== undefined) {
      setKnowledgeBaseConfigs(data.knowledge_base_configs || [])
    }
    if (data.rag_mode !== undefined) {
      setRagMode(data.rag_mode)
    }
    if (data.enable_vision !== undefined) {
      setEnableVision(data.enable_vision)
    }
    if (data.enable_file_upload !== undefined) {
      setEnableFileUpload(data.enable_file_upload)
    }
    if (data.enable_user_input_request !== undefined) {
      setEnableUserInputRequest(data.enable_user_input_request)
    }
    if (data.enable_memory !== undefined) {
      setEnableMemory(data.enable_memory)
    }
    if (data.memory_config !== undefined) {
      setMemoryConfig(data.memory_config || null)
    }
    if (data.file_upload_config !== undefined) {
      setFileUploadConfig(data.file_upload_config || null)
    }
  }

  // Check if tools are enabled
  const hasToolsEnabled = toolsConfig.length > 0

  if (isLoading || !agent) {
    return (
      <div className="h-screen flex">
        <div className="w-52 border-r p-4">
          <Skeleton className="h-10 w-full mb-4" />
          <Skeleton className="h-8 w-full mb-2" />
          <Skeleton className="h-8 w-full mb-2" />
          <Skeleton className="h-8 w-full mb-2" />
        </div>
        <div className="flex-1 p-6">
          <Skeleton className="h-150 rounded-lg" />
        </div>
      </div>
    )
  }

  return (
    <div className="h-full flex overflow-hidden">
      {/* Left Sidebar - Agent Info & Navigation */}
      <AgentSidebar agent={agent} collapsed={sidebarCollapsed} />

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Toolbar */}
        <AgentToolbar
          agent={agent}
          onPublish={handlePublish}
          onSave={handleSave}
          isSaving={isSaving}
          onSettingsClick={() => setShowSettings(true)}
          sidebarCollapsed={sidebarCollapsed}
          onToggleSidebar={() => setSidebarCollapsed(!sidebarCollapsed)}
        />

        {/* Content */}
        <div className="flex-1 flex h-full overflow-hidden p-6 gap-6 min-h-0">
          {/* Orchestration Form */}
          <ScrollArea className="flex-1 min-h-0 [&_[data-slot=scroll-area-scrollbar]]:border-l-0">
            <div className="max-w-3xl">
              <AgentOrchestrationForm
                agent={agent}
                onUpdate={handleOrchestrationUpdate}
              />
            </div>
          </ScrollArea>

          {/* Preview Panel */}
          <div className="w-95 min-w-95 shrink-0 h-full min-h-0 overflow-hidden border rounded-lg">
            <AgentPreviewPanel agent={agent} />
          </div>
        </div>
      </div>

      {/* Settings Drawer */}
      <AgentSettingsDrawer
        agent={agent}
        open={showSettings}
        onOpenChange={setShowSettings}
        name={name}
        onNameChange={setName}
        description={description}
        onDescriptionChange={setDescription}
        icon={icon}
        onIconChange={setIcon}
        openingMessage={openingMessage}
        onOpeningMessageChange={setOpeningMessage}
        suggestedQuestions={suggestedQuestions}
        onSuggestedQuestionsChange={setSuggestedQuestions}
        visibility={visibility}
        onVisibilityChange={setVisibility}
        modelId={modelId}
        onModelChange={setModelId}
        maxIterations={maxIterations}
        onMaxIterationsChange={setMaxIterations}
        hasToolsEnabled={hasToolsEnabled}
      />
    </div>
  )
}
