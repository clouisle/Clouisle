'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
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
import type { VariableDefinition } from '@/lib/api'

interface VariableFormProps {
  variables: VariableDefinition[]
  values: Record<string, unknown>
  onChange: (values: Record<string, unknown>) => void
  onSubmit?: () => void
  className?: string
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
