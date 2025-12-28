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
        label: 'Tavily API Key',
        placeholder: 'tvly-xxxxxxxxxx',
        description: 'Get your API key from Tavily',
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
      setShowPasswords({})
    }
    
    // 当 dialog 关闭时重置 ref
    if (!open) {
      prevToolIdRef.current = null
    }
  }, [tool, open])

  const handleSave = async () => {
    setIsLoading(true)
    try {
      await onSave(config)
      onOpenChange(false)
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
          {fields.map((field) => (
            <div key={field.key} className="space-y-2">
              <Label htmlFor={field.key} className="flex items-center gap-2">
                {field.label}
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
                  onChange={(e) =>
                    setConfig((prev) => ({ ...prev, [field.key]: e.target.value }))
                  }
                  className="pr-10"
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
              {field.description && (
                <p className="text-xs text-muted-foreground">{field.description}</p>
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
