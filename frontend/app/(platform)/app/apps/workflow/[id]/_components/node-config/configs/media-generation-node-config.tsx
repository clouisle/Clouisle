'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { ChevronDown, Image as ImageIcon, Loader2, Search, Video } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { ScrollArea } from '@/components/ui/scroll-area'
import { cn } from '@/lib/utils'
import { useTeam } from '@/contexts/team-context'
import { teamModelsApi, type TeamModel } from '@/lib/api'
import { isValidVariableName } from '../utils'
import { VariableSelector } from '../variable-selector'
import { PromptTextarea } from '../components/prompt-textarea'
import type { AvailableVariable } from '../types'
import {
  defaultMediaGenerationConfig,
  type MediaGenerationConfig,
  type MediaGenerationMode,
} from '../../nodes/media-generation-node'

interface MediaGenerationNodeConfigProps {
  config?: MediaGenerationConfig
  onChange?: (config: MediaGenerationConfig) => void
  getAvailableVariables?: (filterType?: 'iterable' | 'all') => AvailableVariable[]
}

export function MediaGenerationNodeConfig({
  config = defaultMediaGenerationConfig,
  onChange,
  getAvailableVariables,
}: MediaGenerationNodeConfigProps) {
  const t = useTranslations('workflow')
  const { currentTeam } = useTeam()
  const [teamModels, setTeamModels] = React.useState<TeamModel[]>([])
  const [isLoadingModels, setIsLoadingModels] = React.useState(false)
  const [modelSearch, setModelSearch] = React.useState('')
  const [modelSelectorOpen, setModelSelectorOpen] = React.useState(false)
  const [imageVarSelectorOpen, setImageVarSelectorOpen] = React.useState(false)

  const safeConfig: MediaGenerationConfig = {
    ...defaultMediaGenerationConfig,
    ...config,
  }

  React.useEffect(() => {
    let cancelled = false
    const loadModels = async () => {
      if (!currentTeam) return

      setIsLoadingModels(true)
      try {
        const modelType = safeConfig.mode === 'image' ? 'text_to_image' : 'text_to_video'
        const models = await teamModelsApi.getTeamModels(currentTeam.id, modelType)
        if (!cancelled) setTeamModels(models.filter(m => m.is_enabled))
      } catch {
        if (!cancelled) setTeamModels([])
      } finally {
        if (!cancelled) setIsLoadingModels(false)
      }
    }
    loadModels()
    return () => {
      cancelled = true
    }
  }, [currentTeam, safeConfig.mode])

  const selectedModel = React.useMemo(() => {
    if (!safeConfig.modelId) return null
    return teamModels.find(m => m.id === safeConfig.modelId)
  }, [safeConfig.modelId, teamModels])

  const filteredModels = React.useMemo(() => {
    if (!modelSearch) return teamModels
    const query = modelSearch.toLowerCase()
    return teamModels.filter(m =>
      m.model.name.toLowerCase().includes(query) ||
      m.model.provider.toLowerCase().includes(query) ||
      m.model.model_id.toLowerCase().includes(query)
    )
  }, [teamModels, modelSearch])

  const groupedModels = React.useMemo(() => {
    const groups: Record<string, TeamModel[]> = {}
    filteredModels.forEach(m => {
      const provider = m.model.provider
      if (!groups[provider]) groups[provider] = []
      groups[provider].push(m)
    })
    return groups
  }, [filteredModels])

  const imageVariables = React.useMemo(() => {
    if (!getAvailableVariables) return []
    return getAvailableVariables('all').filter(v =>
      v.type === 'Image' || v.type === 'File' || v.isFile || v.type === 'Array' || v.type === 'Object'
    )
  }, [getAvailableVariables])

  const handleChange = (updates: Partial<MediaGenerationConfig>) => {
    onChange?.({ ...safeConfig, ...updates })
  }

  const handleModeChange = (mode: MediaGenerationMode) => {
    onChange?.({
      ...safeConfig,
      mode,
      modelId: undefined,
      modelName: undefined,
      referenceImageVariable: mode === 'image' ? safeConfig.referenceImageVariable : undefined,
      startImageVariable: mode === 'video' ? safeConfig.startImageVariable : undefined,
    })
  }

  const imageVariable = safeConfig.mode === 'image'
    ? safeConfig.referenceImageVariable
    : safeConfig.startImageVariable

  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <Label className="text-xs font-medium">{t('configMediaGeneration.mode')}</Label>
        <div className="grid grid-cols-2 gap-2">
          <Button
            variant={safeConfig.mode === 'image' ? 'default' : 'outline'}
            size="sm"
            className="h-8 text-xs"
            onClick={() => handleModeChange('image')}
          >
            <ImageIcon className="h-3.5 w-3.5 mr-1" />
            {t('configMediaGeneration.imageMode')}
          </Button>
          <Button
            variant={safeConfig.mode === 'video' ? 'default' : 'outline'}
            size="sm"
            className="h-8 text-xs"
            onClick={() => handleModeChange('video')}
          >
            <Video className="h-3.5 w-3.5 mr-1" />
            {t('configMediaGeneration.videoMode')}
          </Button>
        </div>
      </div>

      <div className="space-y-2">
        <div className="flex items-center gap-1">
          <Label className="text-xs font-medium">{t('configCommon.model')}</Label>
          <span className="text-destructive">*</span>
        </div>
        <Popover open={modelSelectorOpen} onOpenChange={setModelSelectorOpen}>
          <PopoverTrigger className="w-full">
            <div className={cn(
              'flex items-center justify-between w-full h-9 px-3 rounded-md border bg-background text-sm cursor-pointer hover:bg-muted/50 transition-colors',
              !safeConfig.modelId && 'text-muted-foreground'
            )}>
              <span className="truncate">
                {selectedModel ? selectedModel.model.name : t('configCommon.selectModel')}
              </span>
              <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" />
            </div>
          </PopoverTrigger>
          <PopoverContent className="w-80 p-0" align="start">
            <div className="p-2 border-b">
              <div className="relative">
                <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
                <Input
                  placeholder={t('configCommon.searchModel')}
                  value={modelSearch}
                  onChange={(e) => setModelSearch(e.target.value)}
                  className="h-8 pl-8 text-xs"
                />
              </div>
            </div>
            <ScrollArea className="h-64">
              {isLoadingModels ? (
                <div className="flex items-center justify-center py-8">
                  <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                </div>
              ) : Object.keys(groupedModels).length === 0 ? (
                <div className="py-8 text-center text-muted-foreground text-xs">
                  {teamModels.length === 0 ? t('configCommon.noAvailableModels') : t('configCommon.noMatchingModels')}
                </div>
              ) : (
                <div className="p-1">
                  {Object.entries(groupedModels).map(([provider, models]) => (
                    <div key={provider} className="mb-2">
                      <div className="px-2 py-1 text-xs text-muted-foreground font-medium uppercase">
                        {provider}
                      </div>
                      {models.map(tm => (
                        <button
                          key={tm.id}
                          className={cn(
                            'w-full flex items-center gap-2 px-2 py-2 text-left hover:bg-muted rounded-md transition-colors',
                            safeConfig.modelId === tm.id && 'bg-muted'
                          )}
                          onClick={() => {
                            handleChange({ modelId: tm.id, modelName: tm.model.name })
                            setModelSelectorOpen(false)
                            setModelSearch('')
                          }}
                        >
                          <div className="flex-1 min-w-0">
                            <div className="text-sm font-medium truncate">{tm.model.name}</div>
                            <div className="text-xs text-muted-foreground truncate">{tm.model.model_id}</div>
                          </div>
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
        <div className="flex items-center gap-1">
          <Label className="text-xs font-medium">{t('configMediaGeneration.prompt')}</Label>
          <span className="text-destructive">*</span>
        </div>
        <PromptTextarea
          value={safeConfig.prompt || ''}
          onChange={(value) => handleChange({ prompt: value })}
          variables={getAvailableVariables?.('all') || []}
          placeholder={t('configMediaGeneration.promptPlaceholder')}
          minHeight="min-h-24"
        />
      </div>

      <div className="space-y-2">
        <Label className="text-xs font-medium">
          {safeConfig.mode === 'image'
            ? t('configMediaGeneration.referenceImage')
            : t('configMediaGeneration.startImage')}
        </Label>
        {imageVariables.length > 0 ? (
          <VariableSelector
            open={imageVarSelectorOpen}
            onOpenChange={setImageVarSelectorOpen}
            variables={imageVariables}
            selectedValue={imageVariable}
            placeholder={t('configMediaGeneration.selectImageVariable')}
            onSelect={(variable) => {
              const value = `{{${variable.id}}}`
              if (safeConfig.mode === 'image') {
                handleChange({ referenceImageVariable: value })
              } else {
                handleChange({ startImageVariable: value })
              }
            }}
          />
        ) : (
          <div className="text-xs text-muted-foreground bg-muted rounded-md p-3">
            {t('configMediaGeneration.noImageVariables')}
          </div>
        )}
      </div>

      {safeConfig.mode === 'image' ? (
        <div className="grid grid-cols-3 gap-2">
          <div className="space-y-2">
            <Label className="text-xs">{t('configMediaGeneration.width')}</Label>
            <Input
              type="number"
              value={safeConfig.width || ''}
              onChange={(e) => handleChange({ width: e.target.value ? Number(e.target.value) : undefined })}
              className="h-8 text-xs"
            />
          </div>
          <div className="space-y-2">
            <Label className="text-xs">{t('configMediaGeneration.height')}</Label>
            <Input
              type="number"
              value={safeConfig.height || ''}
              onChange={(e) => handleChange({ height: e.target.value ? Number(e.target.value) : undefined })}
              className="h-8 text-xs"
            />
          </div>
          <div className="space-y-2">
            <Label className="text-xs">{t('configMediaGeneration.numImages')}</Label>
            <Input
              type="number"
              min={1}
              max={4}
              value={safeConfig.numImages || 1}
              onChange={(e) => handleChange({ numImages: Number(e.target.value) || 1 })}
              className="h-8 text-xs"
            />
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-2">
          <div className="space-y-2">
            <Label className="text-xs">{t('configMediaGeneration.duration')}</Label>
            <Input
              type="number"
              min={1}
              max={30}
              value={safeConfig.duration || 5}
              onChange={(e) => handleChange({ duration: Number(e.target.value) || 5 })}
              className="h-8 text-xs"
            />
          </div>
          <div className="space-y-2">
            <Label className="text-xs">{t('configMediaGeneration.aspectRatio')}</Label>
            <Select
              value={safeConfig.aspectRatio || '16:9'}
              onValueChange={(value) => handleChange({ aspectRatio: value ?? undefined })}
            >
              <SelectTrigger size="sm" className="text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {['16:9', '9:16', '1:1', '4:3', '3:4'].map(value => (
                  <SelectItem key={value} value={value} className="text-xs">{value}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
      )}

      <div className="space-y-2">
        <div className="flex items-center gap-1">
          <Label className="text-xs font-medium">{t('configCommon.outputVariable')}</Label>
          <span className="text-destructive">*</span>
        </div>
        <Input
          value={safeConfig.outputVariable || 'result'}
          onChange={(e) => handleChange({ outputVariable: e.target.value })}
          placeholder="result"
          className={cn(
            'h-9 text-xs font-mono',
            safeConfig.outputVariable && !isValidVariableName(safeConfig.outputVariable) && 'border-destructive!'
          )}
        />
        {safeConfig.outputVariable && !isValidVariableName(safeConfig.outputVariable) && (
          <p className="text-[10px] text-destructive">{t('configCommon.invalidVariableName')}</p>
        )}
      </div>
    </div>
  )
}

export { defaultMediaGenerationConfig }
export type { MediaGenerationConfig }
