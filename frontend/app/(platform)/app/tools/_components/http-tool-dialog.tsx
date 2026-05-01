'use client'

import { useState, useEffect, useRef, useCallback } from 'react'
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
import { ToolCreateInput, ToolUpdateInput, ToolDetail, HttpConfig, ToolCategory, ToolParameter, FormField } from '@/lib/api/tools'
import type { UserTeamInfo } from '@/lib/api'
import { ImageUpload } from '@/components/ui/image-upload'
import { FieldError } from '@/components/ui/field'
import {
  clearValidationError,
  clearValidationErrorsByPrefix,
  getValidationSummaryEntries,
  mapValidationErrors,
  normalizeValidationErrors,
  formatValidationSummaryMessage
} from '@/lib/validation'
import { cn } from '@/lib/utils'
import { ToolCategoryInput } from './tool-category-input'

// 带变量补全的输入框组件
interface VariableInputProps {
  value: string
  onChange: (value: string) => void
  variables: string[]
  placeholder?: string
  className?: string
  multiline?: boolean
  rows?: number
  suggestionTitle?: string
}

function VariableInput({ value, onChange, variables, placeholder, className, multiline, rows = 4, suggestionTitle = '参数补全' }: VariableInputProps) {
  const [showSuggestions, setShowSuggestions] = useState(false)
  const [filteredVars, setFilteredVars] = useState<string[]>([])
  const [cursorPosition, setCursorPosition] = useState(0)
  const [selectedIndex, setSelectedIndex] = useState(0)
  const inputRef = useRef<HTMLInputElement | HTMLTextAreaElement>(null)

  // 检测是否正在输入变量
  const checkForVariableInput = useCallback((text: string, pos: number) => {
    // 从光标位置向前查找 {{
    const beforeCursor = text.slice(0, pos)
    const lastOpenBrace = beforeCursor.lastIndexOf('{{')
    
    if (lastOpenBrace === -1) {
      setShowSuggestions(false)
      return
    }
    
    // 检查 {{ 后面是否已经有 }}
    const afterOpenBrace = text.slice(lastOpenBrace + 2, pos)
    if (afterOpenBrace.includes('}}')) {
      setShowSuggestions(false)
      return
    }
    
    // 获取已输入的变量名部分
    const partialVar = afterOpenBrace.toLowerCase()
    
    // 过滤匹配的变量
    const filtered = variables.filter(v => 
      v.toLowerCase().includes(partialVar)
    )
    
    if (filtered.length > 0) {
      setFilteredVars(filtered)
      setSelectedIndex(0)
      setShowSuggestions(true)
    } else {
      setShowSuggestions(false)
    }
  }, [variables])

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    const newValue = e.target.value
    const pos = e.target.selectionStart || 0
    onChange(newValue)
    setCursorPosition(pos)
    checkForVariableInput(newValue, pos)
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (!showSuggestions) return

    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault()
        setSelectedIndex(prev => Math.min(prev + 1, filteredVars.length - 1))
        break
      case 'ArrowUp':
        e.preventDefault()
        setSelectedIndex(prev => Math.max(prev - 1, 0))
        break
      case 'Enter':
      case 'Tab':
        if (filteredVars.length > 0) {
          e.preventDefault()
          insertVariable(filteredVars[selectedIndex])
        }
        break
      case 'Escape':
        setShowSuggestions(false)
        break
    }
  }

  const insertVariable = (varName: string) => {
    const beforeCursor = value.slice(0, cursorPosition)
    const afterCursor = value.slice(cursorPosition)
    
    // 找到最后一个 {{ 的位置
    const lastOpenBrace = beforeCursor.lastIndexOf('{{')
    
    if (lastOpenBrace !== -1) {
      // 替换 {{ 后面已输入的内容
      const newValue = beforeCursor.slice(0, lastOpenBrace) + `{{${varName}}}` + afterCursor
      onChange(newValue)
      
      // 设置光标位置到 }} 后面
      const newPos = lastOpenBrace + varName.length + 4
      setTimeout(() => {
        if (inputRef.current) {
          inputRef.current.setSelectionRange(newPos, newPos)
          inputRef.current.focus()
        }
      }, 0)
    }
    
    setShowSuggestions(false)
  }

  const handleBlur = () => {
    // 延迟关闭，以便能点击建议项
    setTimeout(() => setShowSuggestions(false), 150)
  }

  const commonProps = {
    value,
    onChange: handleChange,
    onKeyDown: handleKeyDown,
    onBlur: handleBlur,
    placeholder,
  }

  const showDropdown = showSuggestions && filteredVars.length > 0

  return (
    <div className={cn('relative', className)}>
      {multiline ? (
        <Textarea
          ref={inputRef as React.RefObject<HTMLTextAreaElement>}
          rows={rows}
          className="w-full"
          {...commonProps}
        />
      ) : (
        <Input
          ref={inputRef as React.RefObject<HTMLInputElement>}
          className="w-full"
          {...commonProps}
        />
      )}
      {showDropdown && (
        <div className="absolute left-0 top-full mt-1 z-50 w-48 rounded-md border bg-popover p-1 shadow-md">
          <div className="text-xs text-muted-foreground px-2 py-1 border-b mb-1">
            {suggestionTitle}
          </div>
          {filteredVars.map((varName, index) => (
            <button
              key={varName}
              className={cn(
                'w-full text-left px-2 py-1.5 text-sm rounded-sm',
                index === selectedIndex ? 'bg-accent text-accent-foreground' : 'hover:bg-muted'
              )}
              onMouseDown={(e) => {
                e.preventDefault()
                insertVariable(varName)
              }}
              onMouseEnter={() => setSelectedIndex(index)}
            >
              <span className="font-mono text-primary">{`{{${varName}}}`}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

interface HttpToolDialogProps {
  tool?: ToolDetail | null
  open: boolean
  onOpenChange: (open: boolean) => void
  onSave: (data: ToolCreateInput | ToolUpdateInput) => Promise<void>
  teams?: UserTeamInfo[]
  selectedTeamId?: string
  onSelectedTeamChange?: (teamId: string | null) => void
}

const HTTP_METHODS = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE'] as const

// HTTP工具参数字段类型
const HTTP_PARAM_TYPES = ['string', 'number', 'boolean', 'array', 'object', 'file', 'image'] as const

function getHttpParamTypeLabel(t: (key: string) => string, type: string): string {
  const labels: Record<string, string> = {
    string: t('httpDialog.paramTypeString'),
    number: t('httpDialog.paramTypeNumber'),
    boolean: t('httpDialog.paramTypeBoolean'),
    array: t('httpDialog.paramTypeArray'),
    object: t('httpDialog.paramTypeObject'),
    file: t('httpDialog.paramTypeFile'),
    image: t('httpDialog.paramTypeImage'),
  }
  return labels[type] || type
}
const TOOL_NAME_PATTERN = /^[A-Za-z][A-Za-z0-9_]*$/

const HTTP_TOOL_ERROR_PATH_MAP = {
  display_name: 'displayName',
  'http_config.url': 'url',
  'http_config.body_template': 'bodyTemplate',
  parameters: 'parameters',
  'http_config.form_fields': 'formFields',
  'http_config.headers': 'headers',
  'http_config.query_params': 'queryParams',
  'http_config.timeout': 'timeout',
  'http_config.content_type': 'contentType',
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
  teams = [],
  selectedTeamId,
  onSelectedTeamChange,
}: HttpToolDialogProps) {
  const t = useTranslations('platform.tools')
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
  const [contentType, setContentType] = useState<'application/json' | 'multipart/form-data' | 'application/x-www-form-urlencoded'>('application/json')
  const [formFields, setFormFields] = useState<FormField[]>([])

  // 参数定义
  const [parameters, setParameters] = useState<ToolParameter[]>([])

  // UI 状态
  const [isLoading, setIsLoading] = useState(false)
  const [headersOpen, setHeadersOpen] = useState(false)
  const [paramsOpen, setParamsOpen] = useState(false)
  const [bodyOpen, setBodyOpen] = useState(false)
  const [formFieldsOpen, setFormFieldsOpen] = useState(false)

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
        setFieldErrors({})
        setParameters(tool.parameters || [])

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
          setContentType(tool.http_config.content_type || 'application/json')
          setFormFields(tool.http_config.form_fields || [])
        }
      } else {
        // 重置为默认值
        setName('')
        setDisplayName('')
        setDescription('')
        setIcon('')
        setCategory('api')
        setIsEnabled(true)
        setFieldErrors({})
        setMethod('GET')
        setUrl('')
        setHeaders([{ key: '', value: '' }])
        setQueryParams([{ key: '', value: '' }])
        setBodyTemplate('')
        setTimeout(30)
        setContentType('application/json')
        setFormFields([])
        setParameters([])
      }
    }
  }, [tool, open])

  const handleSave = async () => {
    const nextErrors: Record<string, string> = {}
    if (!name.trim()) {
      nextErrors.name = t('error.nameRequired')
    } else if (!TOOL_NAME_PATTERN.test(name.trim())) {
      nextErrors.name = t('error.invalidName')
    }
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
        body_template: contentType === 'application/json' ? (bodyTemplate || undefined) : undefined,
        timeout,
        content_type: ['POST', 'PUT', 'PATCH'].includes(method) ? contentType : undefined,
        form_fields: contentType === 'multipart/form-data' ? formFields.filter(f => f.name.trim()) : undefined,
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
        parameters: parameters.filter(p => p.name.trim()),
      }

      await onSave(data)
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

  // 参数管理
  const addParameter = () => {
    setParameters([...parameters, { name: '', type: 'string', required: false, description: '' }])
  }

  const removeParameter = (index: number) => {
    setParameters(parameters.filter((_, i) => i !== index))
  }

  const updateParameter = (index: number, updates: Partial<ToolParameter>) => {
    const newParams = [...parameters]
    newParams[index] = { ...newParams[index], ...updates }
    setParameters(newParams)
    setFieldErrors((prev) => clearValidationErrorsByPrefix(clearValidationError(prev, 'parameters'), 'parameters'))
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

  const summaryEntries = getValidationSummaryEntries(fieldErrors, ['name', 'displayName', 'url', 'bodyTemplate', 'parameters', 'formFields', 'headers', 'queryParams', 'timeout', 'contentType'])

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
            {!isEditing && onSelectedTeamChange && teams.length > 0 && (
              <div className="space-y-2 col-span-2">
                <Label htmlFor="team">{tCommon('team')}</Label>
                <Select value={selectedTeamId} onValueChange={onSelectedTeamChange}>
                  <SelectTrigger id="team">
                    <SelectValue>
                      {teams.find((team) => team.id === selectedTeamId)?.name || t('selectTeam')}
                    </SelectValue>
                  </SelectTrigger>
                  <SelectContent side="bottom" alignItemWithTrigger={false}>
                    {teams.map((team) => (
                      <SelectItem key={team.id} value={team.id}>
                        {team.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
            <div className="space-y-2">
              <Label htmlFor="name">{t('form.name')}</Label>
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
              <Label htmlFor="displayName">{t('form.displayName')}</Label>
              <Input
                id="displayName"
                placeholder={t('form.displayNamePlaceholder')}
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

          {/* 图标上传 */}
          <div className="flex items-start gap-4">
            <div className="space-y-2">
              <Label>{t('form.icon')}</Label>
              <ImageUpload
                value={icon.startsWith('http') ? icon : ''}
                onChange={setIcon}
                previewSize="sm"
                category="icons"
                placeholder={
                  <span className="text-2xl">
                    {icon.startsWith('http') ? '' : icon}
                  </span>
                }
              />
            </div>
            <div className="flex-1 space-y-2">
              <Label htmlFor="description">{t('form.description')}</Label>
              <Input
                id="description"
                placeholder={t('form.descriptionPlaceholder')}
                value={description}
                onChange={(e) => setDescription(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="category">{t('form.category')}</Label>
              <ToolCategoryInput
                value={category}
                onChange={setCategory}
                inputClassName="w-28"
              />
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
              <VariableInput
                placeholder={t('httpDialog.urlPlaceholder')}
                value={url}
                onChange={(value) => {
                  setUrl(value)
                  setFieldErrors((prev) => clearValidationError(prev, 'url'))
                }}
                variables={parameters.map(p => p.name)}
                className="flex-1"
                suggestionTitle={t('httpDialog.variableCompletion')}
              />
            </div>
            <FieldError>{fieldErrors.url}</FieldError>
            <FieldError>{fieldErrors.headers}</FieldError>
            <FieldError>{fieldErrors.queryParams}</FieldError>
            <FieldError>{fieldErrors.timeout}</FieldError>
            <FieldError>{fieldErrors.contentType}</FieldError>

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
                      placeholder={t('httpDialog.keyPlaceholder')}
                      value={header.key}
                      onChange={(e) => updateKeyValuePair(index, 'key', e.target.value, headers, setHeaders, 'headers')}
                      className="flex-1"
                    />
                    <VariableInput
                      placeholder={t('httpDialog.headerValuePlaceholder')}
                      value={header.value}
                      onChange={(val) => updateKeyValuePair(index, 'value', val, headers, setHeaders, 'headers')}
                      variables={parameters.map(p => p.name)}
                      className="flex-1"
                      suggestionTitle={t('httpDialog.variableCompletion')}
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
                      placeholder={t('httpDialog.keyPlaceholder')}
                      value={param.key}
                      onChange={(e) => updateKeyValuePair(index, 'key', e.target.value, queryParams, setQueryParams, 'queryParams')}
                      className="flex-1"
                    />
                    <VariableInput
                      placeholder={t('httpDialog.queryValuePlaceholder')}
                      value={param.value}
                      onChange={(val) => updateKeyValuePair(index, 'value', val, queryParams, setQueryParams, 'queryParams')}
                      variables={parameters.map(p => p.name)}
                      className="flex-1"
                      suggestionTitle={t('httpDialog.variableCompletion')}
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
              <>
                {/* Content-Type 选择 */}
                <div className="space-y-2">
                  <Label className="text-xs">{t('httpDialog.contentType')}</Label>
                  <Select value={contentType} onValueChange={(v) => {
                    setContentType(v as typeof contentType)
                    setFieldErrors((prev) => clearValidationError(prev, 'contentType'))
                  }}>
                    <SelectTrigger size="default">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="application/json">application/json</SelectItem>
                      <SelectItem value="multipart/form-data">{t('httpDialog.multipartFormData')}</SelectItem>
                      <SelectItem value="application/x-www-form-urlencoded">application/x-www-form-urlencoded</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                {/* JSON Body Template */}
                {contentType === 'application/json' && (
                  <Collapsible open={bodyOpen} onOpenChange={setBodyOpen}>
                    <CollapsibleTrigger asChild>
                      <Button variant="ghost" size="sm" className="w-full justify-between">
                        <span>{t('httpDialog.bodyTemplate')}</span>
                        <ChevronDown className={cn('h-4 w-4 transition-transform', bodyOpen && 'rotate-180')} />
                      </Button>
                    </CollapsibleTrigger>
                    <CollapsibleContent className="pt-2">
                      <VariableInput
                        placeholder={t('httpDialog.bodyTemplatePlaceholder')}
                        value={bodyTemplate}
                        onChange={(value) => {
                          setBodyTemplate(value)
                          setFieldErrors((prev) => clearValidationError(prev, 'bodyTemplate'))
                        }}
                        variables={parameters.map(p => p.name)}
                        multiline
                        rows={4}
                        className="font-mono text-sm"
                        suggestionTitle={t('httpDialog.variableCompletion')}
                      />
                      <FieldError>{fieldErrors.bodyTemplate}</FieldError>
                      <p className="text-xs text-muted-foreground mt-1">
                        {t('httpDialog.bodyTemplateHint')}
                      </p>
                    </CollapsibleContent>
                  </Collapsible>
                )}

                {/* Form Fields for multipart */}
                {contentType === 'multipart/form-data' && (
                  <Collapsible open={formFieldsOpen} onOpenChange={setFormFieldsOpen}>
                    <CollapsibleTrigger asChild>
                      <Button variant="ghost" size="sm" className="w-full justify-between">
                        <span>{t('httpDialog.formFields')}</span>
                        <ChevronDown className={cn('h-4 w-4 transition-transform', formFieldsOpen && 'rotate-180')} />
                      </Button>
                    </CollapsibleTrigger>
                    <CollapsibleContent className="space-y-2 pt-2">
                      {formFields.map((field, index) => (
                        <div key={index} className="flex gap-2">
                          <Input
                            placeholder={t('httpDialog.fieldName')}
                            value={field.name}
                            onChange={(e) => {
                              const newFields = [...formFields]
                              newFields[index] = { ...newFields[index], name: e.target.value }
                              setFormFields(newFields)
                                setFieldErrors((prev) => clearValidationErrorsByPrefix(clearValidationError(prev, 'formFields'), 'formFields'))
                            }}
                            className="flex-1"
                          />
                          <Select
                            value={field.type}
                            onValueChange={(v) => {
                              const newFields = [...formFields]
                              newFields[index] = { ...newFields[index], type: v as 'text' | 'file' }
                              setFormFields(newFields)
                                setFieldErrors((prev) => clearValidationErrorsByPrefix(clearValidationError(prev, 'formFields'), 'formFields'))
                            }}
                          >
                            <SelectTrigger className="w-24">
                              <SelectValue>{field.type === 'file' ? t('httpDialog.fieldTypeFile') : t('httpDialog.fieldTypeText')}</SelectValue>
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value="text">{t('httpDialog.fieldTypeText')}</SelectItem>
                              <SelectItem value="file">{t('httpDialog.fieldTypeFile')}</SelectItem>
                            </SelectContent>
                          </Select>
                          {field.type === 'text' && (
                            <VariableInput
                              placeholder="{{value}}"
                              value={field.value || ''}
                              onChange={(v) => {
                                const newFields = [...formFields]
                                newFields[index] = { ...newFields[index], value: v }
                                setFormFields(newFields)
                                setFieldErrors((prev) => clearValidationErrorsByPrefix(clearValidationError(prev, 'formFields'), 'formFields'))
                              }}
                              variables={parameters.map(p => p.name)}
                              className="flex-1"
                              suggestionTitle={t('httpDialog.variableCompletion')}
                            />
                          )}
                          {field.type === 'file' && (
                            <VariableInput
                              placeholder="{{file}}"
                              value={field.value || ''}
                              onChange={(v) => {
                                const newFields = [...formFields]
                                newFields[index] = { ...newFields[index], value: v }
                                setFormFields(newFields)
                                setFieldErrors((prev) => clearValidationErrorsByPrefix(clearValidationError(prev, 'formFields'), 'formFields'))
                              }}
                              variables={parameters.filter(p => p.type === 'file' || p.type === 'image').map(p => p.name)}
                              className="flex-1"
                              suggestionTitle={t('httpDialog.variableCompletion')}
                            />
                          )}
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => {
                              setFormFields(formFields.filter((_, i) => i !== index))
                              setFieldErrors((prev) => clearValidationErrorsByPrefix(clearValidationError(prev, 'formFields'), 'formFields'))
                            }}
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </div>
                      ))}
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => {
                          setFormFields([...formFields, { name: '', type: 'text', value: '' }])
                          setFieldErrors((prev) => clearValidationErrorsByPrefix(clearValidationError(prev, 'formFields'), 'formFields'))
                        }}
                      >
                        <Plus className="h-4 w-4 mr-1" />
                        {t('httpDialog.addField')}
                      </Button>
                      <FieldError>{fieldErrors.formFields}</FieldError>
                      <p className="text-xs text-muted-foreground">
                        {t('httpDialog.formFieldsHint')}
                      </p>
                    </CollapsibleContent>
                  </Collapsible>
                )}
              </>
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

          {/* 参数定义 */}
          <div className="space-y-4 border rounded-lg p-4">
            <div className="flex items-center justify-between">
              <h4 className="font-medium">{t('httpDialog.parameters')}</h4>
              <Button
                variant="outline"
                size="sm"
                onClick={addParameter}
              >
                <Plus className="h-4 w-4 mr-1" />
                {t('httpDialog.addParameter')}
              </Button>
            </div>
            <FieldError>{fieldErrors.parameters}</FieldError>
            <p className="text-xs text-muted-foreground">
              {t('httpDialog.parametersHint')}
            </p>

            {parameters.length === 0 ? (
              <div className="text-center py-4 text-sm text-muted-foreground">
                {t('httpDialog.noParameters')}
              </div>
            ) : (
              <div className="space-y-3">
                {parameters.map((param, index) => (
                  <div key={index} className="bg-muted/50 rounded-lg p-3 space-y-2">
                    <div className="flex gap-2">
                      <Input
                        placeholder={t('httpDialog.paramName')}
                        value={param.name}
                        onChange={(e) => updateParameter(index, { name: e.target.value })}
                        className="flex-1"
                      />
                      <Select
                        value={param.type}
                        onValueChange={(v) => v && updateParameter(index, { type: v })}
                      >
                        <SelectTrigger className="w-28">
                          <SelectValue>{getHttpParamTypeLabel(t, param.type)}</SelectValue>
                        </SelectTrigger>
                        <SelectContent>
                          {HTTP_PARAM_TYPES.map((type) => (
                            <SelectItem key={type} value={type}>
                              {getHttpParamTypeLabel(t, type)}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <div className="flex items-center gap-1">
                        <Switch
                          checked={param.required}
                          onCheckedChange={(checked) => updateParameter(index, { required: checked })}
                        />
                        <span className="text-xs text-muted-foreground">{t('httpDialog.required')}</span>
                      </div>
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => removeParameter(index)}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                    <Input
                      placeholder={t('httpDialog.paramDescription')}
                      value={param.description || ''}
                      onChange={(e) => updateParameter(index, { description: e.target.value })}
                      className="text-sm"
                    />
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* 启用状态 */}
          <div className="flex items-center justify-between">
            <Label htmlFor="enabled">{t('form.enabled')}</Label>
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
