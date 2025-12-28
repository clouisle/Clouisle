'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { useTeam } from '@/contexts/team-context'
import { teamModelsApi, knowledgeBasesApi, type Agent, type TeamModel, type KnowledgeBase } from '@/lib/api'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  Select,
  SelectContent,
  SelectEmpty,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

interface AgentConfigFormProps {
  agent: Agent
  onSubmit: (data: Partial<Agent>) => Promise<void>
}

export function AgentConfigForm({ agent, onSubmit }: AgentConfigFormProps) {
  const t = useTranslations('agents')
  const { currentTeam } = useTeam()
  
  // Form state
  const [name, setName] = React.useState(agent.name)
  const [description, setDescription] = React.useState(agent.description || '')
  const [icon, setIcon] = React.useState(agent.icon || '')
  const [modelId, setModelId] = React.useState<string | null>(agent.model_id || null)
  const [systemPrompt, setSystemPrompt] = React.useState(agent.system_prompt || '')
  const [openingMessage, setOpeningMessage] = React.useState(agent.opening_message || '')
  const [suggestedQuestions, setSuggestedQuestions] = React.useState<string[]>(agent.suggested_questions || [])
  const [visibility, setVisibility] = React.useState(agent.visibility)
  
  // Data loading
  const [teamChatModels, setTeamChatModels] = React.useState<TeamModel[]>([])
  const [knowledgeBases, setKnowledgeBases] = React.useState<KnowledgeBase[]>([])
  const [isLoadingModels, setIsLoadingModels] = React.useState(false)
  
  // Load models and knowledge bases
  React.useEffect(() => {
    const loadData = async () => {
      if (!currentTeam) return
      
      setIsLoadingModels(true)
      try {
        const [models, kbs] = await Promise.all([
          teamModelsApi.getTeamModels(currentTeam.id, 'chat'),
          knowledgeBasesApi.getKnowledgeBases(),
        ])
        setTeamChatModels(models.filter(m => m.is_enabled))
        setKnowledgeBases(kbs.items.filter(kb => kb.team.id === currentTeam.id))
      } catch {
        // Ignore errors
      } finally {
        setIsLoadingModels(false)
      }
    }
    loadData()
  }, [currentTeam])
  
  // Get selected model name
  const selectedModelName = React.useMemo(() => {
    if (!modelId) return null
    const tm = teamChatModels.find(m => m.id === modelId)
    if (tm) return tm.model.name
    if (agent.model?.name) return agent.model.name
    return null
  }, [modelId, teamChatModels, agent])
  
  // Handle form submit
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    
    await onSubmit({
      name,
      description: description || null,
      icon: icon || null,
      model_id: modelId,
      system_prompt: systemPrompt || null,
      opening_message: openingMessage || null,
      suggested_questions: suggestedQuestions.filter(q => q.trim()),
      visibility,
    })
  }
  
  // Handle suggested questions
  const handleSuggestedQuestionsChange = (value: string) => {
    setSuggestedQuestions(value.split('\n').filter(q => q.trim()))
  }
  
  return (
    <form id="agent-config-form" onSubmit={handleSubmit}>
      <Tabs defaultValue="basic" className="w-full">
        <TabsList className="mb-4">
          <TabsTrigger value="basic">基础设置</TabsTrigger>
          <TabsTrigger value="prompt">提示词</TabsTrigger>
          <TabsTrigger value="model">模型配置</TabsTrigger>
          <TabsTrigger value="kb">知识库</TabsTrigger>
        </TabsList>
        
        {/* Basic Settings */}
        <TabsContent value="basic">
          <Card>
            <CardHeader>
              <CardTitle>基础信息</CardTitle>
              <CardDescription>设置 Agent 的基本信息</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="name">{t('name')}</Label>
                  <Input
                    id="name"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder={t('namePlaceholder')}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="icon">图标</Label>
                  <Input
                    id="icon"
                    value={icon}
                    onChange={(e) => setIcon(e.target.value)}
                    placeholder="输入 emoji，如 🤖"
                  />
                </div>
              </div>
              
              <div className="space-y-2">
                <Label htmlFor="description">{t('descriptionLabel')}</Label>
                <Textarea
                  id="description"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder={t('descriptionPlaceholder')}
                  rows={3}
                />
              </div>
              
              <div className="space-y-2">
                <Label htmlFor="visibility">{t('visibility')}</Label>
                <Select value={visibility} onValueChange={(v) => setVisibility(v as typeof visibility)}>
                  <SelectTrigger id="visibility" className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="private">{t('visibilityPrivate')}</SelectItem>
                    <SelectItem value="team">{t('visibilityTeam')}</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              
              <div className="space-y-2">
                <Label htmlFor="openingMessage">{t('openingMessage')}</Label>
                <Textarea
                  id="openingMessage"
                  value={openingMessage}
                  onChange={(e) => setOpeningMessage(e.target.value)}
                  placeholder={t('openingMessagePlaceholder')}
                  rows={2}
                />
              </div>
              
              <div className="space-y-2">
                <Label htmlFor="suggestedQuestions">{t('suggestedQuestions')}</Label>
                <Textarea
                  id="suggestedQuestions"
                  value={suggestedQuestions.join('\n')}
                  onChange={(e) => handleSuggestedQuestionsChange(e.target.value)}
                  placeholder="每行一个问题"
                  rows={3}
                />
                <p className="text-xs text-muted-foreground">{t('suggestedQuestionsHint')}</p>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
        
        {/* Prompt Settings */}
        <TabsContent value="prompt">
          <Card>
            <CardHeader>
              <CardTitle>{t('systemPrompt')}</CardTitle>
              <CardDescription>定义 Agent 的角色和行为</CardDescription>
            </CardHeader>
            <CardContent>
              <Textarea
                id="systemPrompt"
                value={systemPrompt}
                onChange={(e) => setSystemPrompt(e.target.value)}
                placeholder={t('systemPromptPlaceholder')}
                rows={15}
                className="font-mono text-sm"
              />
              <p className="text-xs text-muted-foreground mt-2">
                支持使用 {'{{变量名}}'} 格式插入变量
              </p>
            </CardContent>
          </Card>
        </TabsContent>
        
        {/* Model Settings */}
        <TabsContent value="model">
          <Card>
            <CardHeader>
              <CardTitle>模型配置</CardTitle>
              <CardDescription>选择和配置 LLM 模型</CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="space-y-2">
                <Label htmlFor="model">{t('model')}</Label>
                <Select 
                  value={modelId ?? undefined} 
                  onValueChange={setModelId}
                  disabled={isLoadingModels}
                >
                  <SelectTrigger id="model" className="w-full">
                    <SelectValue>
                      {selectedModelName || t('selectModel')}
                    </SelectValue>
                  </SelectTrigger>
                  <SelectContent>
                    {teamChatModels.length > 0 ? (
                      teamChatModels.map((tm) => (
                        <SelectItem key={tm.id} value={tm.id}>
                          {tm.model.name}
                        </SelectItem>
                      ))
                    ) : (
                      <SelectEmpty>{t('noModels')}</SelectEmpty>
                    )}
                  </SelectContent>
                </Select>
                <p className="text-xs text-muted-foreground">
                  温度、Top P、最大 Token 等参数在模型配置中设置
                </p>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
        
        {/* Knowledge Base Settings */}
        <TabsContent value="kb">
          <Card>
            <CardHeader>
              <CardTitle>{t('knowledgeBases')}</CardTitle>
              <CardDescription>{t('knowledgeBasesHint')}</CardDescription>
            </CardHeader>
            <CardContent>
              {knowledgeBases.length > 0 ? (
                <div className="space-y-2">
                  {knowledgeBases.map((kb) => {
                    const isConnected = agent.knowledge_bases.some(akb => akb.knowledge_base.id === kb.id)
                    return (
                      <div 
                        key={kb.id} 
                        className={`flex items-center justify-between p-3 rounded-lg border ${isConnected ? 'bg-primary/5 border-primary/20' : ''}`}
                      >
                        <div>
                          <div className="font-medium">{kb.name}</div>
                          {kb.description && (
                            <p className="text-sm text-muted-foreground">{kb.description}</p>
                          )}
                        </div>
                        <span className="text-sm text-muted-foreground">
                          {kb.document_count} 文档
                        </span>
                      </div>
                    )
                  })}
                  <p className="text-xs text-muted-foreground mt-2">
                    知识库关联功能即将推出
                  </p>
                </div>
              ) : (
                <p className="text-muted-foreground">{t('noKnowledgeBasesSelected')}</p>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </form>
  )
}
