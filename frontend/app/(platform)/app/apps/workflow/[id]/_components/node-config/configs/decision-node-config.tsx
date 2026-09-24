'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { ChevronDown, Loader2, Plus, Search, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { ScrollArea } from '@/components/ui/scroll-area'
import { cn } from '@/lib/utils'
import { useTeam } from '@/contexts/team-context'
import { teamModelsApi, type TeamModel } from '@/lib/api'
import { defaultDecisionNodeConfig, type DecisionNodeConfig, type DecisionQuestionType } from '../../nodes/decision-node'
import type { AvailableVariable } from '../types'
import { PromptTextarea } from '../components/prompt-textarea'

interface Props {
  config: DecisionNodeConfig
  variables: AvailableVariable[]
  onConfigChange: (config: DecisionNodeConfig) => void
}

export function DecisionNodeConfig({ config, variables, onConfigChange }: Props) {
  const t = useTranslations('workflow')
  const { currentTeam } = useTeam()
  const [models, setModels] = React.useState<TeamModel[]>([])
  const [isLoadingModels, setIsLoadingModels] = React.useState(false)
  const [modelSelectorOpen, setModelSelectorOpen] = React.useState(false)
  const [modelSearch, setModelSearch] = React.useState('')
  const safe = { ...defaultDecisionNodeConfig, ...config, options: config.options || [] }

  React.useEffect(() => {
    if (!currentTeam) {
      setModels([])
      return
    }
    let cancelled = false
    setIsLoadingModels(true)
    teamModelsApi.getTeamModels(currentTeam.id, 'decision')
      .then((items) => {
        if (!cancelled) setModels(items.filter((item) => item.is_enabled))
      })
      .catch(() => {
        if (!cancelled) setModels([])
      })
      .finally(() => {
        if (!cancelled) setIsLoadingModels(false)
      })
    return () => { cancelled = true }
  }, [currentTeam])

  const update = (patch: Partial<DecisionNodeConfig>) => onConfigChange({ ...safe, ...patch })
  const stateOptions = variables.filter((variable) => variable.type === 'String' || variable.type === 'string')
  const selectedModel = models.find((model) => model.model_id === safe.modelId)
  const selectedModelLabel = selectedModel
    ? `${selectedModel.model.provider_display_name || selectedModel.model.provider} · ${selectedModel.model.name}`
    : safe.modelName || t('decisionConfig.selectModel')
  const filteredModels = models.filter((model) => {
    const query = modelSearch.trim().toLowerCase()
    return !query || [model.model.name, model.model.model_id, model.model.provider_display_name, model.model.provider]
      .some((value) => value?.toLowerCase().includes(query))
  })
  const groupedModels = React.useMemo(() => {
    const groups: Record<string, TeamModel[]> = {}
    filteredModels.forEach((model) => {
      const provider = model.model.provider_display_name || model.model.provider
      if (!groups[provider]) groups[provider] = []
      groups[provider].push(model)
    })
    return groups
  }, [filteredModels])

  const maxOptions = safe.questionType === 'score' ? 10 : 255
  const atOptionLimit = safe.options.length >= maxOptions

  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <div className="flex items-center gap-1">
          <Label className="text-xs font-medium">{t('decisionConfig.model')}</Label>
          <span className="text-destructive">*</span>
        </div>
        <Popover open={modelSelectorOpen} onOpenChange={setModelSelectorOpen}>
          <PopoverTrigger className="w-full">
            <div className={cn(
              'flex h-9 w-full cursor-pointer items-center justify-between rounded-md border bg-background px-3 text-sm transition-colors hover:bg-muted/50',
              !safe.modelId && 'text-muted-foreground'
            )}>
              <span className="truncate">{isLoadingModels ? t('configCommon.loading') : selectedModelLabel}</span>
              {isLoadingModels ? <Loader2 className="h-4 w-4 shrink-0 animate-spin text-muted-foreground" /> : <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" />}
            </div>
          </PopoverTrigger>
          <PopoverContent className="w-80 p-0" align="start">
            <div className="border-b p-2">
              <div className="relative">
                <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
                <Input
                  placeholder={t('configCommon.searchModel')}
                  value={modelSearch}
                  onChange={(event) => setModelSearch(event.target.value)}
                  className="h-8 pl-8 text-xs"
                />
              </div>
            </div>
            <ScrollArea className="h-64">
              {isLoadingModels ? (
                <div className="flex items-center justify-center py-8"><Loader2 className="h-5 w-5 animate-spin text-muted-foreground" /></div>
              ) : Object.keys(groupedModels).length === 0 ? (
                <div className="py-8 text-center text-xs text-muted-foreground">
                  {models.length === 0 ? t('configCommon.noAvailableModels') : t('configCommon.noMatchingModels')}
                </div>
              ) : (
                <div className="p-1">
                  {Object.entries(groupedModels).map(([provider, providerModels]) => (
                    <div key={provider} className="mb-2">
                      <div className="px-2 py-1 text-xs font-medium uppercase text-muted-foreground">{provider}</div>
                      {providerModels.map((model) => (
                        <button
                          key={model.id}
                          type="button"
                          className={cn('w-full rounded-md px-2 py-2 text-left transition-colors hover:bg-muted', safe.modelId === model.model_id && 'bg-muted')}
                          onClick={() => {
                            update({ modelId: model.model_id, modelName: model.model.name })
                            setModelSelectorOpen(false)
                            setModelSearch('')
                          }}
                        >
                          <span className="block truncate text-sm font-medium">{model.model.name}</span>
                          <span className="block truncate text-xs text-muted-foreground">{model.model.model_id}</span>
                        </button>
                      ))}
                    </div>
                  ))}
                </div>
              )}
            </ScrollArea>
          </PopoverContent>
        </Popover>
      </div>
      <div className="space-y-2">
        <Label>{t('decisionConfig.state')}</Label>
        <PromptTextarea
          value={safe.stateTemplate}
          onChange={(value) => update({ stateTemplate: value })}
          variables={variables}
          placeholder="{{start.question}}"
          minHeight="min-h-9"
        />
        {stateOptions.length > 0 && <p className="text-xs text-muted-foreground">{t('decisionConfig.stateHint')}</p>}
      </div>
      <div className="space-y-2">
        <Label>{t('decisionConfig.type')}</Label>
        <Select value={safe.questionType} onValueChange={(value) => update({ questionType: value as DecisionQuestionType })}>
          <SelectTrigger className="w-full"><SelectValue>{t(safe.questionType === 'choice' ? 'decisionConfig.typeChoice' : safe.questionType === 'score' ? 'decisionConfig.typeScore' : 'decisionConfig.typeNoul')}</SelectValue></SelectTrigger>
          <SelectContent>
            <SelectItem value="choice">{t('decisionConfig.typeChoice')}</SelectItem>
            <SelectItem value="score">{t('decisionConfig.typeScore')}</SelectItem>
            <SelectItem value="noul">{t('decisionConfig.typeNoul')}</SelectItem>
          </SelectContent>
        </Select>
        {safe.questionType === 'noul' && <p className="text-xs text-muted-foreground">{t('decisionConfig.noulHint')}</p>}
      </div>
      <div className="space-y-2"><Label>{t('decisionConfig.instructions')}</Label><Textarea value={safe.instructions} onChange={(event) => update({ instructions: event.target.value })} placeholder={t('decisionConfig.instructionsPlaceholder')} /></div>
      {(safe.questionType === 'choice' || safe.questionType === 'score') && <div className="space-y-2">
        <Label>{t(safe.questionType === 'score' ? 'decisionConfig.levels' : 'decisionConfig.options')}</Label>
        {safe.questionType === 'score' && <p className="text-xs text-muted-foreground">{t('decisionConfig.scoreHint')}</p>}
        {safe.options.map((option, index) => <div className="flex gap-2" key={`${index}-${option}`}><Input value={option} onChange={(event) => update({ options: safe.options.map((item, itemIndex) => itemIndex === index ? event.target.value : item) })} /><Button type="button" variant="ghost" size="icon" onClick={() => update({ options: safe.options.filter((_, itemIndex) => itemIndex !== index) })}><Trash2 className="h-4 w-4" /></Button></div>)}
        <Button type="button" variant="outline" size="sm" disabled={atOptionLimit} onClick={() => update({ options: [...safe.options, `option_${safe.options.length + 1}`] })}><Plus className="mr-1 h-4 w-4" />{t('decisionConfig.addOption')}</Button>
        {atOptionLimit && <p className="text-xs text-muted-foreground">{t('decisionConfig.optionLimit', { max: maxOptions })}</p>}
      </div>}
      <div className="space-y-2"><Label>{t('decisionConfig.defaultHandle')}</Label><Input value={safe.defaultHandle || ''} onChange={(event) => update({ defaultHandle: event.target.value })} /></div>
      {safe.questionType !== 'noul' && <div className="space-y-2"><Label>{t('decisionConfig.confidenceThreshold')}</Label><Input type="number" min="0" max="1" step="0.01" value={safe.confidenceThreshold ?? ''} onChange={(event) => update({ confidenceThreshold: event.target.value === '' ? undefined : Number(event.target.value) })} /></div>}
    </div>
  )
}
