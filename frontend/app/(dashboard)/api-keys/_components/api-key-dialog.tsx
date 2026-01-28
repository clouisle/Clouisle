'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { toast } from 'sonner'
import { apiKeysApi, agentsApi, workflowsApi, ApiError, type APIKey, type APIKeyCreateInput, type APIKeyUpdateInput, type AgentListItem, type WorkflowListItem } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Checkbox } from '@/components/ui/checkbox'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Bot, Loader2, Workflow } from 'lucide-react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

interface APIKeyDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  apiKey?: APIKey | null // 编辑时传入，创建时为 null
  onSuccess?: (key?: string) => void
}

export function APIKeyDialog({ open, onOpenChange, apiKey, onSuccess }: APIKeyDialogProps) {
  const t = useTranslations('apiKeys')
  const commonT = useTranslations('common')
  
  const isEditing = !!apiKey
  
  const [formData, setFormData] = React.useState({
    name: '',
    rate_limit: 0,
    expires_at: '',
    is_active: true,
    agent_ids: [] as string[],
    workflow_ids: [] as string[],
  })
  const [fieldErrors, setFieldErrors] = React.useState<Record<string, string>>({})
  const [isSubmitting, setIsSubmitting] = React.useState(false)
  const [agents, setAgents] = React.useState<AgentListItem[]>([])
  const [isLoadingAgents, setIsLoadingAgents] = React.useState(false)
  const [workflows, setWorkflows] = React.useState<WorkflowListItem[]>([])
  const [isLoadingWorkflows, setIsLoadingWorkflows] = React.useState(false)
  
  // 加载所有已发布的 Agent 列表（不限团队）
  React.useEffect(() => {
    if (open) {
      setIsLoadingAgents(true)
      agentsApi.getAgents({ pageSize: 100, status: 'published' })
        .then((data) => {
          setAgents(data.items)
        })
        .catch((error) => {
          console.error('Failed to load agents:', error)
        })
        .finally(() => {
          setIsLoadingAgents(false)
        })
    }
  }, [open])

  // 加载所有已发布的 Workflow 列表（不限团队）
  React.useEffect(() => {
    if (open) {
      setIsLoadingWorkflows(true)
      workflowsApi.getWorkflows({ pageSize: 100, status: 'published' })
        .then((data) => {
          setWorkflows(data.items)
        })
        .catch((error) => {
          console.error('Failed to load workflows:', error)
        })
        .finally(() => {
          setIsLoadingWorkflows(false)
        })
    }
  }, [open])
  
  // 当 apiKey 改变或 dialog 打开时重置表单
  React.useEffect(() => {
    if (open) {
      if (apiKey) {
        setFormData({
          name: apiKey.name,
          rate_limit: apiKey.rate_limit,
          expires_at: apiKey.expires_at
            ? new Date(apiKey.expires_at).toISOString().split('T')[0]
            : '',
          is_active: apiKey.is_active,
          agent_ids: apiKey.agents?.map(a => a.id) || [],
          workflow_ids: apiKey.workflows?.map(w => w.id) || [],
        })
      } else {
        setFormData({
          name: '',
          rate_limit: 0,
          expires_at: '',
          is_active: true,
          agent_ids: [],
          workflow_ids: [],
        })
      }
      setFieldErrors({})
    }
  }, [open, apiKey])
  
  const handleAgentToggle = (agentId: string, checked: boolean) => {
    setFormData(prev => ({
      ...prev,
      agent_ids: checked
        ? [...prev.agent_ids, agentId]
        : prev.agent_ids.filter(id => id !== agentId)
    }))
  }

  const handleWorkflowToggle = (workflowId: string, checked: boolean) => {
    setFormData(prev => ({
      ...prev,
      workflow_ids: checked
        ? [...prev.workflow_ids, workflowId]
        : prev.workflow_ids.filter(id => id !== workflowId)
    }))
  }
  
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setFieldErrors({})
    
    // 验证
    if (!formData.name.trim()) {
      setFieldErrors({ name: t('nameRequired') })
      return
    }
    
    setIsSubmitting(true)
    
    try {
      if (isEditing && apiKey) {
        // 编辑
        const updateData: APIKeyUpdateInput = {
          name: formData.name,
          rate_limit: formData.rate_limit,
          expires_at: formData.expires_at ? new Date(formData.expires_at).toISOString() : null,
          is_active: formData.is_active,
          agent_ids: formData.agent_ids,
          workflow_ids: formData.workflow_ids,
        }
        await apiKeysApi.updateAPIKey(apiKey.id, updateData)
        toast.success(t('keyUpdated'))
        onSuccess?.()
      } else {
        // 创建
        const createData: APIKeyCreateInput = {
          name: formData.name,
          rate_limit: formData.rate_limit,
          expires_at: formData.expires_at ? new Date(formData.expires_at).toISOString() : null,
          agent_ids: formData.agent_ids,
          workflow_ids: formData.workflow_ids,
        }
        const result = await apiKeysApi.createAPIKey(createData)
        toast.success(t('keyCreated'))
        onSuccess?.(result.key) // 传递新创建的 key
      }
      
      onOpenChange(false)
    } catch (error) {
      if (error instanceof ApiError && error.isValidationError()) {
        setFieldErrors(error.getFieldErrors())
      }
    } finally {
      setIsSubmitting(false)
    }
  }
  
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle>{isEditing ? t('editKey') : t('createKey')}</DialogTitle>
          <DialogDescription>
            {isEditing ? t('editKeyDescription') : t('createKeyDescription')}
          </DialogDescription>
        </DialogHeader>
        
        <form onSubmit={handleSubmit} className="grid gap-4">
          <div className="grid gap-2">
            <Label htmlFor="name">{t('name')}</Label>
            <Input
              id="name"
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              placeholder={t('namePlaceholder')}
              required
              autoFocus
            />
            {fieldErrors.name && (
              <p className="text-sm text-destructive">{fieldErrors.name}</p>
            )}
          </div>
          
          <div className="grid gap-2">
            <Label htmlFor="rate_limit">{t('rateLimit')}</Label>
            <Input
              id="rate_limit"
              type="number"
              min="0"
              value={formData.rate_limit}
              onChange={(e) => setFormData({ ...formData, rate_limit: parseInt(e.target.value) || 0 })}
            />
            <p className="text-xs text-muted-foreground">{t('rateLimitHint')}</p>
          </div>
          
          <div className="grid gap-2">
            <Label htmlFor="expires_at">{t('expiresAt')}</Label>
            <Input
              id="expires_at"
              type="date"
              value={formData.expires_at}
              onChange={(e) => setFormData({ ...formData, expires_at: e.target.value })}
            />
            <p className="text-xs text-muted-foreground">{t('expiresAtHint')}</p>
          </div>

          {/* Agent 和 Workflow 选择 - 横向布局 */}
          <div className="grid grid-cols-2 gap-4">
            {/* Agent 选择 */}
            <div className="grid gap-2">
              <Label>{t('allowedAgents')}</Label>
              <p className="text-xs text-muted-foreground">{t('allowedAgentsHint')}</p>
              {isLoadingAgents ? (
                <div className="flex items-center justify-center py-4">
                  <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                </div>
              ) : agents.length === 0 ? (
                <p className="text-sm text-muted-foreground py-2">{t('noAgentsAvailable')}</p>
              ) : (
                <ScrollArea className="h-[150px] rounded-md border p-2">
                  <div className="space-y-2">
                    {agents.map((agent) => (
                      <div
                        key={agent.id}
                        className="flex items-center space-x-3 rounded-md p-2 hover:bg-muted/50"
                      >
                        <Checkbox
                          id={`agent-${agent.id}`}
                          checked={formData.agent_ids.includes(agent.id)}
                          onCheckedChange={(checked) => handleAgentToggle(agent.id, !!checked)}
                        />
                        <label
                          htmlFor={`agent-${agent.id}`}
                          className="flex flex-1 items-center gap-2 cursor-pointer text-sm"
                        >
                          {agent.icon || agent.avatar_url ? (
                            <img
                              src={agent.icon || agent.avatar_url || ''}
                              alt={agent.name}
                              className="h-5 w-5 rounded object-cover"
                            />
                          ) : (
                            <Bot className="h-5 w-5 text-muted-foreground" />
                          )}
                          <span className="font-medium truncate">{agent.name}</span>
                        </label>
                      </div>
                    ))}
                  </div>
                </ScrollArea>
              )}
            </div>

            {/* Workflow 选择 */}
            <div className="grid gap-2">
              <Label>{t('allowedWorkflows')}</Label>
              <p className="text-xs text-muted-foreground">{t('allowedWorkflowsHint')}</p>
              {isLoadingWorkflows ? (
                <div className="flex items-center justify-center py-4">
                  <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                </div>
              ) : workflows.length === 0 ? (
                <p className="text-sm text-muted-foreground py-2">{t('noWorkflowsAvailable')}</p>
              ) : (
                <ScrollArea className="h-[150px] rounded-md border p-2">
                  <div className="space-y-2">
                    {workflows.map((workflow) => (
                      <div
                        key={workflow.id}
                        className="flex items-center space-x-3 rounded-md p-2 hover:bg-muted/50"
                      >
                        <Checkbox
                          id={`workflow-${workflow.id}`}
                          checked={formData.workflow_ids.includes(workflow.id)}
                          onCheckedChange={(checked) => handleWorkflowToggle(workflow.id, !!checked)}
                        />
                        <label
                          htmlFor={`workflow-${workflow.id}`}
                          className="flex flex-1 items-center gap-2 cursor-pointer text-sm"
                        >
                          {workflow.icon ? (
                            <img
                              src={workflow.icon}
                              alt={workflow.name}
                              className="h-5 w-5 rounded object-cover"
                            />
                          ) : (
                            <Workflow className="h-5 w-5 text-muted-foreground" />
                          )}
                          <span className="font-medium truncate">{workflow.name}</span>
                        </label>
                      </div>
                    ))}
                  </div>
                </ScrollArea>
              )}
            </div>
          </div>

          {isEditing && (
            <div className="flex items-center justify-between">
              <Label htmlFor="is_active">{t('active')}</Label>
              <Switch
                id="is_active"
                checked={formData.is_active}
                onCheckedChange={(checked) => setFormData({ ...formData, is_active: checked })}
              />
            </div>
          )}
          
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={isSubmitting}
            >
              {commonT('cancel')}
            </Button>
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting
                ? commonT('loading')
                : isEditing
                  ? commonT('save')
                  : commonT('create')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
