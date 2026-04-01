'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { cn } from '@/lib/utils'
import { ApiError, type VariableDefinition } from '@/lib/api'
import { Upload, X, FileIcon, ImageIcon } from 'lucide-react'
import { uploadApi } from '@/lib/api/upload'

interface VariableFormProps {
  variables: VariableDefinition[]
  values: Record<string, unknown>
  onChange: (values: Record<string, unknown>) => void
  onSubmit?: () => void
  className?: string
}

function showUploadValidationError(error: unknown, fallbackMessage: string, tCommon: ReturnType<typeof useTranslations>) {
  if (error instanceof ApiError && error.code === 1001) {
    const payload = error.data as { allowed?: string[] } | undefined
    const allowed = payload?.allowed?.join(', ')
    toast.error(
      allowed
        ? tCommon('invalidFileTypeWithAllowed', { allowed })
        : tCommon('invalidFileType')
    )
    return
  }

  toast.error(fallbackMessage)
}

export function VariableForm({
  variables,
  values,
  onChange,
  onSubmit,
  className,
}: VariableFormProps) {
  const t = useTranslations('chat.variables')

  // Get visible variables (not hidden)
  const visibleVariables = variables.filter((v) => !v.hidden)

  // Check if all required variables are filled
  const isValid = React.useMemo(() => {
    return visibleVariables
      .filter((v) => v.required)
      .every((v) => {
        const value = values[v.name]
        if (v.type === 'checkbox') {
          return true // Checkbox is always valid
        }
        if (v.type === 'array') {
          // Array is valid if it's a non-empty array or valid JSON string
          if (Array.isArray(value)) {
            return value.length > 0
          }
          if (typeof value === 'string' && value.trim()) {
            try {
              const parsed = JSON.parse(value)
              return Array.isArray(parsed) && parsed.length > 0
            } catch {
              return false
            }
          }
          return false
        }
        if (v.type === 'object') {
          // Object is valid if it's a non-empty object or valid JSON string
          if (typeof value === 'object' && value !== null && !Array.isArray(value)) {
            return Object.keys(value).length > 0
          }
          if (typeof value === 'string' && value.trim()) {
            try {
              const parsed = JSON.parse(value)
              return typeof parsed === 'object' && parsed !== null && !Array.isArray(parsed)
            } catch {
              return false
            }
          }
          return false
        }
        // File types validation
        if (v.type === 'file' || v.type === 'image') {
          return typeof value === 'string' && value.length > 0
        }
        if (v.type === 'files' || v.type === 'images') {
          return Array.isArray(value) && value.length > 0
        }
        return value !== undefined && value !== null && value !== ''
      })
  }, [visibleVariables, values])

  // Update a single variable value
  const updateValue = (name: string, value: unknown) => {
    onChange({ ...values, [name]: value })
  }

  // Handle form submit
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
      {visibleVariables.map((variable) => (
        <VariableField
          key={variable.name}
          variable={variable}
          value={values[variable.name]}
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
  onChange: (value: unknown) => void
  compact?: boolean
}

function VariableField({ variable, value, onChange, compact = false }: VariableFieldProps) {
  const t = useTranslations('chat.variables')
  const label = variable.label || variable.name
  const isRequired = variable.required

  // Initialize with default value if provided
  React.useEffect(() => {
    if (value === undefined && variable.default !== undefined && variable.default !== null) {
      if (variable.type === 'checkbox') {
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
          />
        )

      case 'select':
        return (
          <Select
            value={(value as string) ?? ''}
            onValueChange={(v) => onChange(v)}
          >
            <SelectTrigger className={selectTriggerClassName}>
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

      case 'array':
        return (
          <Textarea
            value={Array.isArray(value) ? JSON.stringify(value, null, 2) : (value as string) ?? ''}
            onChange={(e) => {
              const text = e.target.value
              try {
                // Try to parse as JSON array
                const parsed = JSON.parse(text)
                if (Array.isArray(parsed)) {
                  onChange(parsed)
                } else {
                  // If not an array, store as string for now
                  onChange(text)
                }
              } catch {
                // If invalid JSON, store as string
                onChange(text)
              }
            }}
            placeholder={variable.description || `${label} (JSON array format: ["item1", "item2"])`}
            rows={compact ? 3 : 4}
            className={compact ? 'text-xs min-h-16 font-mono' : 'font-mono'}
          />
        )

      case 'object':
        return (
          <Textarea
            value={typeof value === 'object' && value !== null ? JSON.stringify(value, null, 2) : (value as string) ?? ''}
            onChange={(e) => {
              const text = e.target.value
              try {
                // Try to parse as JSON object
                const parsed = JSON.parse(text)
                if (typeof parsed === 'object' && parsed !== null && !Array.isArray(parsed)) {
                  onChange(parsed)
                } else {
                  // If not an object, store as string for now
                  onChange(text)
                }
              } catch {
                // If invalid JSON, store as string
                onChange(text)
              }
            }}
            placeholder={variable.description || `${label} (JSON object format: {"key": "value"})`}
            rows={compact ? 3 : 4}
            className={compact ? 'text-xs min-h-16 font-mono' : 'font-mono'}
          />
        )

      // File upload types
      case 'file':
      case 'image':
        return <FileUploadInput variable={variable} value={value} onChange={onChange} compact={compact} />

      case 'files':
      case 'images':
        return <MultiFileUploadInput variable={variable} value={value} onChange={onChange} compact={compact} />

      default:
        return null
    }
  }

  return (
    <div className={compact ? "space-y-0.5" : "space-y-2"}>
      <Label className={cn("flex items-center gap-0.5", compact ? "text-xs font-normal" : "")}>
        {label}
        {isRequired && <span className="text-destructive text-xs">*</span>}
      </Label>
      {renderField()}
    </div>
  )
}

/**
 * Hook to manage variable form state
 */
export function useVariableForm(variables: VariableDefinition[]) {
  const [values, setValues] = React.useState<Record<string, unknown>>(() => {
    // Initialize with default values
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

  // Check if form needs to be shown (has visible required variables without default)
  const needsInput = React.useMemo(() => {
    return variables.some((v) => {
      if (v.hidden) return false
      if (!v.required) return false
      // Required and no default value
      return v.default === undefined || v.default === null || v.default === ''
    })
  }, [variables])

  // Check if all required fields are filled
  const isValid = React.useMemo(() => {
    return variables
      .filter((v) => !v.hidden && v.required)
      .every((v) => {
        const value = values[v.name]
        if (v.type === 'checkbox') {
          return true
        }
        if (v.type === 'array') {
          // Array is valid if it's a non-empty array or valid JSON string
          if (Array.isArray(value)) {
            return value.length > 0
          }
          if (typeof value === 'string' && value.trim()) {
            try {
              const parsed = JSON.parse(value)
              return Array.isArray(parsed) && parsed.length > 0
            } catch {
              return false
            }
          }
          return false
        }
        if (v.type === 'object') {
          // Object is valid if it's a non-empty object or valid JSON string
          if (typeof value === 'object' && value !== null && !Array.isArray(value)) {
            return Object.keys(value).length > 0
          }
          if (typeof value === 'string' && value.trim()) {
            try {
              const parsed = JSON.parse(value)
              return typeof parsed === 'object' && parsed !== null && !Array.isArray(parsed)
            } catch {
              return false
            }
          }
          return false
        }
        // File types validation
        if (v.type === 'file' || v.type === 'image') {
          return typeof value === 'string' && value.length > 0
        }
        if (v.type === 'files' || v.type === 'images') {
          return Array.isArray(value) && value.length > 0
        }
        return value !== undefined && value !== null && value !== ''
      })
  }, [variables, values])

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
  }, [variables])

  return {
    values,
    setValues,
    needsInput,
    isValid,
    reset,
  }
}

/**
 * Single file upload input component
 */
interface FileUploadInputProps {
  variable: VariableDefinition
  value: unknown
  onChange: (value: unknown) => void
  compact?: boolean
}

function FileUploadInput({ variable, value, onChange, compact }: FileUploadInputProps) {
  const t = useTranslations('chat.variables')
  const tCommon = useTranslations('common')
  const [uploading, setUploading] = React.useState(false)
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
      alert(t('fileTooLarge', { maxSize: maxSizeMB }))
      if (fileInputRef.current) {
        fileInputRef.current.value = ''
      }
      return
    }

    setUploading(true)
    try {
      const result = await uploadApi.uploadFile(file, 'workflow-input')
      onChange(result.url)
    } catch (error) {
      console.error('File upload failed:', error)
      showUploadValidationError(error, t('fileUploadFailed'), tCommon)
    } finally {
      setUploading(false)
      if (fileInputRef.current) {
        fileInputRef.current.value = ''
      }
    }
  }

  const handleRemove = () => {
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
    </div>
  )
}

/**
 * Multiple files upload input component
 */
interface MultiFileUploadInputProps {
  variable: VariableDefinition
  value: unknown
  onChange: (value: unknown) => void
  compact?: boolean
}

function MultiFileUploadInput({ variable, value, onChange, compact }: MultiFileUploadInputProps) {
  const t = useTranslations('chat.variables')
  const tCommon = useTranslations('common')
  const [uploading, setUploading] = React.useState(false)
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
      alert(t('tooManyFiles', { maxFiles }))
      if (fileInputRef.current) {
        fileInputRef.current.value = ''
      }
      return
    }

    // Validate file sizes
    const oversizedFiles = files.filter(f => f.size > maxSizeBytes)
    if (oversizedFiles.length > 0) {
      const maxSizeMB = maxSizeBytes / (1024 * 1024)
      alert(t('fileTooLarge', { maxSize: maxSizeMB }))
      if (fileInputRef.current) {
        fileInputRef.current.value = ''
      }
      return
    }

    setUploading(true)
    try {
      const uploadPromises = files.map(file => uploadApi.uploadFile(file, 'workflow-input'))
      const results = await Promise.all(uploadPromises)
      const newUrls = results.map(r => r.url)
      onChange([...fileUrls, ...newUrls])
    } catch (error) {
      console.error('File upload failed:', error)
      showUploadValidationError(error, t('fileUploadFailed'), tCommon)
    } finally {
      setUploading(false)
      if (fileInputRef.current) {
        fileInputRef.current.value = ''
      }
    }
  }

  const handleRemove = (index: number) => {
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
    </div>
  )
}
