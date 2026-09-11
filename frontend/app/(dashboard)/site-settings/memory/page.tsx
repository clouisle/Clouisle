'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { toast } from 'sonner'
import { Brain, Loader2 } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { NumberInput } from '@/components/ui/number-input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { siteSettingsApi, type MemorySiteSettings } from '@/lib/api/admin/site-settings'
import { modelsApi, type Model } from '@/lib/api/admin/models'
import { useCanPerform } from '@/components/permission-guard'
import { FieldError } from '@/components/ui/field'
import {
  clearValidationError,
  mapValidationErrors,
  normalizeValidationErrors,
} from '@/lib/validation'
const AUTO_MODEL_VALUE = '__auto__'

export default function SiteSettingsMemoryPage() {
  const t = useTranslations('siteSettings')
  const { canPerform } = useCanPerform()
  const canUpdateSettings = canPerform('admin:settings:update')

  const [loading, setLoading] = React.useState(true)
  const [settingsReady, setSettingsReady] = React.useState(false)
  const [modelsLoading, setModelsLoading] = React.useState(true)
  const [settingsLoadFailed, setSettingsLoadFailed] = React.useState(false)
  const [saving, setSaving] = React.useState(false)
  const [fieldErrors, setFieldErrors] = React.useState<Record<string, string>>({})
  const [chatModels, setChatModels] = React.useState<Model[]>([])
  const [settings, setSettings] = React.useState<MemorySiteSettings>({
    memory_async_extraction_enabled: false,
    memory_extraction_model_id: '',
    memory_extraction_cooldown_seconds: 180,
    memory_extraction_max_pending_turns: 6,
  })
  const selectedModel = chatModels.find(
    (model) =>
      model.id === settings.memory_extraction_model_id
      || model.model_id === settings.memory_extraction_model_id,
  )
  const selectedModelLabel = selectedModel
    ? `${selectedModel.provider_display_name?.trim() || selectedModel.provider} / ${selectedModel.name}`
    : t('memorySettings.modelAuto')


  const loadData = React.useCallback(async () => {
    setLoading(true)
    setSettingsReady(false)
    setSettingsLoadFailed(false)
    setModelsLoading(true)

    const [memoryResult, modelsResult] = await Promise.allSettled([
      siteSettingsApi.getMemory(),
      modelsApi.getModels({ model_type: ['chat'], is_enabled: true, pageSize: 100 }),
    ])

    if (memoryResult.status === 'fulfilled') {
      setSettings(memoryResult.value)
      setSettingsReady(true)
    } else {
      setSettingsLoadFailed(true)
      console.error('Failed to load memory settings:', memoryResult.reason)
    }

    if (modelsResult.status === 'fulfilled') {
      setChatModels(modelsResult.value.items || [])
    } else {
      console.error('Failed to load chat models:', modelsResult.reason)
    }

    setModelsLoading(false)
    setLoading(false)
  }, [])

  React.useEffect(() => {
    loadData()
  }, [loadData])

  const handleSave = async () => {
    if (!canUpdateSettings || !settingsReady) return
    setFieldErrors({})
    try {
      setSaving(true)
      await siteSettingsApi.updateMemory({
        memory_async_extraction_enabled: settings.memory_async_extraction_enabled,
        memory_extraction_model_id: settings.memory_extraction_model_id,
        memory_extraction_cooldown_seconds: settings.memory_extraction_cooldown_seconds || 180,
        memory_extraction_max_pending_turns: settings.memory_extraction_max_pending_turns || 6,
      })
      toast.success(t('saveSuccess'))
    } catch (error: unknown) {
      const errors = mapValidationErrors(normalizeValidationErrors(error), {
        memory_async_extraction_enabled: 'memory_async_extraction_enabled',
        memory_extraction_model_id: 'memory_extraction_model_id',
        memory_extraction_cooldown_seconds: 'memory_extraction_cooldown_seconds',
        memory_extraction_max_pending_turns: 'memory_extraction_max_pending_turns',
        'settings.memory_async_extraction_enabled': 'memory_async_extraction_enabled',
        'settings.memory_extraction_model_id': 'memory_extraction_model_id',
        'settings.memory_extraction_cooldown_seconds': 'memory_extraction_cooldown_seconds',
        'settings.memory_extraction_max_pending_turns': 'memory_extraction_max_pending_turns',
      })
      if (Object.keys(errors).length > 0) {
        setFieldErrors(errors)
      }
      console.error('Failed to save memory settings:', error)
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-64 w-full" />
      </div>
    )
  }

  if (settingsLoadFailed || !settingsReady) {
    return (
      <div className="space-y-4">
        <p className="text-sm text-destructive">{t('loadError')}</p>
        <Button onClick={loadData}>{t('retry')}</Button>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Brain className="h-5 w-5 text-primary" />
            <CardTitle>{t('memorySettings.title')}</CardTitle>
          </div>
          <CardDescription>{t('memorySettings.description')}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Toggle Switch */}
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <Label>
                {t('memorySettings.enableExtraction')}
              </Label>
              <p className="text-sm text-muted-foreground">
                {t('memorySettings.enableExtractionDesc')}
              </p>
            </div>
            <Switch
              checked={settings.memory_async_extraction_enabled}
              onCheckedChange={(checked) =>
                setSettings((prev) => ({ ...prev, memory_async_extraction_enabled: checked }))
              }
              disabled={!canUpdateSettings || saving}
            />
          </div>

          {/* Model Selection */}
          <div className="space-y-2">
            <Label htmlFor="extraction-model">{t('memorySettings.extractionModel')}</Label>
            <p className="text-xs text-muted-foreground">
              {t('memorySettings.extractionModelDesc')}
            </p>
            <Select
              value={selectedModel?.id ?? AUTO_MODEL_VALUE}
              onValueChange={(val) =>
                setSettings((prev) => ({
                  ...prev,
                  memory_extraction_model_id:
                    !val || val === AUTO_MODEL_VALUE ? '' : val,
                }))
              }
              disabled={!canUpdateSettings || saving || modelsLoading}
            >
              <SelectTrigger id="extraction-model" className="w-full">
                <SelectValue>{selectedModelLabel}</SelectValue>
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={AUTO_MODEL_VALUE}>
                  {t('memorySettings.modelAuto')}
                </SelectItem>
                {chatModels.map((model) => (
                  <SelectItem key={model.id} value={model.id}>
                    {`${model.provider_display_name?.trim() || model.provider} / ${model.name}`}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Cooldown Seconds */}
          <div className="space-y-2">
            <Label htmlFor="cooldown-seconds">{t('memorySettings.cooldownSeconds')}</Label>
            <NumberInput
              id="cooldown-seconds"
              value={settings.memory_extraction_cooldown_seconds}
              onChange={(val) => {
                setSettings((prev) => ({
                  ...prev,
                  memory_extraction_cooldown_seconds: val === '' ? 180 : val,
                }))
                setFieldErrors((prev) => clearValidationError(prev, 'memory_extraction_cooldown_seconds'))
              }}
              min={10}
              max={3600}
              disabled={!canUpdateSettings || saving}
              aria-invalid={!!fieldErrors.memory_extraction_cooldown_seconds}
            />
            <FieldError>{fieldErrors.memory_extraction_cooldown_seconds}</FieldError>
            <p className="text-xs text-muted-foreground">
              {t('memorySettings.cooldownSecondsHint')}
            </p>
          </div>

          {/* Max Pending Turns */}
          <div className="space-y-2">
            <Label htmlFor="max-turns">{t('memorySettings.maxPendingTurns')}</Label>
            <NumberInput
              id="max-turns"
              value={settings.memory_extraction_max_pending_turns}
              onChange={(val) => {
                setSettings((prev) => ({
                  ...prev,
                  memory_extraction_max_pending_turns: val === '' ? 6 : val,
                }))
                setFieldErrors((prev) => clearValidationError(prev, 'memory_extraction_max_pending_turns'))
              }}
              min={1}
              max={50}
              disabled={!canUpdateSettings || saving}
              aria-invalid={!!fieldErrors.memory_extraction_max_pending_turns}
            />
            <FieldError>{fieldErrors.memory_extraction_max_pending_turns}</FieldError>
            <p className="text-xs text-muted-foreground">
              {t('memorySettings.maxPendingTurnsHint')}
            </p>
          </div>
        </CardContent>
      </Card>

      {/* Action Buttons */}
      {canUpdateSettings && (
        <div className="flex justify-end">
          <Button onClick={handleSave} disabled={saving || !settingsReady}>
            {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {t('saveChanges')}
          </Button>
        </div>
      )}
    </div>
  )
}
