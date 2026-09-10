'use client'

import { useState, useEffect, useMemo } from 'react'
import { useTranslations } from 'next-intl'
import { Tool, ToolDetail } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Eye, EyeOff, Loader2, ExternalLink } from 'lucide-react'
import { normalizeValidationErrors, clearValidationError, getValidationSummaryEntries, formatValidationSummaryMessage } from '@/lib/validation'
import { FieldError } from '@/components/ui/field'

interface ToolConfigDialogProps {
  tool?: Tool | ToolDetail | null
  open: boolean
  onOpenChange: (open: boolean) => void
  onSave: (config: Record<string, string>) => Promise<void>
  savedConfig?: Record<string, string>
}

// 工具配置说明
const TOOL_CONFIG_INFO: Record<string, {
  fields: Array<{
    key: string
    label: string
    placeholder: string
    description: string
    link?: string
  }>
}> = {
  web_search: {
    fields: [
      {
        key: 'TAVILY_API_KEY',
        label: 'configDialog.tavilyApiKeyLabel',
        placeholder: 'tvly-xxxxxxxxxx',
        description: 'configDialog.tavilyApiKeyDescription',
        link: 'https://tavily.com/',
      },
      {
        key: 'BOCHA_API_KEY',
        label: 'configDialog.bochaApiKeyLabel',
        placeholder: 'sk-xxxxxxxxxx',
        description: 'configDialog.bochaApiKeyDescription',
        link: 'https://bocha.ai/',
      },
    ],
  },
}

export function ToolConfigDialog({
  tool,
  open,
  onOpenChange,
  onSave,
  savedConfig = {},
}: ToolConfigDialogProps) {
  const t = useTranslations('platform.tools')
  const tCommon = useTranslations('common')

  const fields = useMemo(() => (tool?.config_fields?.length
    ? tool.config_fields.map((key) => {
        const found = TOOL_CONFIG_INFO[tool.name]?.fields.find((f) => f.key === key)
        return found || { key, label: key, placeholder: '', description: '' }
      })
    : TOOL_CONFIG_INFO[tool?.name || '']?.fields) || [], [tool?.config_fields, tool?.name])

  const [config, setConfig] = useState<Record<string, string>>({})
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const [showPasswords, setShowPasswords] = useState<Record<string, boolean>>({})
  const [isLoading, setIsLoading] = useState(false)

  const savedConfigKey = useMemo(() => JSON.stringify(savedConfig), [savedConfig])

  useEffect(() => {
    if (!tool || !open) return
    const parsed: Record<string, string> = JSON.parse(savedConfigKey)
    const initial: Record<string, string> = {}
    fields.forEach((f) => {
      initial[f.key] = parsed[f.key] || ''
    })
    setConfig(initial)
    setFieldErrors({})
    setShowPasswords({})
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tool?.name, open, savedConfigKey, fields])

  const handleSave = async () => {
    setFieldErrors({})

    const activeValues: Record<string, string> = {}
    fields.forEach((f) => {
      activeValues[f.key] = config[f.key] !== undefined ? config[f.key] : (savedConfig[f.key] || '')
    })

    const nextErrors = Object.fromEntries(
      fields
        .filter((field) => !(activeValues[field.key] || '').trim())
        .map((field) => [field.key, tCommon('required')])
    )

    if (Object.keys(nextErrors).length > 0) {
      setFieldErrors(nextErrors)
      return
    }

    setIsLoading(true)
    try {
      await onSave(activeValues)
    } catch (error) {
      const errors = normalizeValidationErrors(error)
      if (Object.keys(errors).length > 0) {
        setFieldErrors(errors)
      }
    } finally {
      setIsLoading(false)
    }
  }

  const togglePasswordVisibility = (key: string) => {
    setShowPasswords((prev) => ({ ...prev, [key]: !prev[key] }))
  }

  if (!tool) return null

  const summaryEntries = getValidationSummaryEntries(fieldErrors, fields.map((field) => field.key))

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <span className="text-xl">{tool.icon}</span>
            {t('configDialog.title', { name: tool.display_name })}
          </DialogTitle>
          <DialogDescription>
            {t('configDialog.description')}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          {summaryEntries.length > 0 && (
            <div className="rounded-md border border-destructive/30 bg-destructive/5 p-3 space-y-1">
              {summaryEntries.map(([field, message]) => (
                <FieldError key={field}>
                  {formatValidationSummaryMessage(field, message)}
                </FieldError>
              ))}
            </div>
          )}

          {fields.map((field) => {
            const val = config[field.key] !== undefined ? config[field.key] : (savedConfig[field.key] || '')
            return (
              <div key={field.key} className="space-y-2">
                <Label htmlFor={field.key} className="flex items-center gap-2">
                  {t.has(field.label) ? t(field.label) : field.label}
                  {field.link && (
                    <a
                      href={field.link}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-muted-foreground hover:text-primary"
                    >
                      <ExternalLink className="h-3 w-3" />
                    </a>
                  )}
                </Label>
                <div className="relative">
                  <Input
                    id={field.key}
                    type={showPasswords[field.key] ? 'text' : 'password'}
                    placeholder={field.placeholder}
                    value={val}
                    onChange={(e) => {
                      setConfig((prev) => ({ ...prev, [field.key]: e.target.value }))
                      setFieldErrors((prev) => clearValidationError(prev, field.key))
                    }}
                    className="pr-10"
                    aria-invalid={!!fieldErrors[field.key]}
                  />
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="absolute right-0 top-0 h-full px-3 hover:bg-transparent"
                    onClick={() => togglePasswordVisibility(field.key)}
                  >
                    {showPasswords[field.key] ? (
                      <EyeOff className="h-4 w-4 text-muted-foreground" />
                    ) : (
                      <Eye className="h-4 w-4 text-muted-foreground" />
                    )}
                  </Button>
                </div>
                <FieldError>{fieldErrors[field.key]}</FieldError>
                {field.description && (
                  <p className="text-xs text-muted-foreground">{t.has(field.description) ? t(field.description) : field.description}</p>
                )}
              </div>
            )
          })}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {tCommon('cancel')}
          </Button>
          <Button onClick={handleSave} disabled={isLoading}>
            {isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {tCommon('save')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
