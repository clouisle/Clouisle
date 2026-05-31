'use client'

import { useCallback, useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { ArrowLeft, Loader2, Save } from 'lucide-react'
import { toast } from 'sonner'
import { ApiError } from '@/lib/api'
import { adminWorkflowsApi, type AdminWorkflowDetail } from '@/lib/api/admin'
import type { TriggerType, WorkflowUpdateInput, WorkflowVisibility } from '@/lib/api/workflows'
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

export function AdminWorkflowEditClient({ workflowId }: { workflowId: string }) {
  const router = useRouter()
  const [workflow, setWorkflow] = useState<AdminWorkflowDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [icon, setIcon] = useState('')
  const [visibility, setVisibility] = useState<WorkflowVisibility>('private')
  const [triggerType, setTriggerType] = useState<TriggerType>('manual')
  const [definition, setDefinition] = useState('{}')
  const [variables, setVariables] = useState('[]')
  const [triggerConfig, setTriggerConfig] = useState('{}')
  const [embedConfig, setEmbedConfig] = useState('{}')

  const loadWorkflow = useCallback(async () => {
    setLoading(true)
    try {
      const data = await adminWorkflowsApi.getById(workflowId)
      setWorkflow(data)
      setName(data.name)
      setDescription(data.description ?? '')
      setIcon(data.icon ?? '')
      setVisibility(data.visibility)
      setTriggerType(data.trigger_type)
      setDefinition(formatJson(data.definition))
      setVariables(formatJson(data.variables))
      setTriggerConfig(formatJson(data.trigger_config))
      setEmbedConfig(formatJson(data.embed_config ?? {}))
    } catch (error) {
      toast.error(getErrorMessage(error))
    } finally {
      setLoading(false)
    }
  }, [workflowId])

  useEffect(() => {
    loadWorkflow()
  }, [loadWorkflow])

  const handleSave = async () => {
    if (!workflow) return
    const trimmedName = name.trim()
    if (!trimmedName) {
      toast.error('Name is required')
      return
    }

    setSaving(true)
    try {
      const payload: WorkflowUpdateInput = {
        name: trimmedName,
        description: description || null,
        icon: icon || null,
        visibility,
        trigger_type: triggerType,
        definition: parseJsonField(definition, 'Definition') as WorkflowUpdateInput['definition'],
        variables: parseJsonField(variables, 'Variables') as WorkflowUpdateInput['variables'],
        trigger_config: parseJsonField(triggerConfig, 'Trigger config') as WorkflowUpdateInput['trigger_config'],
        embed_config: parseJsonField(embedConfig, 'Embed config') as Record<string, unknown>,
      }
      const updated = await adminWorkflowsApi.update(workflow.id, payload)
      setWorkflow(updated)
      toast.success('Workflow updated successfully')
      router.push('/apps?tab=workflows')
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

  if (!workflow) {
    return <div className="text-sm text-muted-foreground">Workflow not found.</div>
  }

  return (
    <div className="mx-auto max-w-5xl space-y-4">
      <div className="flex items-center justify-between gap-4">
        <Button variant="ghost" onClick={() => router.push('/apps?tab=workflows')}>
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
          <CardTitle>Edit Workflow</CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="workflow-name">Name</Label>
              <Input id="workflow-name" value={name} onChange={(event) => setName(event.target.value)} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="workflow-visibility">Visibility</Label>
              <Select value={visibility} onValueChange={(value) => setVisibility(value as WorkflowVisibility)}>
                <SelectTrigger id="workflow-visibility"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="private">Private</SelectItem>
                  <SelectItem value="team">Team</SelectItem>
                  <SelectItem value="public">Public</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="workflow-icon">Icon</Label>
              <Input id="workflow-icon" value={icon} onChange={(event) => setIcon(event.target.value)} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="workflow-trigger-type">Trigger Type</Label>
              <Select value={triggerType} onValueChange={(value) => setTriggerType(value as TriggerType)}>
                <SelectTrigger id="workflow-trigger-type"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="manual">Manual</SelectItem>
                  <SelectItem value="cron">Cron</SelectItem>
                  <SelectItem value="webhook">Webhook</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2 md:col-span-2">
              <Label htmlFor="workflow-description">Description</Label>
              <Textarea id="workflow-description" rows={3} value={description} onChange={(event) => setDescription(event.target.value)} />
            </div>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <JsonField label="Definition" value={definition} onChange={setDefinition} />
            <JsonField label="Variables" value={variables} onChange={setVariables} />
            <JsonField label="Trigger Config" value={triggerConfig} onChange={setTriggerConfig} />
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
      <Textarea rows={14} className="font-mono text-xs" value={value} onChange={(event) => onChange(event.target.value)} />
    </div>
  )
}
