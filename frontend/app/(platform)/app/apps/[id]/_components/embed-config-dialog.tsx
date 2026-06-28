'use client'

import * as React from 'react'
import Link from 'next/link'
import { useTranslations } from 'next-intl'
import { Copy, Check } from 'lucide-react'
import { toast } from 'sonner'
import type { Agent, AgentUpdateInput } from '@/lib/api'
import {
  agentsApi,
  clearValidationError,
  getValidationSummaryEntries,
  normalizeValidationErrors,
} from '@/lib/api'
import { workflowsApi, type Workflow, type WorkflowUpdateInput } from '@/lib/api/workflows'
import { Button, buttonVariants } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { FieldError } from '@/components/ui/field'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { formatValidationSummaryMessage } from '@/lib/validation'


interface EmbedConfigDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  agent?: Agent
  workflow?: Workflow
  onUpdate: (updated: Agent | Workflow) => void
  updateAgent?: (id: string, data: AgentUpdateInput) => Promise<Agent>
  updateWorkflow?: (id: string, data: WorkflowUpdateInput) => Promise<Workflow>
}

interface EmbedConfig {
  enabled: boolean
  allowed_domains: string[]
  theme: { mode: string; primary_color: string | null }
  bubble: { position: string; icon: string | null; greeting: string | null }
}

const DEFAULT_EMBED_CONFIG: EmbedConfig = {
  enabled: false,
  allowed_domains: [],
  theme: { mode: 'auto', primary_color: null },
  bubble: { position: 'bottom-right', icon: null, greeting: null },
}

function parseEmbedConfig(raw: Record<string, unknown> | undefined): EmbedConfig {
  if (!raw || Object.keys(raw).length === 0) return { ...DEFAULT_EMBED_CONFIG }
  return {
    enabled: (raw.enabled as boolean) || false,
    allowed_domains: (raw.allowed_domains as string[]) || [],
    theme: {
      mode: ((raw.theme as Record<string, unknown>)?.mode as string) || 'auto',
      primary_color: ((raw.theme as Record<string, unknown>)?.primary_color as string) || null,
    },
    bubble: {
      position: ((raw.bubble as Record<string, unknown>)?.position as string) || 'bottom-right',
      icon: ((raw.bubble as Record<string, unknown>)?.icon as string) || null,
      greeting: ((raw.bubble as Record<string, unknown>)?.greeting as string) || null,
    },
  }
}

export function EmbedConfigDialog({
  open,
  onOpenChange,
  agent,
  workflow,
  onUpdate,
  updateAgent = agentsApi.updateAgent,
  updateWorkflow = workflowsApi.updateWorkflow,
}: EmbedConfigDialogProps) {
  const t = useTranslations('embed.settings')

  const target = agent || workflow
  const targetType = agent ? 'agent' : 'workflow'
  const targetId = target?.id || ''
  const targetStatus = agent?.status || workflow?.status || 'draft'
  const targetEmbedConfig = (agent?.embed_config || workflow?.embed_config) as Record<string, unknown> | undefined

  const [config, setConfig] = React.useState<EmbedConfig>(() =>
    parseEmbedConfig(targetEmbedConfig)
  )
  const [apiKeyInput, setApiKeyInput] = React.useState<string>('')
  const [selectedMode, setSelectedMode] = React.useState<string>('bubble')
  const [fieldErrors, setFieldErrors] = React.useState<Record<string, string>>({})
  const [saving, setSaving] = React.useState(false)
  const [copied, setCopied] = React.useState(false)
  const [domainsText, setDomainsText] = React.useState(
    config.allowed_domains.join(', ')
  )

  const summaryEntries = React.useMemo(
    () => getValidationSummaryEntries(fieldErrors, ['allowed_domains', 'theme.primary_color', 'bubble.greeting', 'apiKey']),
    [fieldErrors]
  )

  // Reset config when target changes
  React.useEffect(() => {
    const parsed = parseEmbedConfig(targetEmbedConfig)
    setConfig(parsed)
    setDomainsText(parsed.allowed_domains.join(', '))
    setFieldErrors({})
  }, [targetEmbedConfig])

  const handleSave = async () => {
    setFieldErrors({})

    const domains = domainsText
      .split(/[,\n]/)
      .map(d => d.trim())
      .filter(Boolean)

    const invalidDomain = domains.find((domain) => !/^(https?:\/\/)?(\*\.)?([a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}(:\d+)?$/i.test(domain))
    if (invalidDomain) {
      setFieldErrors({ allowed_domains: t('invalidDomain', { value: invalidDomain }) })
      return
    }

    if (config.theme.primary_color && !/^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/.test(config.theme.primary_color)) {
      setFieldErrors({ 'theme.primary_color': t('invalidPrimaryColor') })
      return
    }

    setSaving(true)
    try {
      const embedConfig = {
        ...config,
        allowed_domains: domains,
      }

      const updated = targetType === 'agent'
        ? await updateAgent(targetId, { embed_config: embedConfig })
        : await updateWorkflow(targetId, { embed_config: embedConfig })
      onUpdate(updated)
      toast.success(t('save'))
      onOpenChange(false)
    } catch (error) {
      const errors = normalizeValidationErrors(error)
      if (Object.keys(errors).length > 0) {
        setFieldErrors(errors)
      }
    } finally {
      setSaving(false)
    }
  }

  const iframeUrl = React.useMemo(() => {
    const origin = typeof window !== 'undefined' ? window.location.origin : 'https://your-clouisle.com'
    const tokenValue = apiKeyInput.trim() || 'YOUR_API_KEY'
    const params = new URLSearchParams()
    params.set('token', tokenValue)
    if (config.theme.mode !== 'auto') params.set('theme', config.theme.mode)
    if (config.theme.primary_color) params.set('color', config.theme.primary_color)
    params.set('mode', selectedMode)
    return `${origin}/embed/${targetType}/${targetId}?${params.toString()}`
  }, [targetId, targetType, apiKeyInput, selectedMode, config])

  const codeSnippet = React.useMemo(() => {
    const origin = typeof window !== 'undefined' ? window.location.origin : 'https://your-clouisle.com'
    const tokenValue = apiKeyInput.trim() || 'YOUR_API_KEY'

    // Fullscreen / Mobile: plain iframe tag
    if (selectedMode === 'fullscreen') {
      return `<iframe\n  src="${iframeUrl}"\n  style="width: 100%; height: 100%; border: none;"\n  allow="clipboard-write"\n></iframe>`
    }
    if (selectedMode === 'mobile') {
      return `<iframe\n  src="${iframeUrl}"\n  style="position: fixed; top: 0; left: 0; width: 100%; height: 100%; border: none; z-index: 9999;"\n  allow="clipboard-write"\n></iframe>`
    }

    // Bubble: JS SDK (needs JS for floating button)
    const lines = [
      `<script src="${origin}/embed.js"></script>`,
      '<script>',
      '  Clouisle.init({',
      `    type: '${targetType}',`,
      `    id: '${targetId}',`,
      `    token: '${tokenValue}',`,
      `    mode: 'bubble',`,
    ]
    if (config.theme.mode !== 'auto') {
      lines.push(`    theme: '${config.theme.mode}',`)
    }
    if (config.theme.primary_color) {
      lines.push(`    primaryColor: '${config.theme.primary_color}',`)
    }
    lines.push(`    position: '${config.bubble.position}',`)
    if (config.bubble.greeting) {
      lines.push(`    greeting: '${config.bubble.greeting}',`)
    }
    lines.push('  });')
    lines.push('</script>')
    return lines.join('\n')
  }, [targetId, targetType, apiKeyInput, selectedMode, config, iframeUrl])

  const handleCopy = () => {
    navigator.clipboard.writeText(codeSnippet)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const isPublished = targetStatus === 'published'

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{t('title')}</DialogTitle>
          <DialogDescription>{t('description')}</DialogDescription>
        </DialogHeader>

        {!isPublished && (
          <div className="rounded-md bg-yellow-50 dark:bg-yellow-950/20 p-3 text-sm text-yellow-800 dark:text-yellow-200">
            {t('requiresPublish')}
          </div>
        )}

        <div className="space-y-6">
          {summaryEntries.length > 0 && (
            <div className="rounded-md border border-destructive/30 bg-destructive/5 p-3 space-y-1">
              {summaryEntries.map(([field, message]) => (
                <FieldError key={field}>
                  {formatValidationSummaryMessage(field, message)}
                </FieldError>
              ))}
            </div>
          )}

          {/* Enable toggle */}
          <div className="flex items-center justify-between">
            <div>
              <Label>{t('enabled')}</Label>
              <p className="text-xs text-muted-foreground mt-0.5">{t('enabledDescription')}</p>
            </div>
            <Switch
              checked={config.enabled}
              onCheckedChange={v => setConfig(prev => ({ ...prev, enabled: v }))}
              disabled={!isPublished}
            />
          </div>

          {config.enabled && (
            <>
              {/* Allowed domains */}
              <div className="space-y-2">
                <Label>{t('allowedDomains')}</Label>
                <Textarea
                  value={domainsText}
                  onChange={e => {
                    setDomainsText(e.target.value)
                    setFieldErrors((prev) => clearValidationError(prev, 'allowed_domains'))
                  }}
                  placeholder={t('allowedDomainsPlaceholder')}
                  rows={2}
                  className="text-sm"
                  aria-invalid={!!fieldErrors.allowed_domains}
                />
                <FieldError>{fieldErrors.allowed_domains}</FieldError>
                <p className="text-xs text-muted-foreground">{t('allowedDomainsDescription')}</p>
              </div>

              {/* Theme */}
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label>{t('theme')}</Label>
                  <Select
                    value={config.theme.mode}
                    onValueChange={v => setConfig(prev => ({
                      ...prev,
                      theme: { ...prev.theme, mode: v || 'auto' },
                    }))}
                  >
                    <SelectTrigger>
                      <SelectValue>
                        {config.theme.mode === 'auto' && t('themeAuto')}
                        {config.theme.mode === 'light' && t('themeLight')}
                        {config.theme.mode === 'dark' && t('themeDark')}
                      </SelectValue>
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="auto">{t('themeAuto')}</SelectItem>
                      <SelectItem value="light">{t('themeLight')}</SelectItem>
                      <SelectItem value="dark">{t('themeDark')}</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label>{t('primaryColor')}</Label>
                  <div className="flex gap-2">
                    <Input
                      type="color"
                      value={config.theme.primary_color || '#6366f1'}
                      onChange={e => {
                        setConfig(prev => ({
                          ...prev,
                          theme: { ...prev.theme, primary_color: e.target.value },
                        }))
                        setFieldErrors((prev) => clearValidationError(prev, 'theme.primary_color'))
                      }}
                      className="w-12 h-9 p-1 cursor-pointer"
                    />
                    <Input
                      value={config.theme.primary_color || ''}
                      onChange={e => {
                        setConfig(prev => ({
                          ...prev,
                          theme: { ...prev.theme, primary_color: e.target.value || null },
                        }))
                        setFieldErrors((prev) => clearValidationError(prev, 'theme.primary_color'))
                      }}
                      placeholder="#6366f1"
                      className="flex-1"
                      aria-invalid={!!fieldErrors['theme.primary_color']}
                    />
                  </div>
                  <FieldError>{fieldErrors['theme.primary_color']}</FieldError>
                </div>
              </div>

              {/* Bubble settings */}
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label>{t('bubblePosition')}</Label>
                  <Select
                    value={config.bubble.position}
                    onValueChange={v => setConfig(prev => ({
                      ...prev,
                      bubble: { ...prev.bubble, position: v || 'bottom-right' },
                    }))}
                  >
                    <SelectTrigger>
                      <SelectValue>
                        {config.bubble.position === 'bottom-right' && t('bottomRight')}
                        {config.bubble.position === 'bottom-left' && t('bottomLeft')}
                      </SelectValue>
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="bottom-right">{t('bottomRight')}</SelectItem>
                      <SelectItem value="bottom-left">{t('bottomLeft')}</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label>{t('bubbleGreeting')}</Label>
                  <Input
                    value={config.bubble.greeting || ''}
                    onChange={e => setConfig(prev => ({
                      ...prev,
                      bubble: { ...prev.bubble, greeting: e.target.value || null },
                    }))}
                    placeholder={t('bubbleGreetingPlaceholder')}
                  />
                </div>
              </div>

              {/* Code snippet */}
              <div className="space-y-3">
                <Label>{t('codeSnippet')}</Label>

                {/* API Key input */}
                <div className="space-y-2">
                  <div className="flex items-center justify-between gap-3">
                    <Label className="text-xs text-muted-foreground">{t('apiKey')}</Label>
                    <Link
                      href="/app/api-keys"
                      target="_blank"
                      rel="noopener noreferrer"
                      className={buttonVariants({ variant: 'outline', size: 'xs' })}
                    >
                      {t('manageApiKeys')}
                    </Link>
                  </div>
                  <Input
                    type="password"
                    value={apiKeyInput}
                    onChange={e => {
                      setApiKeyInput(e.target.value)
                      setFieldErrors((prev) => clearValidationError(prev, 'apiKey'))
                    }}
                    placeholder="clou_xxxxxxxxxxxx"
                    className="font-mono text-sm"
                    aria-invalid={!!fieldErrors.apiKey}
                  />
                  <FieldError>{fieldErrors.apiKey}</FieldError>
                  <p className="text-xs text-muted-foreground">{t('apiKeyDescription')}</p>
                </div>

                {/* Mode tabs */}
                <Tabs value={selectedMode} onValueChange={setSelectedMode}>
                  <TabsList>
                    <TabsTrigger value="bubble">{t('modeBubble')}</TabsTrigger>
                    <TabsTrigger value="fullscreen">{t('modeFullscreen')}</TabsTrigger>
                    <TabsTrigger value="mobile">{t('modeMobile')}</TabsTrigger>
                  </TabsList>
                </Tabs>

                {/* Code block */}
                <div className="relative">
                  <pre className="rounded-md bg-muted p-3 text-xs overflow-x-auto max-w-full">
                    <code className="break-all whitespace-pre-wrap">{codeSnippet}</code>
                  </pre>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="absolute top-2 right-2 h-7 w-7"
                    onClick={handleCopy}
                  >
                    {copied ? (
                      <Check className="h-3.5 w-3.5 text-green-500" />
                    ) : (
                      <Copy className="h-3.5 w-3.5" />
                    )}
                  </Button>
                </div>
              </div>
            </>
          )}

          {/* Save button */}
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => onOpenChange(false)}>
              {t('preview')}
            </Button>
            <Button onClick={handleSave} disabled={saving || !isPublished}>
              {t('save')}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
