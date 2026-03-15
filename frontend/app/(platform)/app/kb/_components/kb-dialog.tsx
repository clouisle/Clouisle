'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { toast } from 'sonner'
import { useTeam } from '@/contexts/team-context'
import { 
  knowledgeBasesApi, 
  teamModelsApi, 
  type KnowledgeBase, 
  type KnowledgeBaseCreateInput, 
  type TeamModel, 
  ApiError 
} from '@/lib/api'
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
  const { currentTeam } = useTeam()
  
  const isEditing = !!knowledgeBase
  
  // 表单状态
  const [name, setName] = React.useState('')
  const [description, setDescription] = React.useState('')
  const [embeddingModelId, setEmbeddingModelId] = React.useState<string | null>(null)
  const [rerankModelId, setRerankModelId] = React.useState<string | null>(null)
  const [chunkSize, setChunkSize] = React.useState(1000)
  const [chunkOverlap, setChunkOverlap] = React.useState(100)
  const [separator, setSeparator] = React.useState<string>('')
  const [rerankEnabled, setRerankEnabled] = React.useState(true)
  const [rerankCandidateK, setRerankCandidateK] = React.useState(10)
  const [rerankFailOpen, setRerankFailOpen] = React.useState(true)
  const [rerankScoreThreshold, setRerankScoreThreshold] = React.useState('')
  const [isActive, setIsActive] = React.useState(true)
  const [isLoading, setIsLoading] = React.useState(false)
  const [fieldErrors, setFieldErrors] = React.useState<Record<string, string>>({})
  
  // 团队已授权的嵌入模型列表
  const [teamEmbeddingModels, setTeamEmbeddingModels] = React.useState<TeamModel[]>([])
  const [teamRerankModels, setTeamRerankModels] = React.useState<TeamModel[]>([])
  const [isLoadingModels, setIsLoadingModels] = React.useState(false)
  
  // 加载团队已授权的嵌入模型
  React.useEffect(() => {
    const loadModels = async () => {
      if (!currentTeam) return
      setIsLoadingModels(true)
      try {
        const [embeddingModels, rerankModels] = await Promise.all([
          teamModelsApi.getTeamModels(currentTeam.id, 'embedding'),
          teamModelsApi.getTeamModels(currentTeam.id, 'rerank'),
        ])
        setTeamEmbeddingModels(embeddingModels.filter(m => m.is_enabled))
        setTeamRerankModels(rerankModels.filter(m => m.is_enabled))
      } catch {
        // 忽略错误
      } finally {
        setIsLoadingModels(false)
      }
    }
    if (open) {
      loadModels()
    }
  }, [open, currentTeam])
  
  // 获取当前选中模型的名称
  const selectedModelName = React.useMemo(() => {
    if (!embeddingModelId) return null
    const tm = teamEmbeddingModels.find(m => m.model_id === embeddingModelId)
    if (tm) return tm.model.name
    // 编辑时，如果当前模型不在列表中，显示知识库中保存的模型信息
    if (knowledgeBase?.embedding_model?.name) {
      return knowledgeBase.embedding_model.name
    }
    return null
  }, [embeddingModelId, teamEmbeddingModels, knowledgeBase])

  const selectedRerankModelName = React.useMemo(() => {
    if (!rerankModelId) return null
    const tm = teamRerankModels.find(m => m.model_id === rerankModelId)
    if (tm) return tm.model.name
    if (knowledgeBase?.rerank_model?.name) {
      return knowledgeBase.rerank_model.name
    }
    return null
  }, [rerankModelId, teamRerankModels, knowledgeBase])
  
  // 初始化表单
  React.useEffect(() => {
    if (open) {
      if (knowledgeBase) {
        setName(knowledgeBase.name)
        setDescription(knowledgeBase.description || '')
        setEmbeddingModelId(knowledgeBase.embedding_model_id || null)
        setRerankModelId(knowledgeBase.rerank_model_id || null)
        setChunkSize(knowledgeBase.settings?.chunk_size ?? 1000)
        setChunkOverlap(knowledgeBase.settings?.chunk_overlap ?? 100)
        setSeparator(knowledgeBase.settings?.separator || '')
        setRerankEnabled(knowledgeBase.settings?.rerank_enabled ?? true)
        setRerankCandidateK(knowledgeBase.settings?.rerank_candidate_k ?? 10)
        setRerankFailOpen(knowledgeBase.settings?.rerank_fail_open ?? true)
        setRerankScoreThreshold(
          knowledgeBase.settings?.rerank_score_threshold?.toString() || ''
        )
        setIsActive(knowledgeBase.status === 'active')
      } else {
        setName('')
        setDescription('')
        setEmbeddingModelId(null)
        setRerankModelId(null)
        setChunkSize(1000)
        setChunkOverlap(100)
        setSeparator('')
        setRerankEnabled(true)
        setRerankCandidateK(10)
        setRerankFailOpen(true)
        setRerankScoreThreshold('')
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
    
    if (!isEditing && !currentTeam) {
      toast.error(t('teamRequired'))
      return
    }
    
    setIsLoading(true)
    setFieldErrors({})
    
    try {
      const data: KnowledgeBaseCreateInput = {
        name: name.trim(),
        description: description.trim() || null,
        embedding_model_id: embeddingModelId || null,
        rerank_model_id: rerankModelId || null,
        settings: {
          chunk_size: chunkSize,
          chunk_overlap: chunkOverlap,
          separator: separator.trim() || null,
          rerank_enabled: rerankEnabled,
          rerank_candidate_k: rerankCandidateK,
          rerank_fail_open: rerankFailOpen,
          rerank_score_threshold: rerankScoreThreshold
            ? parseFloat(rerankScoreThreshold)
            : null,
        },
      }
      
      if (isEditing) {
        await knowledgeBasesApi.updateKnowledgeBase(knowledgeBase!.id, {
          ...data,
          status: isActive ? 'active' : 'archived',
        })
        toast.success(t('kbUpdated'))
      } else {
        await knowledgeBasesApi.createKnowledgeBase({ ...data, team_id: currentTeam!.id })
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
      <DialogContent className="sm:max-w-125 max-h-[calc(100vh-2rem)] overflow-hidden p-0 gap-0">
        <form
          onSubmit={handleSubmit}
          className="flex max-h-[calc(100vh-2rem)] flex-col"
        >
          <DialogHeader className="px-6 pt-6">
            <DialogTitle>
              {isEditing ? t('editKb') : t('createKb')}
            </DialogTitle>
            <DialogDescription>
              {isEditing ? t('editKbDescription') : t('createKbDescription')}
            </DialogDescription>
          </DialogHeader>
          
          <div className="grid flex-1 gap-4 overflow-y-auto px-6 py-4">
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
                value={embeddingModelId ?? ''} 
                onValueChange={(value) => setEmbeddingModelId(value || null)}
                disabled={isLoadingModels || isEditing}
              >
                <SelectTrigger id="embeddingModel" className="w-full">
                  <SelectValue>
                    {selectedModelName || t('selectEmbeddingModel')}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent side="bottom" alignItemWithTrigger={false}>
                  {teamEmbeddingModels.length > 0 ? (
                    teamEmbeddingModels.map((tm) => (
                      <SelectItem key={tm.model_id} value={tm.model_id}>
                        {tm.model.name}
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

            <div className="space-y-2">
              <Label htmlFor="rerankModel">{t('rerankModel')}</Label>
              <Select
                value={rerankModelId ?? '__none__'}
                onValueChange={(value) => setRerankModelId(value === '__none__' ? null : value)}
                disabled={isLoadingModels}
              >
                <SelectTrigger id="rerankModel" className="w-full">
                  <SelectValue>
                    {selectedRerankModelName || t('selectRerankModel')}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent side="bottom" alignItemWithTrigger={false}>
                  <SelectItem value="__none__">{t('noRerankModel')}</SelectItem>
                  {teamRerankModels.length > 0 ? (
                    teamRerankModels.map((tm) => (
                      <SelectItem key={tm.model_id} value={tm.model_id}>
                        {tm.model.name}
                      </SelectItem>
                    ))
                  ) : (
                    <SelectEmpty>{t('noRerankModels')}</SelectEmpty>
                  )}
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">{t('rerankModelHint')}</p>
              {fieldErrors.rerank_model_id && (
                <p className="text-sm text-destructive">{fieldErrors.rerank_model_id}</p>
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

            <div className="rounded-lg border p-4 space-y-4">
              <div className="flex items-center justify-between">
                <div className="space-y-0.5">
                  <Label htmlFor="rerankEnabled">{t('rerankEnabled')}</Label>
                  <p className="text-xs text-muted-foreground">{t('rerankEnabledHint')}</p>
                </div>
                <Switch
                  id="rerankEnabled"
                  checked={rerankEnabled}
                  onCheckedChange={setRerankEnabled}
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="rerankCandidateK">{t('rerankCandidateK')}</Label>
                  <Input
                    id="rerankCandidateK"
                    type="number"
                    value={rerankCandidateK}
                    onChange={(e) => setRerankCandidateK(Number(e.target.value))}
                    min={1}
                    max={100}
                  />
                  <p className="text-xs text-muted-foreground">{t('rerankCandidateKHint')}</p>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="rerankScoreThreshold">{t('rerankScoreThreshold')}</Label>
                  <Input
                    id="rerankScoreThreshold"
                    type="number"
                    step="0.01"
                    min={0}
                    max={1}
                    value={rerankScoreThreshold}
                    onChange={(e) => setRerankScoreThreshold(e.target.value)}
                    placeholder={t('rerankScoreThresholdPlaceholder')}
                  />
                  <p className="text-xs text-muted-foreground">{t('rerankScoreThresholdHint')}</p>
                </div>
              </div>

              <div className="flex items-center justify-between rounded-lg border p-3">
                <div className="space-y-0.5">
                  <Label htmlFor="rerankFailOpen">{t('rerankFailOpen')}</Label>
                  <p className="text-xs text-muted-foreground">{t('rerankFailOpenHint')}</p>
                </div>
                <Switch
                  id="rerankFailOpen"
                  checked={rerankFailOpen}
                  onCheckedChange={setRerankFailOpen}
                />
              </div>
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
          
          <DialogFooter className="border-t px-6 py-4">
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
