'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { Checkbox } from '@/components/ui/checkbox'
import { FieldError } from '@/components/ui/field'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { cn } from '@/lib/utils'
import { ApiError } from '@/lib/api'
import type { RunVariableDefinition } from '@/lib/utils/extract-variables'
import { clearValidationError, getValidationSummaryEntries,
  formatValidationSummaryMessage
} from '@/lib/validation'
import { Upload, X, FileIcon } from 'lucide-react'
import { uploadApi } from '@/lib/api/upload'
import { GENERAL_UPLOAD_MAX_FILE_SIZE_MB, BYTES_PER_MB } from '@/lib/constants'

type VariableFieldErrors = Record<string, string>
type VariableDefinition = RunVariableDefinition

interface VariableFormProps {
  variables: VariableDefinition[]
  values: Record<string, unknown>
  onChange: (values: Record<string, unknown>) => void
  onSubmit?: () => void
  className?: string
  fieldErrors?: VariableFieldErrors
  /** Keep the existing compact layout by default; workflow forms opt into full size. */
  compact?: boolean
  disabled?: boolean
  onUploadingChange?: (uploading: boolean) => void
}

function getUploadValidationMessage(
  error: unknown,
  fallbackMessage: string,
  tCommon: ReturnType<typeof useTranslations>
): string {
  if (error instanceof ApiError && error.code === 1001) {
    const payload = error.data as { allowed?: string[] } | undefined
    const allowed = payload?.allowed?.join(', ')
    return allowed
      ? tCommon('invalidFileTypeWithAllowed', { allowed })
      : tCommon('invalidFileType')
  }

  return fallbackMessage
}

function validateVariableValue(
  variable: VariableDefinition,
  value: unknown,
  requiredMessage: string,
  invalidJsonMessage: string
): string | null {
  if (variable.type === 'checkbox') {
    return null
  }

  const isEmpty = value === undefined || value === null || value === ''
  if (isEmpty) {
    return variable.required ? requiredMessage : null
  }

  if (variable.type === 'array') {
    if (Array.isArray(value)) {
      return value.length > 0 || !variable.required ? null : requiredMessage
    }
    if (typeof value === 'string') {
      if (!value.trim()) {
        return variable.required ? requiredMessage : null
      }
      try {
        const parsed = JSON.parse(value)
        if (!Array.isArray(parsed)) {
          return invalidJsonMessage
        }
        if (variable.required && parsed.length === 0) {
          return requiredMessage
        }
        return null
      } catch {
        return invalidJsonMessage
      }
    }
    return invalidJsonMessage
  }

  if (variable.type === 'object') {
    if (typeof value === 'object' && value !== null && !Array.isArray(value)) {
      return Object.keys(value).length > 0 || !variable.required ? null : requiredMessage
    }
    if (typeof value === 'string') {
      if (!value.trim()) {
        return variable.required ? requiredMessage : null
      }
      try {
        const parsed = JSON.parse(value)
        if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
          return invalidJsonMessage
        }
        if (variable.required && Object.keys(parsed).length === 0) {
          return requiredMessage
        }
        return null
      } catch {
        return invalidJsonMessage
      }
    }
    return invalidJsonMessage
  }

  if (variable.type === 'file' || variable.type === 'image') {
    return typeof value === 'string' && value.length > 0 ? null : (variable.required ? requiredMessage : null)
  }

  if (variable.type === 'files' || variable.type === 'images') {
    return Array.isArray(value) && value.length > 0 ? null : (variable.required ? requiredMessage : null)
  }

  return null
}

function getVariableFormErrors(
  variables: VariableDefinition[],
  values: Record<string, unknown>,
  requiredMessage: string,
  invalidJsonMessage: string
): VariableFieldErrors {
  const errors: VariableFieldErrors = {}

  for (const variable of variables) {
    if (variable.hidden) {
      continue
    }

    const error = validateVariableValue(
      variable,
      values[variable.name],
      requiredMessage,
      invalidJsonMessage
    )

    if (error) {
      errors[variable.name] = error
    }
  }

  return errors
}

export function VariableForm({
  variables,
  values,
  onChange,
  onSubmit,
  className,
  fieldErrors,
  compact = true,
  disabled = false,
  onUploadingChange,
}: VariableFormProps) {
  const t = useTranslations('chat.variables')
  const tCommon = useTranslations('common')

  const visibleVariables = variables.filter((v) => !v.hidden)
  const effectiveFieldErrors = React.useMemo(() => fieldErrors ?? {}, [fieldErrors])
  const summaryEntries = React.useMemo(
    () => getValidationSummaryEntries(effectiveFieldErrors, visibleVariables.map((variable) => variable.name)),
    [effectiveFieldErrors, visibleVariables]
  )
  const isValid = React.useMemo(
    () => Object.keys(getVariableFormErrors(variables, values, tCommon('required'), tCommon('invalidJSON'))).length === 0,
    [variables, values, tCommon]
  )

  const updateValue = (name: string, value: unknown) => {
    onChange({ ...values, [name]: value })
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (isValid && onSubmit) {
      onSubmit()
    }
  }

  if (visibleVariables.length === 0) {
    return null
  }

  return (
    <form onSubmit={handleSubmit} className={cn('space-y-3', className)}>
      {summaryEntries.length > 0 && (
        <div className="rounded-md border border-destructive/30 bg-destructive/5 p-3 space-y-1">
          {summaryEntries.map(([field, message]) => (
            <FieldError key={field}>
              {formatValidationSummaryMessage(field, message)}
            </FieldError>
          ))}
        </div>
      )}

      {visibleVariables.map((variable) => (
        <VariableField
          key={variable.name}
          variable={variable}
          value={values[variable.name]}
          error={effectiveFieldErrors[variable.name]}
          onChange={(value) => updateValue(variable.name, value)}
          compact={compact}
          disabled={disabled}
          onUploadingChange={onUploadingChange}
        />
      ))}

      {onSubmit && (
        <Button type="submit" className="w-full" disabled={disabled || !isValid}>
          {t('startChat')}
        </Button>
      )}
    </form>
  )
}

interface VariableFieldProps {
  variable: VariableDefinition
  value: unknown
  error?: string
  onChange: (value: unknown) => void
  compact?: boolean
  disabled?: boolean
  onUploadingChange?: (uploading: boolean) => void
}

function VariableField({
  variable,
  value,
  error,
  onChange,
  compact = false,
  disabled = false,
  onUploadingChange,
}: VariableFieldProps) {
  const t = useTranslations('chat.variables')
  const tCommon = useTranslations('common')
  const label = variable.label || variable.name
  const isRequired = variable.required

  // Initialize with default value if provided
  React.useEffect(() => {
    if (value === undefined && variable.default !== undefined && variable.default !== null) {
      if (variable.type === 'checkbox' || variable.type === 'boolean') {
        onChange(variable.default === 'true' ? true : variable.default)
      } else if (variable.type === 'number') {
        onChange(Number(variable.default))
      } else {
        onChange(variable.default)
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []) // Only run once on mount

  const inputClassName = compact ? 'h-7 text-xs' : ''
  const selectTriggerClassName = compact ? 'h-7 text-xs' : ''

  const renderField = () => {
    switch (variable.type) {
      case 'text':
        return (
          <Input value={(value as string) ?? ''} onChange={(e) => onChange(e.target.value)} placeholder={variable.description || label} maxLength={variable.maxLength ?? undefined} className={inputClassName} aria-invalid={!!error} disabled={disabled} />
        )
      case 'paragraph':
        return (
          <Textarea value={(value as string) ?? ''} onChange={(e) => onChange(e.target.value)} placeholder={variable.description || label} maxLength={variable.maxLength ?? undefined} rows={compact ? 2 : 3} className={compact ? 'text-xs min-h-12' : ''} aria-invalid={!!error} disabled={disabled} />
        )
      case 'select':
        return (
          <Select value={(value as string) ?? ''} onValueChange={onChange} disabled={disabled}>
            <SelectTrigger className={selectTriggerClassName} aria-invalid={!!error}><SelectValue>{(value as string) || t('selectPlaceholder')}</SelectValue></SelectTrigger>
            <SelectContent>{(variable.options || []).map((option) => <SelectItem key={option} value={option} className={compact ? 'text-xs' : ''}>{option}</SelectItem>)}</SelectContent>
          </Select>
        )
      case 'number':
        return <Input type="number" value={(value as number) ?? ''} onChange={(e) => onChange(e.target.value ? Number(e.target.value) : '')} placeholder={variable.description || label} min={variable.min ?? undefined} max={variable.max ?? undefined} className={inputClassName} aria-invalid={!!error} disabled={disabled} />
      case 'checkbox':
        return <div className="flex items-center space-x-1.5"><Checkbox id={`var-${variable.name}`} checked={(value as boolean) ?? false} onCheckedChange={onChange} className={compact ? 'h-3.5 w-3.5' : ''} disabled={disabled} />{variable.description && <label htmlFor={`var-${variable.name}`} className={cn('text-muted-foreground cursor-pointer', compact ? 'text-xs' : 'text-sm')}>{variable.description}</label>}</div>
      case 'boolean':
        return <Select value={typeof value === 'boolean' ? String(value) : ((value as string) || 'false')} onValueChange={(v) => onChange(v === 'true')} disabled={disabled}><SelectTrigger className={selectTriggerClassName} aria-invalid={!!error}><SelectValue /></SelectTrigger><SelectContent><SelectItem value="true" className={compact ? 'text-xs' : ''}>{tCommon('yes')}</SelectItem><SelectItem value="false" className={compact ? 'text-xs' : ''}>{tCommon('no')}</SelectItem></SelectContent></Select>
      case 'array':
        return <Textarea value={Array.isArray(value) ? JSON.stringify(value, null, 2) : (value as string) ?? ''} onChange={(e) => { const text = e.target.value; try { const parsed = JSON.parse(text); onChange(Array.isArray(parsed) ? parsed : text) } catch { onChange(text) } }} placeholder={variable.description || t('arrayPlaceholder')} rows={compact ? 3 : 4} className={compact ? 'text-xs min-h-16 font-mono' : 'font-mono'} aria-invalid={!!error} disabled={disabled} />
      case 'object':
        return <Textarea value={typeof value === 'object' && value !== null ? JSON.stringify(value, null, 2) : (value as string) ?? ''} onChange={(e) => { const text = e.target.value; try { const parsed = JSON.parse(text); onChange(typeof parsed === 'object' && parsed !== null && !Array.isArray(parsed) ? parsed : text) } catch { onChange(text) } }} placeholder={variable.description || t('objectPlaceholder')} rows={compact ? 3 : 4} className={compact ? 'text-xs min-h-16 font-mono' : 'font-mono'} aria-invalid={!!error} disabled={disabled} />
      case 'file':
      case 'image':
        return <FileUploadInput variable={variable} value={value} error={error} onChange={onChange} compact={compact} disabled={disabled} onUploadingChange={onUploadingChange} />
      case 'files':
      case 'images':
        return <MultiFileUploadInput variable={variable} value={value} error={error} onChange={onChange} compact={compact} disabled={disabled} onUploadingChange={onUploadingChange} />
      default:
        return null
    }
  }

  const isUploadField = variable.type === 'file' || variable.type === 'image' || variable.type === 'files' || variable.type === 'images'

  return <div className={compact ? 'space-y-0.5' : 'space-y-2'}><Label className={cn('flex items-center gap-0.5', compact ? 'text-xs font-normal' : '')}>{label}{isRequired && <span className="text-destructive text-xs">*</span>}</Label>{renderField()}{!isUploadField && <FieldError>{error}</FieldError>}</div>
}

function getInitialVariableValues(variables: VariableDefinition[]): Record<string, unknown> {
  return Object.fromEntries(
    variables
      .filter((variable) => variable.default !== undefined && variable.default !== null)
      .map((variable) => {
        if (variable.type === 'checkbox' || variable.type === 'boolean') {
          return [variable.name, variable.default === 'true' ? true : variable.default === 'false' ? false : Boolean(variable.default)]
        }
        if (variable.type === 'number') return [variable.name, Number(variable.default)]
        return [variable.name, variable.default]
      })
  )
}

/**
 * Hook to manage variable form state
 */
export function useVariableForm(variables: VariableDefinition[]) {
  const tCommon = useTranslations('common')
  const [values, setValues] = React.useState<Record<string, unknown>>(() => getInitialVariableValues(variables))

  const [fieldErrors, setFieldErrors] = React.useState<VariableFieldErrors>({})

  const needsInput = React.useMemo(() => {
    return variables.some((v) => {
      if (v.hidden) return false
      if (!v.required) return false
      return v.default === undefined || v.default === null || v.default === ''
    })
  }, [variables])

  const derivedErrors = React.useMemo(
    () => getVariableFormErrors(variables, values, tCommon('required'), tCommon('invalidJSON')),
    [variables, values, tCommon]
  )

  const mergedFieldErrors = React.useMemo(
    () => ({ ...fieldErrors, ...derivedErrors }),
    [fieldErrors, derivedErrors]
  )

  const isValid = Object.keys(mergedFieldErrors).length === 0

  const updateValues = React.useCallback((nextValues: Record<string, unknown>) => {
    setValues(nextValues)
    setFieldErrors((prev) => {
      let nextErrors = prev
      for (const variable of variables) {
        const nextValue = nextValues[variable.name]
        const prevValue = values[variable.name]
        if (nextValue !== prevValue) {
          nextErrors = clearValidationError(nextErrors, variable.name)
        }
      }
      return nextErrors
    })
  }, [variables, values])

  const validate = React.useCallback(() => {
    const nextErrors = getVariableFormErrors(variables, values, tCommon('required'), tCommon('invalidJSON'))
    setFieldErrors(nextErrors)
    return Object.keys(nextErrors).length === 0
  }, [variables, values, tCommon])

  const reset = React.useCallback(() => {
    setValues(getInitialVariableValues(variables))
    setFieldErrors({})
  }, [variables])

  return {
    values,
    setValues: updateValues,
    needsInput,
    isValid,
    fieldErrors: mergedFieldErrors,
    validate,
    reset,
  }
}

/**
 * 文件拖拽状态管理：提供 drag 事件处理器与拖拽中标记。
 * depth 计数避免子元素间移动时拖拽层闪烁。
 */
function useDragDrop(
  onFiles: (files: File[]) => void | Promise<void>,
  enabled: boolean
) {
  const [isDragging, setIsDragging] = React.useState(false)
  const depthRef = React.useRef(0)

  const handleDragEnter = React.useCallback((e: React.DragEvent) => {
    if (!enabled) return
    e.preventDefault()
    depthRef.current += 1
    setIsDragging(true)
  }, [enabled])

  const handleDragOver = React.useCallback((e: React.DragEvent) => {
    if (!enabled) return
    e.preventDefault()
  }, [enabled])

  const handleDragLeave = React.useCallback((e: React.DragEvent) => {
    if (!enabled) return
    e.preventDefault()
    depthRef.current = Math.max(0, depthRef.current - 1)
    if (depthRef.current === 0) setIsDragging(false)
  }, [enabled])

  const handleDrop = React.useCallback(async (e: React.DragEvent) => {
    if (!enabled) return
    e.preventDefault()
    depthRef.current = 0
    setIsDragging(false)
    const files = Array.from(e.dataTransfer?.files || [])
    if (files.length > 0) await onFiles(files)
  }, [enabled, onFiles])

  return { isDragging, handleDragEnter, handleDragOver, handleDragLeave, handleDrop }
}

/**
 * Single file upload input component
 */
export interface FileUploadInputProps {
  variable: VariableDefinition
  value: unknown
  error?: string
  onChange: (value: unknown) => void
  compact?: boolean
  disabled?: boolean
  onUploadingChange?: (uploading: boolean) => void
}

export function FileUploadInput({ variable, value, error, onChange, compact, disabled, onUploadingChange }: FileUploadInputProps) {
  const t = useTranslations('chat.variables')
  const tCommon = useTranslations('common')
  const [uploading, setUploading] = React.useState(false)
  const [uploadError, setUploadError] = React.useState<string | null>(null)
  const fileInputRef = React.useRef<HTMLInputElement>(null)

  const isImage = variable.type === 'image'

  // Get accept attribute from fileConfig or use defaults
  const accept = React.useMemo(() => {
    if (variable.fileConfig?.accept && variable.fileConfig.accept.length > 0) {
      return variable.fileConfig.accept.join(',')
    }
    return isImage ? 'image/*' : '*'
  }, [variable.fileConfig, isImage])

  // Get max file size in bytes (fileConfig is in MB)
  const maxSizeBytes = (variable.fileConfig?.maxSize || GENERAL_UPLOAD_MAX_FILE_SIZE_MB) * BYTES_PER_MB

  const handleFiles = async (files: File[]) => {
    const file = files[0]
    if (!file) return

    // Validate file size
    if (file.size > maxSizeBytes) {
      const maxSizeMB = maxSizeBytes / BYTES_PER_MB
      setUploadError(t('fileTooLarge', { maxSize: maxSizeMB }))
      if (fileInputRef.current) {
        fileInputRef.current.value = ''
      }
      return
    }

    setUploadError(null)
    setUploading(true)
    onUploadingChange?.(true)
    try {
      const result = await uploadApi.uploadFile(file, 'workflow-input')
      setUploadError(null)
      onChange(result.url)
    } catch (error) {
      console.error('File upload failed:', error)
      setUploadError(getUploadValidationMessage(error, t('fileUploadFailed'), tCommon))
    } finally {
      setUploading(false)
      onUploadingChange?.(false)
      if (fileInputRef.current) {
        fileInputRef.current.value = ''
      }
    }
  }

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    return handleFiles(Array.from(e.target.files || []))
  }

  const dragDrop = useDragDrop(handleFiles, !disabled && !uploading)

  const handleRemove = () => {
    setUploadError(null)
    onChange(null)
    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
  }

  const fileUrl = typeof value === 'string' ? value : null

  return (
    <div className={cn("space-y-1.5", compact && "space-y-1")}>
      <input
        ref={fileInputRef}
        type="file"
        accept={accept}
        onChange={handleFileSelect}
        className="hidden"
        disabled={disabled || uploading}
      />

      <div
        className={cn("relative rounded-md", compact && "rounded-sm")}
        onDragEnter={dragDrop.handleDragEnter}
        onDragOver={dragDrop.handleDragOver}
        onDragLeave={dragDrop.handleDragLeave}
        onDrop={dragDrop.handleDrop}
      >
        {dragDrop.isDragging && (
          <div className="absolute inset-0 z-10 flex items-center justify-center rounded-md border-2 border-dashed border-primary bg-background/90 backdrop-blur-sm text-xs font-medium text-primary">
            {isImage ? t('dropImages') : t('dropFiles')}
          </div>
        )}

        {!fileUrl ? (
          <Button
            type="button"
            variant="outline"
            size={compact ? "sm" : "default"}
            onClick={() => fileInputRef.current?.click()}
            disabled={disabled || uploading}
            className="w-full"
            aria-invalid={!!(error || uploadError)}
          >
            <Upload className={cn("mr-2", compact ? "h-3 w-3" : "h-4 w-4")} />
            {uploading ? t('uploading') : (isImage ? t('selectImage') : t('selectFile'))}
          </Button>
        ) : (
          <div className={cn(
            "flex items-center gap-2 p-2 border rounded-md bg-muted/30",
            compact && "p-1.5 text-xs"
          )}>
            {isImage ? (
              <img
                src={fileUrl}
                alt=""
                className={cn("rounded-md border object-cover", compact ? "h-8 w-8" : "h-12 w-12")}
              />
            ) : (
              <FileIcon className={compact ? "h-3 w-3" : "h-4 w-4"} />
            )}
            <span className="flex-1 truncate text-sm">{fileUrl.split('/').pop()}</span>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              onClick={handleRemove}
              disabled={disabled}
              className={compact ? "h-5 w-5" : "h-6 w-6"}
            >
              <X className={compact ? "h-3 w-3" : "h-4 w-4"} />
            </Button>
          </div>
        )}
      </div>
      <FieldError>{uploadError || error}</FieldError>
    </div>
  )
}

/**
 * Multiple files upload input component
 */
export interface MultiFileUploadInputProps {
  variable: VariableDefinition
  value: unknown
  error?: string
  onChange: (value: unknown) => void
  compact?: boolean
  disabled?: boolean
  onUploadingChange?: (uploading: boolean) => void
}

export function MultiFileUploadInput({ variable, value, error, onChange, compact, disabled, onUploadingChange }: MultiFileUploadInputProps) {
  const t = useTranslations('chat.variables')
  const tCommon = useTranslations('common')
  const [uploading, setUploading] = React.useState(false)
  const [uploadError, setUploadError] = React.useState<string | null>(null)
  const fileInputRef = React.useRef<HTMLInputElement>(null)

  const isImages = variable.type === 'images'

  // Get accept attribute from fileConfig or use defaults
  const accept = React.useMemo(() => {
    if (variable.fileConfig?.accept && variable.fileConfig.accept.length > 0) {
      return variable.fileConfig.accept.join(',')
    }
    return isImages ? 'image/*' : '*'
  }, [variable.fileConfig, isImages])

  // Get max file size in bytes (fileConfig is in MB)
  const maxSizeBytes = (variable.fileConfig?.maxSize || GENERAL_UPLOAD_MAX_FILE_SIZE_MB) * BYTES_PER_MB
  const maxFiles = variable.fileConfig?.maxFiles || 5

  const fileUrls = Array.isArray(value) ? value.filter((v): v is string => typeof v === 'string') : []

  const handleFiles = async (files: File[]) => {
    if (files.length === 0) return

    // Check max files limit
    if (fileUrls.length + files.length > maxFiles) {
      setUploadError(t('tooManyFiles', { maxFiles }))
      if (fileInputRef.current) {
        fileInputRef.current.value = ''
      }
      return
    }

    // Validate file sizes
    const oversizedFiles = files.filter(f => f.size > maxSizeBytes)
    if (oversizedFiles.length > 0) {
      const maxSizeMB = maxSizeBytes / BYTES_PER_MB
      setUploadError(t('fileTooLarge', { maxSize: maxSizeMB }))
      if (fileInputRef.current) {
        fileInputRef.current.value = ''
      }
      return
    }

    setUploadError(null)
    setUploading(true)
    onUploadingChange?.(true)
    try {
      const uploadPromises = files.map(file => uploadApi.uploadFile(file, 'workflow-input'))
      const results = await Promise.all(uploadPromises)
      const newUrls = results.map(r => r.url)
      setUploadError(null)
      onChange([...fileUrls, ...newUrls])
    } catch (error) {
      console.error('File upload failed:', error)
      setUploadError(getUploadValidationMessage(error, t('fileUploadFailed'), tCommon))
    } finally {
      setUploading(false)
      onUploadingChange?.(false)
      if (fileInputRef.current) {
        fileInputRef.current.value = ''
      }
    }
  }

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    return handleFiles(Array.from(e.target.files || []))
  }

  const dragDrop = useDragDrop(handleFiles, !disabled && !uploading && fileUrls.length < maxFiles)

  const handleRemove = (index: number) => {
    setUploadError(null)
    const newUrls = fileUrls.filter((_, i) => i !== index)
    onChange(newUrls.length > 0 ? newUrls : null)
  }

  return (
    <div className={cn("space-y-1.5", compact && "space-y-1")}>
      <input
        ref={fileInputRef}
        type="file"
        accept={accept}
        multiple
        onChange={handleFileSelect}
        className="hidden"
        disabled={disabled || uploading}
      />

      <div
        className={cn("relative rounded-md", compact && "rounded-sm")}
        onDragEnter={dragDrop.handleDragEnter}
        onDragOver={dragDrop.handleDragOver}
        onDragLeave={dragDrop.handleDragLeave}
        onDrop={dragDrop.handleDrop}
      >
        {dragDrop.isDragging && (
          <div className="absolute inset-0 z-10 flex items-center justify-center rounded-md border-2 border-dashed border-primary bg-background/90 backdrop-blur-sm text-xs font-medium text-primary">
            {isImages ? t('dropImages') : t('dropFiles')}
          </div>
        )}

        <Button
          type="button"
          variant="outline"
          size={compact ? "sm" : "default"}
          onClick={() => fileInputRef.current?.click()}
          disabled={disabled || uploading || fileUrls.length >= maxFiles}
          className="w-full"
          aria-invalid={!!(error || uploadError)}
        >
          <Upload className={cn("mr-2", compact ? "h-3 w-3" : "h-4 w-4")} />
          {uploading ? t('uploading') : (isImages ? t('selectImages') : t('selectFiles'))}
          {fileUrls.length > 0 && ` (${fileUrls.length}/${maxFiles})`}
        </Button>

        {isImages && fileUrls.length > 0 && (
          <div className={cn("flex flex-wrap gap-2 pt-2", compact && "gap-1.5 pt-1.5")}>
            {fileUrls.map((url, index) => (
              <div key={index} className="relative">
                <img
                  src={url}
                  alt=""
                  className={cn(
                    "rounded-md border object-cover",
                    compact ? "h-12 w-12" : "h-16 w-16"
                  )}
                />
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  onClick={() => handleRemove(index)}
                  disabled={disabled}
                  className="absolute -right-1.5 -top-1.5 h-5 w-5 rounded-full border bg-background shadow-sm"
                >
                  <X className="h-3 w-3" />
                </Button>
              </div>
            ))}
          </div>
        )}
      </div>

      {!isImages && fileUrls.length > 0 && (
        <div className={cn("space-y-1", compact && "space-y-0.5")}>
          {fileUrls.map((url, index) => (
            <div
              key={index}
              className={cn(
                "flex items-center gap-2 p-2 border rounded-md bg-muted/30",
                compact && "p-1.5 text-xs"
              )}
            >
              <FileIcon className={compact ? "h-3 w-3" : "h-4 w-4"} />
              <span className="flex-1 truncate text-sm">{url.split('/').pop()}</span>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                onClick={() => handleRemove(index)}
                disabled={disabled}
            className={compact ? "h-5 w-5" : "h-6 w-6"}
              >
                <X className={compact ? "h-3 w-3" : "h-4 w-4"} />
              </Button>
            </div>
          ))}
        </div>
      )}
      <FieldError>{uploadError || error}</FieldError>
    </div>
  )
}
