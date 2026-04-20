'use client'

import { useState, useEffect } from 'react'
import { useTranslations } from 'next-intl'
import { Loader2, Plus, Trash2, ChevronDown } from 'lucide-react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Switch } from '@/components/ui/switch'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { ToolCreateInput, ToolUpdateInput, ToolDetail, HttpConfig, ToolCategory } from '@/lib/api/tools'
import { cn } from '@/lib/utils'
import { FieldError } from '@/components/ui/field'
import {
  clearValidationError,
  getValidationSummaryEntries,
  mapValidationErrors,
  normalizeValidationErrors,
  formatValidationSummaryMessage
} from '@/lib/validation'

interface HttpToolDialogProps {
  tool?: ToolDetail | null
  open: boolean
  onOpenChange: (open: boolean) => void
  onSave: (data: ToolCreateInput | ToolUpdateInput) => Promise<void>
}

const HTTP_METHODS = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE'] as const

const HTTP_TOOL_ERROR_PATH_MAP = {
  display_name: 'displayName',
  'http_config.url': 'url',
  'http_config.body_template': 'bodyTemplate',
  'http_config.headers': 'headers',
  'http_config.query_params': 'queryParams',
  'http_config.timeout': 'timeout',
} as const

interface KeyValuePair {
  key: string
  value: string
}

export function HttpToolDialog({
  tool,
  open,
  onOpenChange,
  onSave,
}: HttpToolDialogProps) {
  const t = useTranslations('tools')
  const tCommon = useTranslations('common')

  const isEditing = !!tool

  // 基本信息
  const [name, setName] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [description, setDescription] = useState('')
  const [icon, setIcon] = useState('')
  const [category, setCategory] = useState<ToolCategory>('api')
  const [isEnabled, setIsEnabled] = useState(true)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})

  // HTTP 配置
  const [method, setMethod] = useState<typeof HTTP_METHODS[number]>('GET')
  const [url, setUrl] = useState('')
  const [headers, setHeaders] = useState<KeyValuePair[]>([{ key: '', value: '' }])
  const [queryParams, setQueryParams] = useState<KeyValuePair[]>([{ key: '', value: '' }])
  const [bodyTemplate, setBodyTemplate] = useState('')
  const [timeout, setTimeout] = useState(30)

  // UI 状态
  const [isLoading, setIsLoading] = useState(false)
  const [headersOpen, setHeadersOpen] = useState(false)
  const [paramsOpen, setParamsOpen] = useState(false)
  const [bodyOpen, setBodyOpen] = useState(false)

  // 初始化表单
  useEffect(() => {
    if (open) {
      if (tool) {
        setName(tool.name)
        setDisplayName(tool.display_name)
        setDescription(tool.description)
        setIcon(tool.icon || '')
        setCategory(tool.category || 'api')
        setIsEnabled(tool.is_enabled)

        if (tool.http_config) {
          setMethod(tool.http_config.method as typeof HTTP_METHODS[number])
          setUrl(tool.http_config.url)
          setHeaders(
            tool.http_config.headers
              ? Object.entries(tool.http_config.headers).map(([key, value]) => ({ key, value }))
              : [{ key: '', value: '' }]
          )
          setQueryParams(
            tool.http_config.query_params
              ? Object.entries(tool.http_config.query_params).map(([key, value]) => ({ key, value }))
              : [{ key: '', value: '' }]
          )
          setBodyTemplate(tool.http_config.body_template || '')
          setTimeout(tool.http_config.timeout || 30)
        }
      } else {
        // 重置为默认值
        setName('')
        setDisplayName('')
        setDescription('')
        setIcon('')
        setCategory('api')
        setIsEnabled(true)
        setMethod('GET')
        setUrl('')
        setHeaders([{ key: '', value: '' }])
        setQueryParams([{ key: '', value: '' }])
        setBodyTemplate('')
        setTimeout(30)
      }
    }
  }, [tool, open])

  const handleSave = async () => {
    const nextErrors: Record<string, string> = {}
    if (!name.trim()) nextErrors.name = t('form.nameRequired')
    if (!displayName.trim()) nextErrors.displayName = t('form.displayNameRequired')
    if (!url.trim()) nextErrors.url = t('form.urlRequired')

    if (Object.keys(nextErrors).length > 0) {
      setFieldErrors(nextErrors)
      return
    }

    setFieldErrors({})
    setIsLoading(true)
    try {
      const httpConfig: HttpConfig = {
        method,
        url,
        headers: headers
          .filter((h) => h.key.trim())
          .reduce((acc, h) => ({ ...acc, [h.key]: h.value }), {}),
        query_params: queryParams
          .filter((p) => p.key.trim())
          .reduce((acc, p) => ({ ...acc, [p.key]: p.value }), {}),
        body_template: bodyTemplate || undefined,
        timeout,
      }

      const data: ToolCreateInput | ToolUpdateInput = {
        name,
        display_name: displayName,
        description,
        icon,
        category,
        is_enabled: isEnabled,
        type: 'custom',
        custom_type: 'http',
        http_config: httpConfig,
      }

      await onSave(data)
      onOpenChange(false)
    } catch (error) {
      const errors = mapValidationErrors(normalizeValidationErrors(error), HTTP_TOOL_ERROR_PATH_MAP)
      if (Object.keys(errors).length > 0) {
        setFieldErrors(errors)
      } else {
        throw error
      }
    } finally {
      setIsLoading(false)
    }
  }

  const addKeyValuePair = (
    pairs: KeyValuePair[],
    setPairs: (pairs: KeyValuePair[]) => void
  ) => {
    setPairs([...pairs, { key: '', value: '' }])
  }

  const removeKeyValuePair = (
    index: number,
    pairs: KeyValuePair[],
    setPairs: (pairs: KeyValuePair[]) => void
  ) => {
    if (pairs.length > 1) {
      setPairs(pairs.filter((_, i) => i !== index))
    }
  }

  const updateKeyValuePair = (
    index: number,
    field: 'key' | 'value',
    value: string,
    pairs: KeyValuePair[],
    setPairs: (pairs: KeyValuePair[]) => void,
    errorKey: 'headers' | 'queryParams'
  ) => {
    const newPairs = [...pairs]
    newPairs[index][field] = value
    setPairs(newPairs)
    setFieldErrors((prev) => clearValidationError(prev, errorKey))
  }

  const summaryEntries = getValidationSummaryEntries(fieldErrors, ['name', 'displayName', 'url', 'bodyTemplate', 'headers', 'queryParams', 'timeout'])

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>
            {isEditing ? t('httpDialog.editTitle') : t('httpDialog.createTitle')}
          </DialogTitle>
          <DialogDescription>
            {t('httpDialog.description')}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6 py-4">
          {summaryEntries.length > 0 && (
            <div className="rounded-md border border-destructive/30 bg-destructive/5 p-3 space-y-1">
              {summaryEntries.map(([field, message]) => (
                <FieldError key={field}>
                  {formatValidationSummaryMessage(field, message)}
                </FieldError>
              ))}
            </div>
          )}
          {/* 基本信息 */}
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="name">{t('name')}</Label>
              <Input
                id="name"
                placeholder={t('httpDialog.toolNamePlaceholder')}
                value={name}
                onChange={(e) => {
                  setName(e.target.value)
                  setFieldErrors((prev) => clearValidationError(prev, 'name'))
                }}
                disabled={isEditing}
                aria-invalid={!!fieldErrors.name}
              />
              <FieldError>{fieldErrors.name}</FieldError>
            </div>
            <div className="space-y-2">
              <Label htmlFor="displayName">{t('displayName')}</Label>
              <Input
                id="displayName"
                placeholder={t('displayNamePlaceholder')}
                value={displayName}
                onChange={(e) => {
                  setDisplayName(e.target.value)
                  setFieldErrors((prev) => clearValidationError(prev, 'displayName'))
                }}
                aria-invalid={!!fieldErrors.displayName}
              />
              <FieldError>{fieldErrors.displayName}</FieldError>
            </div>
          </div>

          <div className="grid grid-cols-[auto_1fr_auto] gap-4">
            <div className="space-y-2">
              <Label htmlFor="icon">{t('icon')}</Label>
              <Input
                id="icon"
                className="w-16 text-center text-xl"
                value={icon}
                onChange={(e) => setIcon(e.target.value)}
                maxLength={2}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="description">{t('descriptionLabel')}</Label>
              <Input
                id="description"
                placeholder={t('descriptionPlaceholder')}
                value={description}
                onChange={(e) => setDescription(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label>{t('category')}</Label>
              <Select value={category} onValueChange={(v) => setCategory(v as ToolCategory)}>
                <SelectTrigger className="w-28">
                  <SelectValue>{t(`categories.${category}`)}</SelectValue>
                </SelectTrigger>
                <SelectContent side="bottom" alignItemWithTrigger={false}>
                  <SelectItem value="time">{t('categories.time')}</SelectItem>
                  <SelectItem value="math">{t('categories.math')}</SelectItem>
                  <SelectItem value="search">{t('categories.search')}</SelectItem>
                  <SelectItem value="web">{t('categories.web')}</SelectItem>
                  <SelectItem value="file">{t('categories.file')}</SelectItem>
                  <SelectItem value="code">{t('categories.code')}</SelectItem>
                  <SelectItem value="api">{t('categories.api')}</SelectItem>
                  <SelectItem value="data">{t('categories.data')}</SelectItem>
                  <SelectItem value="other">{t('categories.other')}</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* HTTP 配置 */}
          <div className="space-y-4 border rounded-lg p-4">
            <h4 className="font-medium">{t('httpDialog.httpConfig')}</h4>

            <div className="flex gap-2">
              <Select value={method} onValueChange={(v) => setMethod(v as typeof HTTP_METHODS[number])}>
                <SelectTrigger className="w-28">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {HTTP_METHODS.map((m) => (
                    <SelectItem key={m} value={m}>
                      {m}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Input
                placeholder={t('httpDialog.urlPlaceholder')}
                value={url}
                onChange={(e) => {
                  setUrl(e.target.value)
                  setFieldErrors((prev) => clearValidationError(prev, 'url'))
                }}
                className="flex-1"
              />
            </div>
            <FieldError>{fieldErrors.url}</FieldError>
            <FieldError>{fieldErrors.headers}</FieldError>
            <FieldError>{fieldErrors.queryParams}</FieldError>
            <FieldError>{fieldErrors.timeout}</FieldError>

            {/* Headers */}
            <Collapsible open={headersOpen} onOpenChange={setHeadersOpen}>
              <CollapsibleTrigger asChild>
                <Button variant="ghost" size="sm" className="w-full justify-between">
                  <span>{t('httpDialog.headers')}</span>
                  <ChevronDown className={cn('h-4 w-4 transition-transform', headersOpen && 'rotate-180')} />
                </Button>
              </CollapsibleTrigger>
              <CollapsibleContent className="space-y-2 pt-2">
                {headers.map((header, index) => (
                  <div key={index} className="flex gap-2">
                    <Input
                      placeholder="Key"
                      value={header.key}
                      onChange={(e) => updateKeyValuePair(index, 'key', e.target.value, headers, setHeaders, 'headers')}
                      className="flex-1"
                    />
                    <Input
                      placeholder="Value"
                      value={header.value}
                      onChange={(e) => updateKeyValuePair(index, 'value', e.target.value, headers, setHeaders, 'headers')}
                      className="flex-1"
                    />
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => removeKeyValuePair(index, headers, setHeaders)}
                      disabled={headers.length === 1}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                ))}
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => addKeyValuePair(headers, setHeaders)}
                >
                  <Plus className="h-4 w-4 mr-1" />
                  {t('httpDialog.addHeader')}
                </Button>
              </CollapsibleContent>
            </Collapsible>

            {/* Query Params */}
            <Collapsible open={paramsOpen} onOpenChange={setParamsOpen}>
              <CollapsibleTrigger asChild>
                <Button variant="ghost" size="sm" className="w-full justify-between">
                  <span>{t('httpDialog.queryParams')}</span>
                  <ChevronDown className={cn('h-4 w-4 transition-transform', paramsOpen && 'rotate-180')} />
                </Button>
              </CollapsibleTrigger>
              <CollapsibleContent className="space-y-2 pt-2">
                {queryParams.map((param, index) => (
                  <div key={index} className="flex gap-2">
                    <Input
                      placeholder="Key"
                      value={param.key}
                      onChange={(e) => updateKeyValuePair(index, 'key', e.target.value, queryParams, setQueryParams, 'queryParams')}
                      className="flex-1"
                    />
                    <Input
                      placeholder="Value"
                      value={param.value}
                      onChange={(e) => updateKeyValuePair(index, 'value', e.target.value, queryParams, setQueryParams, 'queryParams')}
                      className="flex-1"
                    />
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => removeKeyValuePair(index, queryParams, setQueryParams)}
                      disabled={queryParams.length === 1}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                ))}
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => addKeyValuePair(queryParams, setQueryParams)}
                >
                  <Plus className="h-4 w-4 mr-1" />
                  {t('httpDialog.addParam')}
                </Button>
              </CollapsibleContent>
            </Collapsible>

            {/* Body Template */}
            {['POST', 'PUT', 'PATCH'].includes(method) && (
              <Collapsible open={bodyOpen} onOpenChange={setBodyOpen}>
                <CollapsibleTrigger asChild>
                  <Button variant="ghost" size="sm" className="w-full justify-between">
                    <span>{t('httpDialog.bodyTemplate')}</span>
                    <ChevronDown className={cn('h-4 w-4 transition-transform', bodyOpen && 'rotate-180')} />
                  </Button>
                </CollapsibleTrigger>
                <CollapsibleContent className="pt-2">
                  <Textarea
                    placeholder='{"key": "{{value}}"}'
                    value={bodyTemplate}
                    onChange={(e) => {
                      setBodyTemplate(e.target.value)
                      setFieldErrors((prev) => clearValidationError(prev, 'bodyTemplate'))
                    }}
                    rows={4}
                    className="font-mono text-sm"
                  />
                  <FieldError>{fieldErrors.bodyTemplate}</FieldError>
                  <p className="text-xs text-muted-foreground mt-1">
                    {t('httpDialog.bodyTemplateHint')}
                  </p>
                </CollapsibleContent>
              </Collapsible>
            )}

            {/* Timeout */}
            <div className="flex items-center gap-2">
              <Label htmlFor="timeout" className="whitespace-nowrap">
                {t('httpDialog.timeout')}
              </Label>
              <Input
                id="timeout"
                type="number"
                value={timeout}
                onChange={(e) => {
                  setTimeout(parseInt(e.target.value) || 30)
                  setFieldErrors((prev) => clearValidationError(prev, 'timeout'))
                }}
                className="w-20"
                min={1}
                max={300}
                aria-invalid={!!fieldErrors.timeout}
              />
              <span className="text-sm text-muted-foreground">s</span>
            </div>
          </div>

          {/* 启用状态 */}
          <div className="flex items-center justify-between">
            <Label htmlFor="enabled">{t('enabled')}</Label>
            <Switch
              id="enabled"
              checked={isEnabled}
              onCheckedChange={setIsEnabled}
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {tCommon('cancel')}
          </Button>
          <Button onClick={handleSave} disabled={isLoading}>
            {isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {isEditing ? tCommon('save') : tCommon('create')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
