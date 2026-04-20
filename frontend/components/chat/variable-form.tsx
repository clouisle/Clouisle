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
import { ApiError, type VariableDefinition as AgentVariableDefinition } from '@/lib/api'
import { clearValidationError, getValidationSummaryEntries,
  formatValidationSummaryMessage
} from '@/lib/validation'
import { Upload, X, FileIcon, ImageIcon } from 'lucide-react'
import { uploadApi } from '@/lib/api/upload'

type VariableFieldErrors = Record<string, string>
type VariableDefinition = Omit<AgentVariableDefinition, 'type'> & { type: AgentVariableDefinition['type'] | 'boolean' }

interface VariableFormProps {
  variables: VariableDefinition[]
  values: Record<string, unknown>
  onChange: (values: Record<string, unknown>) => void
  onSubmit?: () => void
  className?: string
  fieldErrors?: VariableFieldErrors
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
          compact
        />
      ))}

      {onSubmit && (
        <Button type="submit" className="w-full" disabled={!isValid}>
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
}

function VariableField({ variable, value, error, onChange, compact = false }: VariableFieldProps) {
  const t = useTranslations('chat.variables')
  const tCommon = useTranslations('common')
  const label = variable.label || variable.name
  const isRequired = variable.required

  // Initialize with default value if provided
  React.useEffect(() => {
    if (value === undefined && variable.default !== undefined && variable.default !== null) {
      if (variable.type === 'checkbox' || variable.type === 'boolean') {
        onChange(variable.default === 'true')
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
          <Input
            value={(value as string) ?? ''}
            onChange={(e) => onChange(e.target.value)}
            placeholder={variable.description || label}
            maxLength={variable.maxLength ?? undefined}
            className={inputClassName}
            aria-invalid={!!error}
          />
        )

      case 'paragraph':
        return (
          <Textarea
            value={(value as string) ?? ''}
            onChange={(e) => onChange(e.target.value)}
            placeholder={variable.description || label}
            maxLength={variable.maxLength ?? undefined}
            rows={compact ? 2 : 3}
            className={compact ? 'text-xs min-h-12' : ''}
            aria-invalid={!!error}
          />
        )

      case 'select':
        return (
          <Select
            value={(value as string) ?? ''}
            onValueChange={(v) => onChange(v)}
          >
            <SelectTrigger className={selectTriggerClassName} aria-invalid={!!error}>
              <SelectValue>
                {(value as string) || t('selectPlaceholder')}
              </SelectValue>
            </SelectTrigger>
            <SelectContent>
              {(variable.options || []).map((option) => (
                <SelectItem key={option} value={option} className={compact ? 'text-xs' : ''}>
                  {option}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )

      case 'number':
        return (
          <Input
            type="number"
            value={(value as number) ?? ''}
            onChange={(e) => onChange(e.target.value ? Number(e.target.value) : '')}
            placeholder={variable.description || label}
            min={variable.min ?? undefined}
            max={variable.max ?? undefined}
            className={inputClassName}
            aria-invalid={!!error}
          />
        )

      case 'checkbox':
        return (
          <div className="flex items-center space-x-1.5">
            <Checkbox
              id={`var-${variable.name}`}
              checked={(value as boolean) ?? false}
              onCheckedChange={(checked) => onChange(checked)}
              className={compact ? 'h-3.5 w-3.5' : ''}
            />
            {variable.description && (
              <label
                htmlFor={`var-${variable.name}`}
                className={cn("text-muted-foreground cursor-pointer", compact ? "text-xs" : "text-sm")}
              >
                {variable.description}
              </label>
            )}
          </div>
        )

      case 'boolean':
        return (
          <Select
            value={typeof value === 'boolean' ? String(value) : ((value as string) || 'false')}
            onValueChange={(v) => onChange(v === 'true')}
          >
            <SelectTrigger className={selectTriggerClassName} aria-invalid={!!error}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="true" className={compact ? 'text-xs' : ''}>{tCommon('yes')}</SelectItem>
              <SelectItem value="false" className={compact ? 'text-xs' : ''}>{tCommon('no')}</SelectItem>
            </SelectContent>
          </Select>
        )

      case 'array':
        return (
          <Textarea
            value={Array.isArray(value) ? JSON.stringify(value, null, 2) : (value as string) ?? ''}
            onChange={(e) => {
              const text = e.target.value
              try {
                const parsed = JSON.parse(text)
                if (Array.isArray(parsed)) {
                  onChange(parsed)
                } else {
                  onChange(text)
                }
              } catch {
                onChange(text)
              }
            }}
            placeholder={variable.description || t('arrayPlaceholder')}
            rows={compact ? 3 : 4}
            className={compact ? 'text-xs min-h-16 font-mono' : 'font-mono'}
            aria-invalid={!!error}
          />
        )

      case 'object':
        return (
          <Textarea
            value={typeof value === 'object' && value !== null ? JSON.stringify(value, null, 2) : (value as string) ?? ''}
            onChange={(e) => {
              const text = e.target.value
              try {
                const parsed = JSON.parse(text)
                if (typeof parsed === 'object' && parsed !== null && !Array.isArray(parsed)) {
                  onChange(parsed)
                } else {
                  onChange(text)
                }
              } catch {
                onChange(text)
              }
            }}
            placeholder={variable.description || t('objectPlaceholder')}
            rows={compact ? 3 : 4}
            className={compact ? 'text-xs min-h-16 font-mono' : 'font-mono'}
            aria-invalid={!!error}
          />
        )

      // File upload types
      case 'file':
      case 'image':
        return <FileUploadInput variable={variable} value={value} error={error} onChange={onChange} compact={compact} />

      case 'files':
      case 'images':
        return <MultiFileUploadInput variable={variable} value={value} error={error} onChange={onChange} compact={compact} />

      default:
        return null
    }
  }

  const isUploadField = variable.type === 'file' || variable.type === 'image' || variable.type === 'files' || variable.type === 'images'

  return (
    <div className={compact ? "space-y-0.5" : "space-y-2"}>
      <Label className={cn("flex items-center gap-0.5", compact ? "text-xs font-normal" : "")}>
        {label}
        {isRequired && <span className="text-destructive text-xs">*</span>}
      </Label>
      {renderField()}
      {!isUploadField && <FieldError>{error}</FieldError>}
    </div>
  )
}

/**
 * Hook to manage variable form state
 */
export function useVariableForm(variables: VariableDefinition[]) {
  const tCommon = useTranslations('common')
  const [values, setValues] = React.useState<Record<string, unknown>>(() => {
    const initial: Record<string, unknown> = {}
    variables.forEach((v) => {
      if (v.default !== undefined && v.default !== null) {
        if (v.type === 'checkbox') {
          initial[v.name] = v.default === 'true'
        } else if (v.type === 'number') {
          initial[v.name] = Number(v.default)
        } else {
          initial[v.name] = v.default
        }
      }
    })
    return initial
  })

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
    const initial: Record<string, unknown> = {}
    variables.forEach((v) => {
      if (v.default !== undefined && v.default !== null) {
        if (v.type === 'checkbox') {
          initial[v.name] = v.default === 'true'
        } else if (v.type === 'number') {
          initial[v.name] = Number(v.default)
        } else {
          initial[v.name] = v.default
        }
      }
    })
    setValues(initial)
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
 * Single file upload input component
 */
interface FileUploadInputProps {
  variable: VariableDefinition
  value: unknown
  error?: string
  onChange: (value: unknown) => void
  compact?: boolean
}

function FileUploadInput({ variable, value, error, onChange, compact }: FileUploadInputProps) {
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
  const maxSizeBytes = (variable.fileConfig?.maxSize || (isImage ? 10 : 50)) * 1024 * 1024

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return

    // Validate file size
    if (file.size > maxSizeBytes) {
      const maxSizeMB = maxSizeBytes / (1024 * 1024)
      setUploadError(t('fileTooLarge', { maxSize: maxSizeMB }))
      if (fileInputRef.current) {
        fileInputRef.current.value = ''
      }
      return
    }

    setUploadError(null)
    setUploading(true)
    try {
      const result = await uploadApi.uploadFile(file, 'workflow-input')
      setUploadError(null)
      onChange(result.url)
    } catch (error) {
      console.error('File upload failed:', error)
      setUploadError(getUploadValidationMessage(error, t('fileUploadFailed'), tCommon))
    } finally {
      setUploading(false)
      if (fileInputRef.current) {
        fileInputRef.current.value = ''
      }
    }
  }

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
        disabled={uploading}
      />

      {!fileUrl ? (
        <Button
          type="button"
          variant="outline"
          size={compact ? "sm" : "default"}
          onClick={() => fileInputRef.current?.click()}
          disabled={uploading}
          className="w-full"
          aria-invalid={!!(error || uploadError)}
        >
          <Upload className={cn("mr-2", compact ? "h-3 w-3" : "h-4 w-4")} />
          {uploading ? t('uploading') : t('selectFile')}
        </Button>
      ) : (
        <div className={cn(
          "flex items-center gap-2 p-2 border rounded-md bg-muted/30",
          compact && "p-1.5 text-xs"
        )}>
          {isImage ? (
            <ImageIcon className={compact ? "h-3 w-3" : "h-4 w-4"} />
          ) : (
            <FileIcon className={compact ? "h-3 w-3" : "h-4 w-4"} />
          )}
          <span className="flex-1 truncate text-sm">{fileUrl.split('/').pop()}</span>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            onClick={handleRemove}
            className={compact ? "h-5 w-5" : "h-6 w-6"}
          >
            <X className={compact ? "h-3 w-3" : "h-4 w-4"} />
          </Button>
        </div>
      )}
      <FieldError>{uploadError || error}</FieldError>
    </div>
  )
}

/**
 * Multiple files upload input component
 */
interface MultiFileUploadInputProps {
  variable: VariableDefinition
  value: unknown
  error?: string
  onChange: (value: unknown) => void
  compact?: boolean
}

function MultiFileUploadInput({ variable, value, error, onChange, compact }: MultiFileUploadInputProps) {
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
  const maxSizeBytes = (variable.fileConfig?.maxSize || 50) * 1024 * 1024
  const maxFiles = variable.fileConfig?.maxFiles || 5

  const fileUrls = Array.isArray(value) ? value.filter((v): v is string => typeof v === 'string') : []

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || [])
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
      const maxSizeMB = maxSizeBytes / (1024 * 1024)
      setUploadError(t('fileTooLarge', { maxSize: maxSizeMB }))
      if (fileInputRef.current) {
        fileInputRef.current.value = ''
      }
      return
    }

    setUploadError(null)
    setUploading(true)
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
      if (fileInputRef.current) {
        fileInputRef.current.value = ''
      }
    }
  }

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
        disabled={uploading}
      />

      <Button
        type="button"
        variant="outline"
        size={compact ? "sm" : "default"}
        onClick={() => fileInputRef.current?.click()}
        disabled={uploading || fileUrls.length >= maxFiles}
        className="w-full"
        aria-invalid={!!(error || uploadError)}
      >
        <Upload className={cn("mr-2", compact ? "h-3 w-3" : "h-4 w-4")} />
        {uploading ? t('uploading') : t('selectFiles')}
        {fileUrls.length > 0 && ` (${fileUrls.length}/${maxFiles})`}
      </Button>

      {fileUrls.length > 0 && (
        <div className={cn("space-y-1", compact && "space-y-0.5")}>
          {fileUrls.map((url, index) => (
            <div
              key={index}
              className={cn(
                "flex items-center gap-2 p-2 border rounded-md bg-muted/30",
                compact && "p-1.5 text-xs"
              )}
            >
              {isImages ? (
                <ImageIcon className={compact ? "h-3 w-3" : "h-4 w-4"} />
              ) : (
                <FileIcon className={compact ? "h-3 w-3" : "h-4 w-4"} />
              )}
              <span className="flex-1 truncate text-sm">{url.split('/').pop()}</span>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                onClick={() => handleRemove(index)}
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
