'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { toast } from 'sonner'
import { knowledgeBasesApi, modelsApi, teamsApi, type KnowledgeBase, type KnowledgeBaseCreateInput, type ModelBrief, type UserTeamInfo } from '@/lib/api'
import { clearValidationError, getValidationSummaryEntries, mapValidationErrors, normalizeValidationErrors,
  formatValidationSummaryMessage
} from '@/lib/validation'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { NumberInput } from '@/components/ui/number-input'
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
import { FieldError } from '@/components/ui/field'

interface KnowledgeBaseDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  knowledgeBase: KnowledgeBase | null
  onSuccess: () => void
}

const KB_ERROR_PATH_MAP = {
  team_id: 'team_id',
  embedding_model_id: 'embedding_model_id',
  rerank_model_id: 'rerank_model_id',
  'settings.chunk_size': 'chunk_size',
  'settings.chunk_overlap': 'chunk_overlap',
  'settings.separator': 'separator',
  'settings.rerank_candidate_k': 'rerank_candidate_k',
  'settings.rerank_score_threshold': 'rerank_score_threshold',
} as const

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
  const [rerankModelId, setRerankModelId] = React.useState<string | null>(null)
  const [chunkSize, setChunkSize] = React.useState<number | ''>(1000)
  const [chunkOverlap, setChunkOverlap] = React.useState<number | ''>(100)
  const [separator, setSeparator] = React.useState<string>('')
  const [rerankEnabled, setRerankEnabled] = React.useState(true)
  const [rerankCandidateK, setRerankCandidateK] = React.useState<number | ''>(10)
  const [rerankFailOpen, setRerankFailOpen] = React.useState(true)
  const [rerankScoreThreshold, setRerankScoreThreshold] = React.useState('')
  const [isActive, setIsActive] = React.useState(true)
  const [isLoading, setIsLoading] = React.useState(false)
  const [fieldErrors, setFieldErrors] = React.useState<Record<string, string>>({})
  
  // 模型列表和团队列表
  const [embeddingModels, setEmbeddingModels] = React.useState<ModelBrief[]>([])
  const [rerankModels, setRerankModels] = React.useState<ModelBrief[]>([])
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

  const selectedRerankModelName = React.useMemo(() => {
    if (!rerankModelId) return null
    const model = rerankModels.find(m => m.id === rerankModelId)
    if (model) return model.name
    if (knowledgeBase?.rerank_model?.name) {
      return knowledgeBase.rerank_model.name
    }
    return null
  }, [rerankModelId, rerankModels, knowledgeBase])
  
  // 加载数据
  React.useEffect(() => {
    const loadData = async () => {
      try {
        const [models, availableRerankModels, userTeams] = await Promise.all([
          modelsApi.getAvailableModels('embedding'),
          modelsApi.getAvailableModels('rerank'),
          teamsApi.getMyTeams(),
        ])
        setEmbeddingModels(models)
        setRerankModels(availableRerankModels)
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
        // 编辑时不需要重新选择团队
      } else {
        setName('')
        setDescription('')
        setEmbeddingModelId('')
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
        rerank_model_id: rerankModelId || null,
        settings: {
          chunk_size: chunkSize === '' ? undefined : chunkSize,
        chunk_overlap: chunkOverlap === '' ? undefined : chunkOverlap,
          separator: separator.trim() || null,
          rerank_enabled: rerankEnabled,
          rerank_candidate_k: rerankCandidateK === '' ? undefined : rerankCandidateK,
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
        await knowledgeBasesApi.createKnowledgeBase({ ...data, team_id: teamId! })
        toast.success(t('kbCreated'))
      }
      
      onOpenChange(false)
      onSuccess()
    } catch (error) {
      const errors = mapValidationErrors(normalizeValidationErrors(error), KB_ERROR_PATH_MAP)
      if (Object.keys(errors).length > 0) {
        setFieldErrors(errors)
      }
      // 其他错误已由 API 客户端处理
    } finally {
      setIsLoading(false)
    }
  }
  
  const summaryEntries = React.useMemo(
    () => getValidationSummaryEntries(fieldErrors, [
      'name',
      'team_id',
      'description',
      'embedding_model_id',
      'rerank_model_id',
      'chunk_size',
      'chunk_overlap',
      'separator',
      'rerank_candidate_k',
      'rerank_score_threshold',
    ]),
    [fieldErrors]
  )

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
            {summaryEntries.length > 0 && (
              <div className="rounded-md border border-destructive/30 bg-destructive/5 p-3 space-y-1">
                {summaryEntries.map(([field, message]) => (
                  <FieldError key={field}>
                    {formatValidationSummaryMessage(field, message)}
                  </FieldError>
                ))}
              </div>
            )}
            {/* 名称 */}
            <div className="space-y-2">
              <Label htmlFor="name">{t('name')}</Label>
              <Input
                id="name"
                value={name}
                onChange={(e) => {
                  setName(e.target.value)
                  setFieldErrors((prev) => clearValidationError(prev, 'name'))
                }}
                placeholder={t('namePlaceholder')}
                aria-invalid={!!fieldErrors.name}
              />
              <FieldError>{fieldErrors.name}</FieldError>
            </div>
            
            {/* 团队选择 - 仅创建时显示 */}
            {!isEditing && (
              <div className="space-y-2">
                <Label htmlFor="team">{t('team')}</Label>
                <Select value={teamId} onValueChange={(v) => {
                  if (v) {
                    setTeamId(v)
                    setFieldErrors((prev) => clearValidationError(prev, 'team_id'))
                  }
                }}>
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
                <FieldError>{fieldErrors.team_id}</FieldError>
              </div>
            )}
            
            {/* 描述 */}
            <div className="space-y-2">
              <Label htmlFor="description">{t('descriptionLabel')}</Label>
              <Textarea
                id="description"
                value={description}
                onChange={(e) => {
                  setDescription(e.target.value)
                  setFieldErrors((prev) => clearValidationError(prev, 'description'))
                }}
                placeholder={t('descriptionPlaceholder')}
                rows={3}
                aria-invalid={!!fieldErrors.description}
              />
              <FieldError>{fieldErrors.description}</FieldError>
            </div>
            
            {/* Embedding 模型 */}
            <div className="space-y-2">
              <Label htmlFor="embeddingModel">{t('embeddingModel')}</Label>
              <Select
                value={embeddingModelId}
                onValueChange={(v) => {
                  if (v) {
                    setEmbeddingModelId(v)
                    setFieldErrors((prev) => clearValidationError(prev, 'embedding_model_id'))
                  }
                }}
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
              <FieldError>{fieldErrors.embedding_model_id}</FieldError>
            </div>

            <div className="space-y-2">
              <Label htmlFor="rerankModel">{t('rerankModel')}</Label>
              <Select
                value={rerankModelId || '__none__'}
                onValueChange={(v) => {
                  setRerankModelId(v === '__none__' ? null : v)
                  setFieldErrors((prev) => clearValidationError(prev, 'rerank_model_id'))
                }}
              >
                <SelectTrigger id="rerankModel" className="w-full">
                  <SelectValue>
                    {selectedRerankModelName || t('selectRerankModel')}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent side="bottom" alignItemWithTrigger={false}>
                  <SelectItem value="__none__">{t('noRerankModel')}</SelectItem>
                  {rerankModels.length > 0 ? (
                    rerankModels.map((model) => (
                      <SelectItem key={model.id} value={model.id}>
                        {model.name}
                      </SelectItem>
                    ))
                  ) : (
                    <SelectEmpty>{t('noRerankModels')}</SelectEmpty>
                  )}
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">{t('rerankModelHint')}</p>
              <FieldError>{fieldErrors.rerank_model_id}</FieldError>
            </div>
            
            {/* 分块设置 */}
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="chunkSize">{t('chunkSize')}</Label>
                <NumberInput
                  value={chunkSize}
                  onChange={(value) => {
                    setChunkSize(value)
                    setFieldErrors((prev) => clearValidationError(prev, 'chunk_size'))
                  }}
                  min={100}
                  max={2000}
                  aria-invalid={!!fieldErrors.chunk_size}
                />
                <p className="text-xs text-muted-foreground">{t('chunkSizeHint')}</p>
                <FieldError>{fieldErrors.chunk_size}</FieldError>
              </div>
              
              <div className="space-y-2">
                <Label htmlFor="chunkOverlap">{t('chunkOverlap')}</Label>
                <NumberInput
                  value={chunkOverlap}
                  onChange={(value) => {
                    setChunkOverlap(value)
                    setFieldErrors((prev) => clearValidationError(prev, 'chunk_overlap'))
                  }}
                  min={0}
                  max={500}
                  aria-invalid={!!fieldErrors.chunk_overlap}
                />
                <p className="text-xs text-muted-foreground">{t('chunkOverlapHint')}</p>
                <FieldError>{fieldErrors.chunk_overlap}</FieldError>
              </div>
            </div>
            
            {/* 自定义分隔符 */}
            <div className="space-y-2">
              <Label htmlFor="separator">{t('separator')}</Label>
              <Input
                id="separator"
                value={separator}
                onChange={(e) => {
                  setSeparator(e.target.value)
                  setFieldErrors((prev) => clearValidationError(prev, 'separator'))
                }}
                placeholder={t('separatorPlaceholder')}
                aria-invalid={!!fieldErrors.separator}
              />
              <p className="text-xs text-muted-foreground">{t('separatorHint')}</p>
              <FieldError>{fieldErrors.separator}</FieldError>
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
                  <NumberInput
                    value={rerankCandidateK}
                    onChange={(value) => {
                      setRerankCandidateK(value)
                      setFieldErrors((prev) => clearValidationError(prev, 'rerank_candidate_k'))
                    }}
                    min={1}
                    max={100}
                    aria-invalid={!!fieldErrors.rerank_candidate_k}
                  />
                  <p className="text-xs text-muted-foreground">{t('rerankCandidateKHint')}</p>
                  <FieldError>{fieldErrors.rerank_candidate_k}</FieldError>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="rerankScoreThreshold">{t('rerankScoreThreshold')}</Label>
                  <Input
                    id="rerankScoreThreshold"
                    step="0.01"
                    min={0}
                    max={1}
                    value={rerankScoreThreshold}
                    onChange={(e) => {
                      setRerankScoreThreshold(e.target.value)
                      setFieldErrors((prev) => clearValidationError(prev, 'rerank_score_threshold'))
                    }}
                    placeholder={t('rerankScoreThresholdPlaceholder')}
                    aria-invalid={!!fieldErrors.rerank_score_threshold}
                  />
                  <p className="text-xs text-muted-foreground">{t('rerankScoreThresholdHint')}</p>
                  <FieldError>{fieldErrors.rerank_score_threshold}</FieldError>
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
