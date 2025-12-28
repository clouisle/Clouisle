'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { toast } from 'sonner'
import { knowledgeBasesApi, modelsApi, teamsApi, type KnowledgeBase, type KnowledgeBaseCreateInput, type ModelBrief, type UserTeamInfo, ApiError } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectEmpty,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'

interface KnowledgeBaseDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  knowledgeBase: KnowledgeBase | null
  onSuccess: () => void
}

export function KnowledgeBaseDialog({
  open,
  onOpenChange,
  knowledgeBase,
  onSuccess,
}: KnowledgeBaseDialogProps) {
  const t = useTranslations('knowledgeBases')
  const commonT = useTranslations('common')
  
  const isEditing = !!knowledgeBase
  
  // 表单状态
  const [name, setName] = React.useState('')
  const [description, setDescription] = React.useState('')
  const [teamId, setTeamId] = React.useState<string>('')
  const [embeddingModelId, setEmbeddingModelId] = React.useState<string>('')
  const [chunkSize, setChunkSize] = React.useState(500)
  const [chunkOverlap, setChunkOverlap] = React.useState(50)
  const [separator, setSeparator] = React.useState<string>('')
  const [isActive, setIsActive] = React.useState(true)
  const [isLoading, setIsLoading] = React.useState(false)
  const [fieldErrors, setFieldErrors] = React.useState<Record<string, string>>({})
  
  // 模型列表和团队列表
  const [embeddingModels, setEmbeddingModels] = React.useState<ModelBrief[]>([])
  const [teams, setTeams] = React.useState<UserTeamInfo[]>([])
  
  // 获取当前选中模型的名称
  const selectedModelName = React.useMemo(() => {
    if (!embeddingModelId) return null
    // 先从模型列表中查找
    const model = embeddingModels.find(m => m.id === embeddingModelId)
    if (model) return model.name
    // 编辑时，使用知识库自带的模型信息
    if (knowledgeBase?.embedding_model?.name) {
      return knowledgeBase.embedding_model.name
    }
    return null
  }, [embeddingModelId, embeddingModels, knowledgeBase])
  
  // 加载数据
  React.useEffect(() => {
    const loadData = async () => {
      try {
        const [models, userTeams] = await Promise.all([
          modelsApi.getAvailableModels('embedding'),
          teamsApi.getMyTeams(),
        ])
        setEmbeddingModels(models)
        setTeams(userTeams)
        // 如果没有选择团队，默认选择第一个可写团队
        if (!isEditing && userTeams.length > 0) {
          const writableTeam = userTeams.find(t => ['owner', 'admin', 'member'].includes(t.role))
          if (writableTeam) {
            setTeamId(writableTeam.id)
          }
        }
      } catch {
        // 忽略错误
      }
    }
    if (open) {
      loadData()
    }
  }, [open, isEditing])
  
  // 初始化表单
  React.useEffect(() => {
    if (open) {
      if (knowledgeBase) {
        setName(knowledgeBase.name)
        setDescription(knowledgeBase.description || '')
        setEmbeddingModelId(knowledgeBase.embedding_model_id || '')
        setChunkSize(knowledgeBase.settings?.chunk_size ?? 500)
        setChunkOverlap(knowledgeBase.settings?.chunk_overlap ?? 50)
        setSeparator(knowledgeBase.settings?.separator || '')
        setIsActive(knowledgeBase.status === 'active')
        // 编辑时不需要重新选择团队
      } else {
        setName('')
        setDescription('')
        setEmbeddingModelId('')
        setChunkSize(500)
        setChunkOverlap(50)
        setSeparator('')
        setIsActive(true)
      }
      setFieldErrors({})
    }
  }, [open, knowledgeBase])
  
  // 提交
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    
    // 基本验证
    if (!name.trim()) {
      setFieldErrors({ name: t('nameRequired') })
      return
    }
    
    if (!isEditing && !teamId) {
      setFieldErrors({ team_id: t('teamRequired') })
      return
    }
    
    setIsLoading(true)
    setFieldErrors({})
    
    try {
      const data: KnowledgeBaseCreateInput = {
        name: name.trim(),
        description: description.trim() || null,
        embedding_model_id: embeddingModelId || null,
        settings: {
          chunk_size: chunkSize,
          chunk_overlap: chunkOverlap,
          separator: separator.trim() || null,
        },
      }
      
      if (isEditing) {
        await knowledgeBasesApi.updateKnowledgeBase(knowledgeBase!.id, {
          ...data,
          status: isActive ? 'active' : 'archived',
        })
        toast.success(t('kbUpdated'))
      } else {
        await knowledgeBasesApi.createKnowledgeBase({ ...data, team_id: teamId! })
        toast.success(t('kbCreated'))
      }
      
      onOpenChange(false)
      onSuccess()
    } catch (error) {
      if (error instanceof ApiError && error.isValidationError()) {
        setFieldErrors(error.getFieldErrors())
      }
      // 其他错误已由 API 客户端处理
    } finally {
      setIsLoading(false)
    }
  }
  
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-125">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>
              {isEditing ? t('editKb') : t('createKb')}
            </DialogTitle>
            <DialogDescription>
              {isEditing ? t('editKbDescription') : t('createKbDescription')}
            </DialogDescription>
          </DialogHeader>
          
          <div className="grid gap-4 py-4">
            {/* 名称 */}
            <div className="space-y-2">
              <Label htmlFor="name">{t('name')}</Label>
              <Input
                id="name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder={t('namePlaceholder')}
              />
              {fieldErrors.name && (
                <p className="text-sm text-destructive">{fieldErrors.name}</p>
              )}
            </div>
            
            {/* 团队选择 - 仅创建时显示 */}
            {!isEditing && (
              <div className="space-y-2">
                <Label htmlFor="team">{t('team')}</Label>
                <Select value={teamId} onValueChange={(v) => v && setTeamId(v)}>
                  <SelectTrigger id="team" className="w-full">
                    <SelectValue>
                      {teamId 
                        ? teams.find(t => t.id === teamId)?.name 
                        : t('selectTeam')}
                    </SelectValue>
                  </SelectTrigger>
                  <SelectContent side="bottom" alignItemWithTrigger={false}>
                    {teams.filter(team => ['owner', 'admin', 'member'].includes(team.role)).length > 0 ? (
                      teams
                        .filter(team => ['owner', 'admin', 'member'].includes(team.role))
                        .map((team) => (
                          <SelectItem key={team.id} value={team.id}>
                            {team.name}
                          </SelectItem>
                        ))
                    ) : (
                      <SelectEmpty>{t('noTeams')}</SelectEmpty>
                    )}
                  </SelectContent>
                </Select>
                <p className="text-xs text-muted-foreground">{t('teamHint')}</p>
                {fieldErrors.team_id && (
                  <p className="text-sm text-destructive">{fieldErrors.team_id}</p>
                )}
              </div>
            )}
            
            {/* 描述 */}
            <div className="space-y-2">
              <Label htmlFor="description">{t('descriptionLabel')}</Label>
              <Textarea
                id="description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder={t('descriptionPlaceholder')}
                rows={3}
              />
              {fieldErrors.description && (
                <p className="text-sm text-destructive">{fieldErrors.description}</p>
              )}
            </div>
            
            {/* Embedding 模型 */}
            <div className="space-y-2">
              <Label htmlFor="embeddingModel">{t('embeddingModel')}</Label>
              <Select 
                value={embeddingModelId} 
                onValueChange={(v) => v && setEmbeddingModelId(v)}
                disabled={isEditing}
              >
                <SelectTrigger id="embeddingModel" className="w-full">
                  <SelectValue>
                    {selectedModelName || t('selectEmbeddingModel')}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent side="bottom" alignItemWithTrigger={false}>
                  {embeddingModels.length > 0 ? (
                    embeddingModels.map((model) => (
                      <SelectItem key={model.id} value={model.id}>
                        {model.name}
                      </SelectItem>
                    ))
                  ) : (
                    <SelectEmpty>{t('noEmbeddingModels')}</SelectEmpty>
                  )}
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">
                {isEditing ? t('embeddingModelCannotChange') : t('embeddingModelHint')}
              </p>
              {fieldErrors.embedding_model_id && (
                <p className="text-sm text-destructive">{fieldErrors.embedding_model_id}</p>
              )}
            </div>
            
            {/* 分块设置 */}
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="chunkSize">{t('chunkSize')}</Label>
                <Input
                  id="chunkSize"
                  type="number"
                  value={chunkSize}
                  onChange={(e) => setChunkSize(Number(e.target.value))}
                  min={100}
                  max={2000}
                />
                <p className="text-xs text-muted-foreground">{t('chunkSizeHint')}</p>
                {fieldErrors.chunk_size && (
                  <p className="text-sm text-destructive">{fieldErrors.chunk_size}</p>
                )}
              </div>
              
              <div className="space-y-2">
                <Label htmlFor="chunkOverlap">{t('chunkOverlap')}</Label>
                <Input
                  id="chunkOverlap"
                  type="number"
                  value={chunkOverlap}
                  onChange={(e) => setChunkOverlap(Number(e.target.value))}
                  min={0}
                  max={500}
                />
                <p className="text-xs text-muted-foreground">{t('chunkOverlapHint')}</p>
                {fieldErrors.chunk_overlap && (
                  <p className="text-sm text-destructive">{fieldErrors.chunk_overlap}</p>
                )}
              </div>
            </div>
            
            {/* 自定义分隔符 */}
            <div className="space-y-2">
              <Label htmlFor="separator">{t('separator')}</Label>
              <Input
                id="separator"
                value={separator}
                onChange={(e) => setSeparator(e.target.value)}
                placeholder={t('separatorPlaceholder')}
              />
              <p className="text-xs text-muted-foreground">{t('separatorHint')}</p>
              {fieldErrors.separator && (
                <p className="text-sm text-destructive">{fieldErrors.separator}</p>
              )}
            </div>
            
            {/* 状态切换 - 仅编辑时显示 */}
            {isEditing && (
              <div className="flex items-center justify-between rounded-lg border p-3">
                <div className="space-y-0.5">
                  <Label htmlFor="status">{t('enableKb')}</Label>
                  <p className="text-xs text-muted-foreground">{t('enableKbHint')}</p>
                </div>
                <Switch
                  id="status"
                  checked={isActive}
                  onCheckedChange={setIsActive}
                />
              </div>
            )}
          </div>
          
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              {commonT('cancel')}
            </Button>
            <Button type="submit" disabled={isLoading}>
              {isLoading ? commonT('loading') : (isEditing ? commonT('save') : commonT('create'))}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
