'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { toast } from 'sonner'
import { Image as ImageIcon, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { FieldError } from '@/components/ui/field'
import { Label } from '@/components/ui/label'
import { NumberInput } from '@/components/ui/number-input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { Switch } from '@/components/ui/switch'
import { useCanPerform } from '@/components/permission-guard'
import { modelsApi, type Model } from '@/lib/api/admin/models'
import { siteSettingsApi, type KnowledgeBaseImageSettings } from '@/lib/api/admin/site-settings'
import {
  clearValidationError,
  mapValidationErrors,
  normalizeValidationErrors,
} from '@/lib/validation'

const IMAGE_INPUT_PROVIDERS: Record<string, true> = {
  openai: true,
  azure_openai: true,
  xai: true,
  deepseek: true,
  moonshot: true,
  zhipu: true,
  qwen: true,
  baichuan: true,
  minimax: true,
  volcengine: true,
  siliconflow: true,
  ollama: true,
  anthropic: true,
  google: true,
  custom: true,
}
const NO_MODEL_VALUE = '__none__'
const DEFAULTS: KnowledgeBaseImageSettings = {
  kb_image_understanding_enabled: false,
  kb_image_understanding_model_id: '',
  kb_image_ocr_model_id: '',
  kb_image_understanding_allow_external: false,
  kb_image_understanding_max_images: 8,
  kb_image_understanding_max_image_bytes: 10485760,
  kb_image_understanding_max_image_pixels: 20000000,
  kb_image_understanding_concurrency: 2,
}
const NUMBER_FIELDS = [
  'kb_image_understanding_max_images',
  'kb_image_understanding_max_image_bytes',
  'kb_image_understanding_max_image_pixels',
  'kb_image_understanding_concurrency',
] as const

export default function SiteSettingsParsingPage() {
  const t = useTranslations('siteSettings')
  const { canPerform } = useCanPerform()
  const canUpdateSettings = canPerform('admin:settings:update')
  const [settings, setSettings] = React.useState<KnowledgeBaseImageSettings>(DEFAULTS)
  const [imageModels, setImageModels] = React.useState<Model[]>([])
  const [loading, setLoading] = React.useState(true)
  const [settingsReady, setSettingsReady] = React.useState(false)
  const [modelsLoading, setModelsLoading] = React.useState(true)
  const [saving, setSaving] = React.useState(false)
  const [fieldErrors, setFieldErrors] = React.useState<Record<string, string>>({})

  const selectedModel = imageModels.find((model) => model.id === settings.kb_image_understanding_model_id)
  const selectedModelLabel = selectedModel
    ? `${selectedModel.provider_display_name?.trim() || selectedModel.provider} / ${selectedModel.name}`
    : t('parsingSettings.modelNone')
  const selectedOcrModel = imageModels.find((model) => model.id === settings.kb_image_ocr_model_id)
  const selectedOcrModelLabel = selectedOcrModel
    ? `${selectedOcrModel.provider_display_name?.trim() || selectedOcrModel.provider} / ${selectedOcrModel.name}`
    : t('parsingSettings.ocrModelNone')

  const loadData = React.useCallback(async () => {
    setLoading(true)
    setSettingsReady(false)
    setModelsLoading(true)
    const [settingsResult, modelsResult] = await Promise.allSettled([
      siteSettingsApi.getKnowledgeBaseImages(),
      modelsApi.getModels({ model_type: ['chat'], is_enabled: true, pageSize: 100 }),
    ])

    if (settingsResult.status === 'fulfilled') {
      setSettings(settingsResult.value)
      setSettingsReady(true)
    } else {
      console.error('Failed to load knowledge-base image settings:', settingsResult.reason)
    }

    if (modelsResult.status === 'fulfilled') {
      const models = (modelsResult.value.items || []).filter((model) => {
        const modalities = model.capabilities?.input_modalities
        return Boolean(IMAGE_INPUT_PROVIDERS[model.provider])
          && Array.isArray(modalities)
          && modalities.includes('image')
      })
      if (settingsResult.status === 'fulfilled') {
        const missingIds = [
          settingsResult.value.kb_image_understanding_model_id,
          settingsResult.value.kb_image_ocr_model_id,
        ].filter((id) => id && !models.some((model) => model.id === id))
        const savedModels = await Promise.allSettled(
          missingIds.map((id) => modelsApi.getModel(id)),
        )
        for (const result of savedModels) {
          if (result.status === 'fulfilled' && !models.some((model) => model.id === result.value.id)) {
            models.push(result.value)
          }
        }
      }
      setImageModels(models)
    } else {
      console.error('Failed to load image-capable models:', modelsResult.reason)
    }
    setModelsLoading(false)
    setLoading(false)
  }, [])

  React.useEffect(() => {
    void loadData()
  }, [loadData])

  const setBoolean = (key: 'kb_image_understanding_enabled' | 'kb_image_understanding_allow_external', value: boolean) => {
    setSettings((previous) => ({ ...previous, [key]: value }))
    setFieldErrors((previous) => clearValidationError(previous, key))
  }

  const setNumber = (key: (typeof NUMBER_FIELDS)[number], value: number | '') => {
    setSettings((previous) => ({ ...previous, [key]: value === '' ? DEFAULTS[key] : value }))
    setFieldErrors((previous) => clearValidationError(previous, key))
  }

  const handleSave = async () => {
    if (!canUpdateSettings || !settingsReady) return
    setFieldErrors({})
    if (
      settings.kb_image_understanding_enabled
      && !settings.kb_image_understanding_model_id
      && !settings.kb_image_ocr_model_id
    ) {
      setFieldErrors({ kb_image_understanding_model_id: t('parsingSettings.modelRequired') })
      return
    }
    try {
      setSaving(true)
      await siteSettingsApi.updateKnowledgeBaseImages(settings)
      toast.success(t('saveSuccess'))
    } catch (error: unknown) {
      const keys = [
        'kb_image_understanding_enabled',
        'kb_image_understanding_model_id',
        'kb_image_ocr_model_id',
        'kb_image_understanding_allow_external',
        ...NUMBER_FIELDS,
      ]
      const keyMap = Object.fromEntries(keys.flatMap((key) => [[key, key], [`settings.${key}`, key]]))
      const errors = mapValidationErrors(normalizeValidationErrors(error), keyMap)
      if (Object.keys(errors).length) {
        setFieldErrors(errors)
      } else {
        toast.error(error instanceof Error ? error.message : t('saveError'))
      }
      console.error('Failed to save knowledge-base image settings:', error)
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return <div className="space-y-6"><Skeleton className="h-64 w-full" /></div>
  }

  if (!settingsReady) {
    return (
      <div className="space-y-4">
        <p className="text-sm text-destructive">{t('loadError')}</p>
        <Button onClick={() => void loadData()}>{t('retry')}</Button>
      </div>
    )
  }

  const numberFields = [
    { key: 'kb_image_understanding_max_images', min: 1, max: 20, label: 'maxImages', hint: 'maxImagesHint' },
    { key: 'kb_image_understanding_max_image_bytes', min: 1, max: 52428800, label: 'maxImageBytes', hint: 'maxImageBytesHint' },
    { key: 'kb_image_understanding_max_image_pixels', min: 1, max: 40000000, label: 'maxImagePixels', hint: 'maxImagePixelsHint' },
    { key: 'kb_image_understanding_concurrency', min: 1, max: 8, label: 'concurrency', hint: 'concurrencyHint' },
  ] as const

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <ImageIcon className="h-5 w-5 text-primary" />
            <CardTitle>{t('parsingSettings.title')}</CardTitle>
          </div>
          <CardDescription>{t('parsingSettings.description')}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="flex items-center justify-between gap-4">
            <div className="space-y-0.5">
              <Label htmlFor="kb-image-understanding-enabled">{t('parsingSettings.enableUnderstanding')}</Label>
              <p className="text-sm text-muted-foreground">{t('parsingSettings.enableUnderstandingDesc')}</p>
            </div>
            <Switch
              id="kb-image-understanding-enabled"
              checked={settings.kb_image_understanding_enabled}
              onCheckedChange={(checked) => setBoolean('kb_image_understanding_enabled', checked)}
              disabled={!canUpdateSettings || saving}
            />
          </div>
          <FieldError>{fieldErrors.kb_image_understanding_enabled}</FieldError>

          <div className="space-y-2">
            <Label htmlFor="kb-image-model">{t('parsingSettings.visionModel')}</Label>
            <p className="text-xs text-muted-foreground">{t('parsingSettings.visionModelDesc')}</p>
            <Select
              value={selectedModel?.id ?? NO_MODEL_VALUE}
              onValueChange={(value) => {
                setSettings((previous) => ({
                  ...previous,
                  kb_image_understanding_model_id: !value || value === NO_MODEL_VALUE ? '' : value,
                }))
                setFieldErrors((previous) => clearValidationError(previous, 'kb_image_understanding_model_id'))
              }}
              disabled={!canUpdateSettings || saving || modelsLoading}
            >
              <SelectTrigger id="kb-image-model" className="w-full">
                <SelectValue>{selectedModelLabel}</SelectValue>
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={NO_MODEL_VALUE}>{t('parsingSettings.modelNone')}</SelectItem>
                {imageModels.map((model) => (
                  <SelectItem key={model.id} value={model.id}>
                    {`${model.provider_display_name?.trim() || model.provider} / ${model.name}`}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <FieldError>{fieldErrors.kb_image_understanding_model_id}</FieldError>
          </div>

          <div className="space-y-2">
            <Label htmlFor="kb-image-ocr-model">{t('parsingSettings.ocrModel')}</Label>
            <p className="text-xs text-muted-foreground">{t('parsingSettings.ocrModelDesc')}</p>
            <Select
              value={selectedOcrModel?.id ?? NO_MODEL_VALUE}
              onValueChange={(value) => {
                setSettings((previous) => ({
                  ...previous,
                  kb_image_ocr_model_id: !value || value === NO_MODEL_VALUE ? '' : value,
                }))
                setFieldErrors((previous) => clearValidationError(previous, 'kb_image_ocr_model_id'))
              }}
              disabled={!canUpdateSettings || saving || modelsLoading}
            >
              <SelectTrigger id="kb-image-ocr-model" className="w-full">
                <SelectValue>{selectedOcrModelLabel}</SelectValue>
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={NO_MODEL_VALUE}>{t('parsingSettings.ocrModelNone')}</SelectItem>
                {imageModels.map((model) => (
                  <SelectItem key={model.id} value={model.id}>
                    {`${model.provider_display_name?.trim() || model.provider} / ${model.name}`}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <FieldError>{fieldErrors.kb_image_ocr_model_id}</FieldError>
          </div>

          <div className="flex items-center justify-between gap-4">
            <div className="space-y-0.5">
              <Label htmlFor="kb-image-external">{t('parsingSettings.allowExternal')}</Label>
              <p className="text-sm text-muted-foreground">{t('parsingSettings.allowExternalDesc')}</p>
            </div>
            <Switch
              id="kb-image-external"
              checked={settings.kb_image_understanding_allow_external}
              onCheckedChange={(checked) => setBoolean('kb_image_understanding_allow_external', checked)}
              disabled={!canUpdateSettings || saving}
            />
          </div>
          <FieldError>{fieldErrors.kb_image_understanding_allow_external}</FieldError>

          <div className="grid gap-6 md:grid-cols-2">
            {numberFields.map(({ key, min, max, label, hint }) => (
              <div key={key} className="space-y-2">
                <Label htmlFor={key}>{t(`parsingSettings.${label}`)}</Label>
                <NumberInput
                  id={key}
                  value={settings[key]}
                  onChange={(value) => setNumber(key, value)}
                  min={min}
                  max={max}
                  disabled={!canUpdateSettings || saving}
                  aria-invalid={!!fieldErrors[key]}
                />
                <FieldError>{fieldErrors[key]}</FieldError>
                <p className="text-xs text-muted-foreground">{t(`parsingSettings.${hint}`)}</p>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
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
