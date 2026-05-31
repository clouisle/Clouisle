'use client'

import { useCallback, useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { ArrowLeft, Loader2, Save } from 'lucide-react'
import { toast } from 'sonner'
import { ApiError } from '@/lib/api'
import { adminAgentsApi, type AdminAgentDetail } from '@/lib/api/admin'
import type { AgentUpdateInput } from '@/lib/api/agents'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'

function getErrorMessage(error: unknown) {
  if (error instanceof ApiError) return error.message
  if (error instanceof Error) return error.message
  return 'Unknown error'
}

function parseJsonField(value: string, fieldName: string) {
  if (!value.trim()) return undefined
  try {
    return JSON.parse(value) as unknown
  } catch {
    throw new Error(`${fieldName} must be valid JSON`)
  }
}

function formatJson(value: unknown) {
  return JSON.stringify(value ?? null, null, 2)
}

export function AdminAgentEditClient({ agentId }: { agentId: string }) {
  const router = useRouter()
  const [agent, setAgent] = useState<AdminAgentDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [icon, setIcon] = useState('')
  const [avatarUrl, setAvatarUrl] = useState('')
  const [systemPrompt, setSystemPrompt] = useState('')
  const [maxIterations, setMaxIterations] = useState('')
  const [visibility, setVisibility] = useState<'private' | 'team'>('private')
  const [hideToolCalls, setHideToolCalls] = useState(false)
  const [enableVision, setEnableVision] = useState(false)
  const [enableFileUpload, setEnableFileUpload] = useState(false)
  const [enableUserInputRequest, setEnableUserInputRequest] = useState(false)
  const [enableMemory, setEnableMemory] = useState(false)
  const [enableImageGeneration, setEnableImageGeneration] = useState(false)
  const [enableVideoGeneration, setEnableVideoGeneration] = useState(false)
  const [ragMode, setRagMode] = useState<'off' | 'auto' | 'agentic'>('off')
  const [openingMessage, setOpeningMessage] = useState('')
  const [suggestedQuestions, setSuggestedQuestions] = useState('[]')
  const [variables, setVariables] = useState('[]')
  const [toolsConfig, setToolsConfig] = useState('[]')
  const [knowledgeBaseConfigs, setKnowledgeBaseConfigs] = useState('[]')
  const [fileUploadConfig, setFileUploadConfig] = useState('null')
  const [memoryConfig, setMemoryConfig] = useState('null')
  const [contextCompressionConfig, setContextCompressionConfig] = useState('null')
  const [imageGenerationConfig, setImageGenerationConfig] = useState('null')
  const [videoGenerationConfig, setVideoGenerationConfig] = useState('null')
  const [embedConfig, setEmbedConfig] = useState('{}')

  const loadAgent = useCallback(async () => {
    setLoading(true)
    try {
      const data = await adminAgentsApi.getById(agentId)
      setAgent(data)
      setName(data.name)
      setDescription(data.description ?? '')
      setIcon(data.icon ?? '')
      setAvatarUrl(data.avatar_url ?? '')
      setSystemPrompt(data.system_prompt ?? '')
      setMaxIterations(String(data.max_iterations))
      setVisibility(data.visibility === 'team' ? 'team' : 'private')
      setHideToolCalls(data.hide_tool_calls)
      setEnableVision(data.enable_vision)
      setEnableFileUpload(data.enable_file_upload)
      setEnableUserInputRequest(data.enable_user_input_request)
      setEnableMemory(data.enable_memory)
      setEnableImageGeneration(data.enable_image_generation)
      setEnableVideoGeneration(data.enable_video_generation)
      setRagMode(data.rag_mode)
      setOpeningMessage(data.opening_message ?? '')
      setSuggestedQuestions(formatJson(data.suggested_questions))
      setVariables(formatJson(data.variables))
      setToolsConfig(formatJson(data.tools_config))
      setKnowledgeBaseConfigs(formatJson(data.knowledge_bases.map((kb) => ({
        knowledge_base_id: kb.knowledge_base.id,
        retrieval_top_k: kb.retrieval_top_k,
        score_threshold: kb.score_threshold,
        search_mode: kb.search_mode,
      }))))
      setFileUploadConfig(formatJson(data.file_upload_config))
      setMemoryConfig(formatJson(data.memory_config))
      setContextCompressionConfig(formatJson(data.context_compression_config))
      setImageGenerationConfig(formatJson(data.image_generation_config))
      setVideoGenerationConfig(formatJson(data.video_generation_config))
      setEmbedConfig(formatJson(data.embed_config ?? {}))
    } catch (error) {
      toast.error(getErrorMessage(error))
    } finally {
      setLoading(false)
    }
  }, [agentId])

  useEffect(() => {
    loadAgent()
  }, [loadAgent])

  const handleSave = async () => {
    if (!agent) return
    const trimmedName = name.trim()
    if (!trimmedName) {
      toast.error('Name is required')
      return
    }

    setSaving(true)
    try {
      const parsedMaxIterations = Number(maxIterations)
      const payload: AgentUpdateInput = {
        name: trimmedName,
        description: description || null,
        icon: icon || null,
        avatar_url: avatarUrl || null,
        system_prompt: systemPrompt || null,
        max_iterations: parsedMaxIterations,
        hide_tool_calls: hideToolCalls,
        visibility,
        enable_vision: enableVision,
        enable_file_upload: enableFileUpload,
        enable_user_input_request: enableUserInputRequest,
        enable_memory: enableMemory,
        enable_image_generation: enableImageGeneration,
        enable_video_generation: enableVideoGeneration,
        rag_mode: ragMode,
        opening_message: openingMessage || null,
        suggested_questions: parseJsonField(suggestedQuestions, 'Suggested questions') as string[],
        variables: parseJsonField(variables, 'Variables') as AgentUpdateInput['variables'],
        tools_config: parseJsonField(toolsConfig, 'Tools config') as AgentUpdateInput['tools_config'],
        knowledge_base_configs: parseJsonField(knowledgeBaseConfigs, 'Knowledge base configs') as AgentUpdateInput['knowledge_base_configs'],
        file_upload_config: parseJsonField(fileUploadConfig, 'File upload config') as AgentUpdateInput['file_upload_config'],
        memory_config: parseJsonField(memoryConfig, 'Memory config') as AgentUpdateInput['memory_config'],
        context_compression_config: parseJsonField(contextCompressionConfig, 'Context compression config') as AgentUpdateInput['context_compression_config'],
        image_generation_config: parseJsonField(imageGenerationConfig, 'Image generation config') as AgentUpdateInput['image_generation_config'],
        video_generation_config: parseJsonField(videoGenerationConfig, 'Video generation config') as AgentUpdateInput['video_generation_config'],
        embed_config: parseJsonField(embedConfig, 'Embed config') as Record<string, unknown>,
      }
      const updated = await adminAgentsApi.update(agent.id, payload)
      setAgent(updated)
      toast.success('Agent updated successfully')
      router.push('/apps')
    } catch (error) {
      toast.error(getErrorMessage(error))
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (!agent) {
    return <div className="text-sm text-muted-foreground">Agent not found.</div>
  }

  return (
    <div className="mx-auto max-w-5xl space-y-4">
      <div className="flex items-center justify-between gap-4">
        <Button variant="ghost" onClick={() => router.push('/apps')}>
          <ArrowLeft className="mr-2 h-4 w-4" />
          Back
        </Button>
        <Button onClick={handleSave} disabled={saving}>
          {saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Save className="mr-2 h-4 w-4" />}
          Save
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Edit Agent</CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="agent-name">Name</Label>
              <Input id="agent-name" value={name} onChange={(event) => setName(event.target.value)} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="agent-visibility">Visibility</Label>
              <Select value={visibility} onValueChange={(value) => setVisibility(value as 'private' | 'team')}>
                <SelectTrigger id="agent-visibility"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="private">Private</SelectItem>
                  <SelectItem value="team">Team</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="agent-icon">Icon</Label>
              <Input id="agent-icon" value={icon} onChange={(event) => setIcon(event.target.value)} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="agent-avatar">Avatar URL</Label>
              <Input id="agent-avatar" value={avatarUrl} onChange={(event) => setAvatarUrl(event.target.value)} />
            </div>
            <div className="space-y-2 md:col-span-2">
              <Label htmlFor="agent-description">Description</Label>
              <Textarea id="agent-description" rows={3} value={description} onChange={(event) => setDescription(event.target.value)} />
            </div>
            <div className="space-y-2 md:col-span-2">
              <Label htmlFor="agent-system-prompt">System Prompt</Label>
              <Textarea id="agent-system-prompt" rows={8} value={systemPrompt} onChange={(event) => setSystemPrompt(event.target.value)} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="agent-max-iterations">Max Iterations</Label>
              <Input id="agent-max-iterations" type="number" min={1} max={200} value={maxIterations} onChange={(event) => setMaxIterations(event.target.value)} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="agent-rag-mode">RAG Mode</Label>
              <Select value={ragMode} onValueChange={(value) => setRagMode(value as 'off' | 'auto' | 'agentic')}>
                <SelectTrigger id="agent-rag-mode"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="off">Off</SelectItem>
                  <SelectItem value="auto">Auto</SelectItem>
                  <SelectItem value="agentic">Agentic</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2 md:col-span-2">
              <Label htmlFor="agent-opening-message">Opening Message</Label>
              <Textarea id="agent-opening-message" rows={3} value={openingMessage} onChange={(event) => setOpeningMessage(event.target.value)} />
            </div>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            {[
              ['Hide tool calls', hideToolCalls, setHideToolCalls],
              ['Vision', enableVision, setEnableVision],
              ['File upload', enableFileUpload, setEnableFileUpload],
              ['User input request', enableUserInputRequest, setEnableUserInputRequest],
              ['Memory', enableMemory, setEnableMemory],
              ['Image generation', enableImageGeneration, setEnableImageGeneration],
              ['Video generation', enableVideoGeneration, setEnableVideoGeneration],
            ].map(([label, value, setter]) => (
              <div key={label as string} className="flex items-center justify-between rounded-lg border p-3">
                <Label>{label as string}</Label>
                <Switch checked={value as boolean} onCheckedChange={setter as (checked: boolean) => void} />
              </div>
            ))}
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <JsonField label="Suggested Questions" value={suggestedQuestions} onChange={setSuggestedQuestions} />
            <JsonField label="Variables" value={variables} onChange={setVariables} />
            <JsonField label="Tools Config" value={toolsConfig} onChange={setToolsConfig} />
            <JsonField label="Knowledge Base Configs" value={knowledgeBaseConfigs} onChange={setKnowledgeBaseConfigs} />
            <JsonField label="File Upload Config" value={fileUploadConfig} onChange={setFileUploadConfig} />
            <JsonField label="Memory Config" value={memoryConfig} onChange={setMemoryConfig} />
            <JsonField label="Context Compression Config" value={contextCompressionConfig} onChange={setContextCompressionConfig} />
            <JsonField label="Image Generation Config" value={imageGenerationConfig} onChange={setImageGenerationConfig} />
            <JsonField label="Video Generation Config" value={videoGenerationConfig} onChange={setVideoGenerationConfig} />
            <JsonField label="Embed Config" value={embedConfig} onChange={setEmbedConfig} />
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

function JsonField({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return (
    <div className="space-y-2">
      <Label>{label}</Label>
      <Textarea rows={8} className="font-mono text-xs" value={value} onChange={(event) => onChange(event.target.value)} />
    </div>
  )
}
