'use client'

import { useState, useEffect, useRef } from 'react'
import { useTranslations } from 'next-intl'
import { Loader2, Eye, EyeOff, ExternalLink } from 'lucide-react'
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
import { FieldError } from '@/components/ui/field'
import {
  clearValidationError,
  getValidationSummaryEntries,
  normalizeValidationErrors,
  formatValidationSummaryMessage
} from '@/lib/validation'
import { Tool } from '@/lib/api/tools'

interface ToolConfigDialogProps {
  tool: Tool | null
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

  const [config, setConfig] = useState<Record<string, string>>({})
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const [showPasswords, setShowPasswords] = useState<Record<string, boolean>>({})
  const [isLoading, setIsLoading] = useState(false)
  
  // 使用 ref 存储 savedConfig 避免无限循环
  const savedConfigRef = useRef(savedConfig)
  savedConfigRef.current = savedConfig
  
  // 跟踪上一次打开时的 tool id
  const prevToolIdRef = useRef<string | undefined | null>(null)

  // 初始化配置 - 只在 dialog 打开且 tool 变化时执行
  useEffect(() => {
    if (tool && open && prevToolIdRef.current !== tool.id) {
      prevToolIdRef.current = tool.id
      const initialConfig: Record<string, string> = {}
      tool.config_fields?.forEach((field) => {
        initialConfig[field] = savedConfigRef.current[field] || ''
      })
      setConfig(initialConfig)
      setFieldErrors({})
      setShowPasswords({})
    }
    
    // 当 dialog 关闭时重置 ref
    if (!open) {
      prevToolIdRef.current = null
    }
  }, [tool, open])

  const handleSave = async () => {
    setFieldErrors({})

    const nextErrors = Object.fromEntries(
      fields
        .filter((field) => !(config[field.key] || '').trim())
        .map((field) => [field.key, tCommon('required')])
    )

    if (Object.keys(nextErrors).length > 0) {
      setFieldErrors(nextErrors)
      return
    }

    setIsLoading(true)
    try {
      await onSave(config)
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

  const configInfo = TOOL_CONFIG_INFO[tool.name]
  const fields = configInfo?.fields || tool.config_fields?.map((key) => ({
    key,
    label: key,
    placeholder: '',
    description: '',
  })) || []
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

          {fields.map((field) => (
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
                  value={config[field.key] || ''}
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
          ))}
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
