'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { useRouter } from 'next/navigation'
import { AlertCircle, Loader2, RefreshCw } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import type { Tool } from '@/lib/api/tools'
import { agentsApi, type AgentListItem } from '@/lib/api/agents'
import {
  toolMcpApi,
  type McpCapabilities,
  type McpEnumeration,
  type McpOperation,
  type McpPrompt,
  type McpPromptResult,
  type McpResource,
  type McpResourceContents,
  type McpResourceTemplate,
  type McpResourceSubscriptionOpened,
  type McpSubscriptionCloseReason,
} from '@/lib/api/tool-mcp'
import {
  EMPTY_CONNECTION_BINDING,
  ToolConnectionPicker,
  type ToolConnectionBinding,
} from '@/components/tools/connection-picker'
import { storeMcpDraft } from '@/lib/chat/mcp-draft'
import { ApiError } from '@/lib/api/client'

type BrowseTab = 'resources' | 'templates' | 'prompts'
type BrowseScope = BrowseTab | 'capabilities' | 'preview'

interface BrowserError {
  /** Localized, server-resolved message. ``null`` means a generic fallback. */
  message: string | null
  code?: number
  scope: BrowseScope
}

interface OperationPreview {
  kind: 'resource' | 'prompt'
  title: string
  text: string
  messages?: Array<{ role: string; text: string }>
  binary?: { uri: string; mimeType: string | null }
  truncated?: boolean
  pendingExecutionId?: string
}

interface McpToolBrowserProps {
  tool: Tool | null
  teamId?: string
  open: boolean
  onOpenChange: (open: boolean) => void
}

const MAX_PREVIEW_CHARS = 6000
const POLICY_CONFIGURATION_REQUIRED = 6510
const BROWSE_TABS: BrowseTab[] = ['resources', 'templates', 'prompts']
const UNRESOLVED_TEMPLATE_VARIABLE = /\{[^{}]+\}/

function tabCapability(capabilities: McpCapabilities | null, tab: BrowseTab): boolean {
  if (!capabilities) return false
  if (tab === 'resources') return capabilities.resources === true
  if (tab === 'templates') return capabilities.resource_templates === true
  return capabilities.prompts === true
}

function apiError(error: unknown, scope: BrowseScope): BrowserError {
  if (error instanceof ApiError) return { message: error.message || null, code: error.code, scope }
  return { message: null, scope }
}

function contentText(contents: McpResourceContents[]): { text: string; truncated: boolean } {
  const full = contents
    .map((item) => item.text ?? '')
    .filter(Boolean)
    .join('\n\n')
  return { text: full.slice(0, MAX_PREVIEW_CHARS), truncated: full.length > MAX_PREVIEW_CHARS }
}

function messageText(content: Record<string, unknown>): string {
  if (typeof content.text === 'string') return content.text
  if (content.type === 'text' && typeof content.data === 'string') return content.data
  return ''
}

function draftText(notice: string, body: string): { text: string; truncated: boolean } {
  return {
    text: [notice, '', body.slice(0, MAX_PREVIEW_CHARS)].join('\n'),
    truncated: body.length > MAX_PREVIEW_CHARS,
  }
}

export function McpToolBrowser({ tool, teamId, open, onOpenChange }: McpToolBrowserProps) {
  const t = useTranslations('tools.mcpBrowser')
  const router = useRouter()
  const [tab, setTab] = React.useState<BrowseTab>('resources')
  const [binding, setBinding] = React.useState<ToolConnectionBinding>(EMPTY_CONNECTION_BINDING)
  const [capabilities, setCapabilities] = React.useState<McpCapabilities | null>(null)
  const [isLoading, setIsLoading] = React.useState(false)
  const [error, setError] = React.useState<BrowserError | null>(null)
  const generationRef = React.useRef(0)
  const contentRef = React.useRef<HTMLDivElement>(null)
  const [pending, setPending] = React.useState<{
    kind: BrowseTab | 'capabilities' | 'resource' | 'prompt'
    cursor?: string
    executionId: string
    target?: string
  } | null>(null)
  const [monitor, setMonitor] = React.useState<{
    uri: string
    status: 'connecting' | 'open' | 'closed' | 'pending' | 'error'
    opened?: McpResourceSubscriptionOpened
    updates: number
    reason?: McpSubscriptionCloseReason
    executionId?: string
  } | null>(null)
  const monitorCloseRef = React.useRef<(() => void) | null>(null)

  const [resources, setResources] = React.useState<McpEnumeration<McpResource> | null>(null)
  const [templates, setTemplates] = React.useState<McpEnumeration<McpResourceTemplate> | null>(null)
  const [prompts, setPrompts] = React.useState<McpEnumeration<McpPrompt> | null>(null)
  const [selectedPrompt, setSelectedPrompt] = React.useState<McpPrompt | null>(null)
  const [promptArgs, setPromptArgs] = React.useState<Record<string, string>>({})
  const [templateUri, setTemplateUri] = React.useState('')
  const [preview, setPreview] = React.useState<OperationPreview | null>(null)
  const [previewLoading, setPreviewLoading] = React.useState(false)
  const [applyOpen, setApplyOpen] = React.useState(false)
  const [agents, setAgents] = React.useState<AgentListItem[]>([])
  const [selectedAgentId, setSelectedAgentId] = React.useState('')
  const [applyError, setApplyError] = React.useState<string | null>(null)

  const identity = React.useMemo(
    () => ({
      connection_mode: binding.connection_mode ?? undefined,
      connection_id: binding.connection_id ?? undefined,
    }),
    [binding]
  )

  const loadCapabilities = React.useCallback(async (executionId?: string) => {
    if (!tool?.id || !teamId) return
    const generation = generationRef.current
    setIsLoading(true)
    setError((current) => (current?.scope === 'capabilities' ? null : current))
    try {
      const outcome = await toolMcpApi.getCapabilities(tool.id, { teamId, ...identity, execution_id: executionId })
      if (generation !== generationRef.current) return
      if (outcome.status === 'pending_approval') {
        setPending({ kind: 'capabilities', executionId: outcome.execution_id ?? outcome.pending_approval?.execution_id ?? '' })
        setCapabilities(null)
      } else {
        setPending(null)
        const result = outcome.result
        setCapabilities(result)
        if (result) {
          const supported = BROWSE_TABS.filter((key) => tabCapability(result, key))
          setTab((current) => (supported.includes(current) ? current : supported[0] ?? current))
        }
      }
    } catch (err) {
      if (generation !== generationRef.current) return
      setError(apiError(err, 'capabilities'))
      setCapabilities(null)
    } finally {
      if (generation === generationRef.current) setIsLoading(false)
    }
  }, [tool?.id, teamId, identity])

  React.useEffect(() => {
    if (!open) return
    generationRef.current += 1
    setTab('resources')
    setBinding(EMPTY_CONNECTION_BINDING)
    setPreview(null)
    setPreviewLoading(false)
    setResources(null)
    setTemplates(null)
    setPrompts(null)
    setSelectedPrompt(null)
    setPromptArgs({})
    setTemplateUri('')
    setCapabilities(null)
    setPending(null)
    setError(null)
    setApplyOpen(false)
    setApplyError(null)
    monitorCloseRef.current?.()
    monitorCloseRef.current = null
    setMonitor(null)
  }, [open, tool?.id])

  React.useEffect(() => {
    if (open) return
    monitorCloseRef.current?.()
    monitorCloseRef.current = null
    setMonitor(null)
  }, [open])

  React.useEffect(() => {
    generationRef.current += 1
  }, [identity])

  React.useEffect(() => {
    if (open) void loadCapabilities()
  }, [open, loadCapabilities])

  const loadList = React.useCallback(
    async (target: BrowseTab, cursor?: string, executionId?: string) => {
      if (!tool?.id || !teamId) return
      // Never ask a server for a capability it did not advertise.
      if (!tabCapability(capabilities, target)) return
      const generation = generationRef.current
      setError((current) => (current?.scope === target ? null : current))
      try {
        if (target === 'resources') {
          const outcome = await toolMcpApi.listResources(tool.id, { teamId, cursor, ...identity, execution_id: executionId })
          if (generation !== generationRef.current) return
          if (outcome.status === 'pending_approval') {
            setPending({ kind: target, cursor, executionId: outcome.execution_id ?? outcome.pending_approval?.execution_id ?? '' })
            return
          }
          setPending(null)
          if (!outcome.result) return
          const next = outcome.result
          setResources((current) => cursor && current ? { ...next, items: [...current.items, ...next.items] } : next)
          return
        }
        if (target === 'templates') {
          const outcome = await toolMcpApi.listResourceTemplates(tool.id, { teamId, cursor, ...identity, execution_id: executionId })
          if (generation !== generationRef.current) return
          if (outcome.status === 'pending_approval') {
            setPending({ kind: target, cursor, executionId: outcome.execution_id ?? outcome.pending_approval?.execution_id ?? '' })
            return
          }
          setPending(null)
          if (!outcome.result) return
          const next = outcome.result
          setTemplates((current) => cursor && current ? { ...next, items: [...current.items, ...next.items] } : next)
          return
        }
        const outcome = await toolMcpApi.listPrompts(tool.id, { teamId, cursor, ...identity, execution_id: executionId })
        if (generation !== generationRef.current) return
        if (outcome.status === 'pending_approval') {
          setPending({ kind: target, cursor, executionId: outcome.execution_id ?? outcome.pending_approval?.execution_id ?? '' })
          return
        }
        setPending(null)
        if (!outcome.result) return
        const next = outcome.result
        setPrompts((current) => cursor && current ? { ...next, items: [...current.items, ...next.items] } : next)
      } catch (err) {
        if (generation !== generationRef.current) return
        setError(apiError(err, target))
      }
    },
    [tool?.id, teamId, identity, capabilities]
  )

  React.useEffect(() => {
    if (!open || !capabilities) return
    if (!tabCapability(capabilities, tab)) return
    if (error?.scope === tab) return
    if (tab === 'resources' && !resources) void loadList('resources')
    if (tab === 'templates' && !templates) void loadList('templates')
    if (tab === 'prompts' && !prompts) void loadList('prompts')
  }, [open, tab, capabilities, resources, templates, prompts, loadList, error])

  const stopMonitor = React.useCallback(() => {
    monitorCloseRef.current?.()
    monitorCloseRef.current = null
    setMonitor(null)
  }, [])

  React.useEffect(() => () => {
    monitorCloseRef.current?.()
    monitorCloseRef.current = null
  }, [])

  const startMonitor = (uri: string, executionId?: string) => {
    if (!tool?.id || !teamId) return
    monitorCloseRef.current?.()
    setMonitor({ uri, status: 'connecting', updates: 0 })
    monitorCloseRef.current = toolMcpApi.subscribeResource(
      tool.id,
      { teamId, uri, ...identity, execution_id: executionId },
      {
        onOpened: (opened) => setMonitor((current) => current
          ? { ...current, status: 'open', opened, executionId: undefined }
          : current),
        onUpdated: () => {
          setMonitor((current) => current ? { ...current, updates: current.updates + 1 } : current)
          void readResource(uri)
        },
        onClosed: (reason) => {
          monitorCloseRef.current = null
          setMonitor((current) => current ? { ...current, status: 'closed', reason } : current)
        },
        onPendingApproval: (executionId) => {
          monitorCloseRef.current = null
          setMonitor((current) => current ? { ...current, status: 'pending', executionId } : current)
        },
      }
    )
  }

  const readResource = async (uri: string, executionId?: string) => {
    if (!tool?.id || !teamId) return
    if (UNRESOLVED_TEMPLATE_VARIABLE.test(uri)) return
    const generation = generationRef.current
    setPreviewLoading(true)
    setPreview(null)
    setError((current) => (current?.scope === 'preview' ? null : current))
    try {
      const outcome = await toolMcpApi.readResource(tool.id, teamId, uri, {
        ...identity,
        ...(executionId ? { execution_id: executionId } : {}),
      })
      if (generation !== generationRef.current) return
      const next = resourcePreview(uri, outcome, t('draftResourceNotice', { uri }))
      if (next.pendingExecutionId) {
        setPending({ kind: 'resource', executionId: next.pendingExecutionId, target: uri })
      } else {
        setPending(null)
      }
      setPreview(next)
    } catch (err) {
      if (generation !== generationRef.current) return
      setError(apiError(err, 'preview'))
    } finally {
      if (generation === generationRef.current) setPreviewLoading(false)
    }
  }

  const getPrompt = async (prompt: McpPrompt | string, executionId?: string) => {
    if (!tool?.id || !teamId) return
    const name = typeof prompt === 'string' ? prompt : prompt.name
    const generation = generationRef.current
    setPreviewLoading(true)
    setPreview(null)
    setError((current) => (current?.scope === 'preview' ? null : current))
    try {
      const outcome = await toolMcpApi.getPrompt(tool.id, teamId, name, promptArgs, {
        ...identity,
        ...(executionId ? { execution_id: executionId } : {}),
      })
      if (generation !== generationRef.current) return
      const next = promptPreview(name, outcome, t('draftPromptNotice', { name }))
      if (next.pendingExecutionId) {
        setPending({ kind: 'prompt', executionId: next.pendingExecutionId, target: name })
      } else {
        setPending(null)
      }
      setPreview(next)
    } catch (err) {
      if (generation !== generationRef.current) return
      setError(apiError(err, 'preview'))
    } finally {
      if (generation === generationRef.current) setPreviewLoading(false)
    }
  }

  const openApply = async () => {
    if (!preview || !teamId) return
    setApplyError(null)
    setApplyOpen(true)
    if (agents.length > 0) return
    try {
      const page = await agentsApi.getAgents({ teamId, pageSize: 100, status: 'published' })
      setAgents(page.items)
    } catch {
      setAgents([])
    }
  }

  const apply = () => {
    if (!preview || !teamId || !selectedAgentId) return
    const result = storeMcpDraft({
      agentId: selectedAgentId,
      teamId,
      text: preview.text,
      source: preview.title,
    })
    if (!result.stored) {
      setApplyError(result.reason === 'too_large' ? t('draftTooLarge') : t('draftUnavailable'))
      return
    }
    setApplyOpen(false)
    router.push(`/chat/${selectedAgentId}?draft=1&team=${encodeURIComponent(teamId)}`)
  }

  const unresolvedTemplateVariables = React.useMemo(() => {
    const matches = Array.from(templateUri.matchAll(/\{([^{}]+)\}/g)).map((match) => match[1])
    return Array.from(new Set(matches))
  }, [templateUri])

  const handleOpenChange = (next: boolean) => {
    if (!next) {
      generationRef.current += 1
      setIsLoading(false)
      stopMonitor()
      setApplyOpen(false)
    }
    onOpenChange(next)
  }

  return (
    <>
      <Dialog open={open} onOpenChange={handleOpenChange}>
        <DialogContent
          className="sm:max-w-4xl max-h-[90vh] overflow-y-auto"
          onKeyDownCapture={(event) => {
            if (event.key !== 'Escape') return
            const target = event.target as Node | null
            const boundary = contentRef.current?.parentElement
            if (target && boundary && !boundary.contains(target)) return
            event.preventDefault()
            event.stopPropagation()
            handleOpenChange(false)
          }}
        >
          <DialogHeader>
            <DialogTitle>{t('title', { name: tool?.display_name || tool?.name || '' })}</DialogTitle>
            <DialogDescription>{t('description')}</DialogDescription>
          </DialogHeader>

          <div ref={contentRef} className="space-y-3 py-2">
            <ToolConnectionPicker
              tool={tool}
              teamId={teamId}
              value={binding}
              onChange={(next) => {
                generationRef.current += 1
                stopMonitor()
                setBinding(next)
                setResources(null)
                setTemplates(null)
                setPrompts(null)
                setSelectedPrompt(null)
                setPreview(null)
                setPreviewLoading(false)
                setError(null)
              }}
            />

            <div className="flex items-center justify-between gap-2">
              <p className="text-xs text-muted-foreground">
                {capabilities?.server_name
                  ? t('serverInfo', {
                      name: capabilities.server_name,
                      version: capabilities.server_version || '',
                    })
                  : t('serverUnknown')}
              </p>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="h-7 text-xs"
                onClick={() => {
                  generationRef.current += 1
                  void loadCapabilities()
                  setResources(null)
                  setTemplates(null)
                  setPrompts(null)
                  setPreview(null)
                  setPreviewLoading(false)
                  setPending(null)
                  setError(null)
                }}
                disabled={isLoading}
              >
                {isLoading ? <Loader2 className="mr-1 h-3 w-3 animate-spin" /> : <RefreshCw className="mr-1 h-3 w-3" />}
                {t('refresh')}
              </Button>
            </div>

            {error && (
              <div
                role="alert"
                className="flex items-start gap-2 rounded border border-destructive/30 bg-destructive/5 p-2 text-xs text-destructive"
              >
                <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                <div className="space-y-1">
                  <p>{error.message ?? t('loadFailed')}</p>
                  {error.code === POLICY_CONFIGURATION_REQUIRED && <p>{t('policyGuidance')}</p>}
                </div>
              </div>
            )}
          {isLoading && !capabilities && (
            <div className="flex items-center gap-2 py-6 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              {t('loading')}
            </div>
          )}

          {pending && (
            <div className="flex items-center justify-between gap-2 rounded border border-amber-500/30 bg-amber-500/5 p-2 text-xs">
              <span>{t('pendingApproval', { executionId: pending.executionId })}</span>
              <Button
                size="sm"
                variant="outline"
                className="h-6 text-xs"
                onClick={() => {
                  if (pending.kind === 'capabilities') void loadCapabilities(pending.executionId)
                  else if (pending.kind === 'resource' && pending.target) {
                    void readResource(pending.target, pending.executionId)
                  } else if (pending.kind === 'prompt' && pending.target) {
                    void getPrompt(pending.target, pending.executionId)
                  } else if (pending.kind !== 'resource' && pending.kind !== 'prompt') {
                    void loadList(pending.kind, pending.cursor, pending.executionId)
                  }
                }}
              >
                {t('retryApproval')}
              </Button>
            </div>
          )}

          <Tabs
            value={tab}
            onValueChange={(value) => {
              setTab(value as BrowseTab)
              setError((current) => (current?.scope === 'capabilities' ? current : null))
            }}
          >
            <TabsList className="grid w-full grid-cols-3">
              <TabsTrigger value="resources" disabled={!tabCapability(capabilities, 'resources')}>
                {t('tabs.resources')}
              </TabsTrigger>
              <TabsTrigger value="templates" disabled={!tabCapability(capabilities, 'templates')}>
                {t('tabs.templates')}
              </TabsTrigger>
              <TabsTrigger value="prompts" disabled={!tabCapability(capabilities, 'prompts')}>
                {t('tabs.prompts')}
              </TabsTrigger>
            </TabsList>

            <TabsContent value="resources" className="mt-3">
              {!capabilities ? null : !tabCapability(capabilities, 'resources') ? (
                <p className="text-xs text-muted-foreground">{t('unsupported.resources')}</p>
              ) : error?.scope === 'resources' || pending?.kind === 'resources' ? null : resources === null ? (
                <p className="text-xs text-muted-foreground">{t('loadingList')}</p>
              ) : resources.items.length === 0 ? (
                <p className="text-xs text-muted-foreground">{t('resources.empty')}</p>
              ) : (
                <EnumerationList
                  items={resources.items}
                  empty={t('resources.empty')}
                  render={(resource) => (
                    <div key={resource.uri} className="rounded border p-2 hover:bg-muted/40 space-y-1">
                      <button
                        type="button"
                        className="w-full text-left"
                        onClick={() => void readResource(resource.uri)}
                      >
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-medium truncate">{resource.title || resource.name || resource.uri}</span>
                          {resource.mime_type && <Badge variant="outline" className="text-[10px]">{resource.mime_type}</Badge>}
                        </div>
                        <p className="text-xs text-muted-foreground truncate">{resource.uri}</p>
                        {resource.description && <p className="text-xs text-muted-foreground line-clamp-2">{resource.description}</p>}
                      </button>
                      {capabilities?.resources_subscribe && (
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          className="h-6 text-[10px]"
                          onClick={() => startMonitor(resource.uri)}
                        >
                          {t('monitor.start')}
                        </Button>
                      )}
                    </div>
                  )}
                />
              )}
              {resources?.truncated && <TruncationNotice data={resources} />}
              {resources?.next_cursor && (
                <Button variant="outline" size="sm" className="mt-2" onClick={() => void loadList('resources', resources.next_cursor!)}>
                  {t('loadMore')}
                </Button>
              )}
            </TabsContent>

            <TabsContent value="templates" className="mt-3 space-y-2">
              {!capabilities ? null : !tabCapability(capabilities, 'templates') ? (
                <p className="text-xs text-muted-foreground">{t('unsupported.templates')}</p>
              ) : error?.scope === 'templates' || pending?.kind === 'templates' ? null : templates === null ? (
                <p className="text-xs text-muted-foreground">{t('loadingList')}</p>
              ) : (
                <>
                  {templates.items.length === 0 ? (
                    <p className="text-xs text-muted-foreground">{t('templates.empty')}</p>
                  ) : (
                    templates.items.map((template) => (
                      <div key={template.uri_template} className="rounded border p-2 space-y-1">
                        <div className="text-sm font-medium">{template.title || template.name || template.uri_template}</div>
                        <p className="text-xs text-muted-foreground font-mono break-all">{template.uri_template}</p>
                        <Button
                          variant="outline"
                          size="sm"
                          className="h-7 text-xs"
                          onClick={() => {
                            setTab('templates')
                            setTemplateUri(template.uri_template)
                            setPreview(null)
                          }}
                        >
                          {t('templates.expand')}
                        </Button>
                      </div>
                    ))
                  )}
                  {templateUri && (
                    <div className="space-y-2 border-t pt-2">
                      <Label className="text-xs">{t('templates.uri')}</Label>
                      <Input
                        value={templateUri}
                        className="font-mono text-xs"
                        aria-invalid={unresolvedTemplateVariables.length > 0}
                        onChange={(event) => setTemplateUri(event.target.value)}
                      />
                      {unresolvedTemplateVariables.length > 0 && (
                        <p role="alert" className="text-xs text-destructive">
                          {t('templates.unexpanded', { variables: unresolvedTemplateVariables.join(', ') })}
                        </p>
                      )}
                      <Button
                        size="sm"
                        className="h-7 text-xs"
                        onClick={() => void readResource(templateUri)}
                        disabled={!templateUri.trim() || unresolvedTemplateVariables.length > 0}
                      >
                        {t('templates.read')}
                      </Button>
                    </div>
                  )}
                  {templates.truncated && <TruncationNotice data={templates} />}
                  {templates.next_cursor && (
                    <Button variant="outline" size="sm" onClick={() => void loadList('templates', templates.next_cursor!)}>
                      {t('loadMore')}
                    </Button>
                  )}
                </>
              )}
            </TabsContent>

            <TabsContent value="prompts" className="mt-3 space-y-2">
              {!capabilities ? null : !tabCapability(capabilities, 'prompts') ? (
                <p className="text-xs text-muted-foreground">{t('unsupported.prompts')}</p>
              ) : error?.scope === 'prompts' || pending?.kind === 'prompts' ? null : prompts === null ? (
                <p className="text-xs text-muted-foreground">{t('loadingList')}</p>
              ) : (
                <>
                  {prompts.items.length === 0 ? (
                    <p className="text-xs text-muted-foreground">{t('prompts.empty')}</p>
                  ) : (
                    prompts.items.map((prompt) => (
                      <div key={prompt.name} className="rounded border p-2 space-y-2">
                        <div>
                          <div className="text-sm font-medium">{prompt.title || prompt.name}</div>
                          {prompt.description && <p className="text-xs text-muted-foreground">{prompt.description}</p>}
                        </div>
                        <Button
                          variant="outline"
                          size="sm"
                          className="h-7 text-xs"
                          onClick={() => {
                            setSelectedPrompt(prompt)
                            setPromptArgs({})
                            setPreview(null)
                          }}
                        >
                          {t('prompts.use')}
                        </Button>
                        {selectedPrompt?.name === prompt.name && (
                          <div className="space-y-2 border-t pt-2">
                            {prompt.arguments.map((argument) => (
                              <div key={argument.name} className="space-y-1">
                                <Label className="text-xs">
                                  {argument.name}
                                  {argument.required ? ' *' : ''}
                                </Label>
                                <Input
                                  value={promptArgs[argument.name] ?? ''}
                                  onChange={(event) => setPromptArgs((current) => ({ ...current, [argument.name]: event.target.value }))}
                                  placeholder={argument.description ?? argument.name}
                                />
                              </div>
                            ))}
                            <Button
                              size="sm"
                              className="h-7 text-xs"
                              onClick={() => void getPrompt(prompt)}
                              disabled={prompt.arguments.some((argument) => argument.required && !(promptArgs[argument.name] ?? '').trim())}
                            >
                              {t('prompts.get')}
                            </Button>
                          </div>
                        )}
                      </div>
                    ))
                  )}
                  {prompts.truncated && <TruncationNotice data={prompts} />}
                  {prompts.next_cursor && (
                    <Button variant="outline" size="sm" onClick={() => void loadList('prompts', prompts.next_cursor!)}>
                      {t('loadMore')}
                    </Button>
                  )}
                </>
              )}
            </TabsContent>
          </Tabs>

          {monitor && (
            <div className="space-y-1 rounded-lg border border-sky-500/30 bg-sky-500/5 p-3 text-xs">
              <div className="flex items-center justify-between gap-2">
                <span className="font-mono truncate">{monitor.uri}</span>
                {(monitor.status === 'open' || monitor.status === 'connecting') && (
                  <Button variant="outline" size="sm" className="h-6 text-[10px]" onClick={stopMonitor}>
                    {t('monitor.stop')}
                  </Button>
                )}
              </div>
              {monitor.status === 'connecting' && <p>{t('monitor.connecting')}</p>}
              {monitor.status === 'open' && monitor.opened && (
                <p className="text-muted-foreground">
                  {t('monitor.open', {
                    account: monitor.opened.account_label || monitor.opened.connection_scope || t('monitor.noAccount'),
                    expires: monitor.opened.expires_at,
                  })}
                </p>
              )}
              {monitor.status === 'open' && <p>{t('monitor.updates', { count: monitor.updates })}</p>}
              {monitor.status === 'closed' && (
                <div className="flex items-center justify-between gap-2">
                  <span>{t('monitor.closed', { reason: monitor.reason || 'connection_lost' })}</span>
                  <Button variant="outline" size="sm" className="h-6 text-[10px]" onClick={() => startMonitor(monitor.uri)}>
                    {t('monitor.reconnect')}
                  </Button>
                </div>
              )}
              {monitor.status === 'pending' && (
                <div className="flex items-center justify-between gap-2">
                  <span>{t('monitor.pending', { executionId: monitor.executionId || '' })}</span>
                  <Button variant="outline" size="sm" className="h-6 text-[10px]" onClick={() => startMonitor(monitor.uri, monitor.executionId)}>
                    {t('monitor.retry')}
                  </Button>
                </div>
              )}
              {monitor.status === 'error' && <p className="text-destructive">{t('monitor.failed')}</p>}
            </div>
          )}

          {previewLoading && (
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              {t('previewLoading')}
            </div>
          )}

          {preview && (
            <div className="space-y-2 rounded-lg border p-3">
              <div className="flex items-center justify-between gap-2">
                <div className="text-sm font-medium">{preview.title}</div>
                <Button size="sm" className="h-7 text-xs" onClick={() => void openApply()} disabled={!!preview.pendingExecutionId || !preview.text.trim()}>
                  {t('apply')}
                </Button>
              </div>
              {preview.pendingExecutionId && (
                <p className="text-xs text-amber-600 dark:text-amber-400">
                  {t('pendingApproval', { executionId: preview.pendingExecutionId })}
                </p>
              )}
              {preview.kind === 'prompt' && (
                <p className="rounded border border-amber-500/30 bg-amber-500/5 p-2 text-xs text-amber-700 dark:text-amber-400">
                  {t('untrustedPrompt')}
                </p>
              )}
              {preview.truncated && (
                <p className="text-xs text-muted-foreground">{t('previewTruncated', { limit: MAX_PREVIEW_CHARS })}</p>
              )}
              {preview.binary && (
                <p className="text-xs text-muted-foreground">
                  {t('binaryResource', { uri: preview.binary.uri, mime: preview.binary.mimeType || t('unknownMime') })}
                </p>
              )}
              {preview.messages ? (
                <ScrollArea className="max-h-56">
                  <div className="space-y-2 pr-2">
                    {preview.messages.map((message, index) => (
                      <div key={index} className="rounded bg-muted/40 p-2">
                        <div className="text-[10px] uppercase text-muted-foreground">{message.role}</div>
                        <pre className="text-xs whitespace-pre-wrap break-words">{message.text}</pre>
                      </div>
                    ))}
                  </div>
                </ScrollArea>
              ) : preview.text ? (
                <ScrollArea className="max-h-56">
                  <pre className="text-xs whitespace-pre-wrap break-words pr-2">{preview.text}</pre>
                </ScrollArea>
              ) : null}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => handleOpenChange(false)}>{t('close')}</Button>
        </DialogFooter>
      </DialogContent>
      </Dialog>

      <Dialog open={applyOpen} onOpenChange={setApplyOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{t('applyTitle')}</DialogTitle>
            <DialogDescription>{t('applyHint')}</DialogDescription>
          </DialogHeader>
          <div className="space-y-2 py-2">
            <Label>{t('targetAgent')}</Label>
            <Select value={selectedAgentId} onValueChange={(value) => setSelectedAgentId(value ?? '')}>
              <SelectTrigger className="w-full">
                <SelectValue>{agents.find((agent) => agent.id === selectedAgentId)?.name || t('selectAgent')}</SelectValue>
              </SelectTrigger>
              <SelectContent side="bottom" alignItemWithTrigger={false}>
                {agents.map((agent) => (
                  <SelectItem key={agent.id} value={agent.id}>{agent.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            {agents.length === 0 && <p className="text-xs text-muted-foreground">{t('noAgents')}</p>}
            {applyError && <p className="text-xs text-destructive">{applyError}</p>}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setApplyOpen(false)}>{t('cancel')}</Button>
            <Button onClick={apply} disabled={!selectedAgentId}>{t('openChat')}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}

function EnumerationList<T>({
  items,
  empty,
  render,
}: {
  items: T[]
  empty: string
  render: (item: T) => React.ReactNode
}) {
  if (items.length === 0) return <p className="text-xs text-muted-foreground">{empty}</p>
  return <div className="space-y-2">{items.map(render)}</div>
}

function TruncationNotice({ data }: { data: McpEnumeration<unknown> }) {
  const t = useTranslations('tools.mcpBrowser')
  const reason = data.truncation_reason
  const reasonText =
    reason === 'max_items'
      ? t('truncated.maxItems')
      : reason === 'max_pages'
        ? t('truncated.maxPages')
        : reason === 'cursor_loop'
          ? t('truncated.cursorLoop')
          : reason === 'deadline'
            ? t('truncated.deadline')
            : t('truncated.unknown')
  return (
    <p className="rounded border border-amber-500/30 bg-amber-500/5 p-2 text-xs text-amber-700 dark:text-amber-400">
      {t('truncated.list', { count: data.total_items, reason: reasonText })}
    </p>
  )
}

function resourcePreview(
  uri: string,
  outcome: McpOperation<McpResourceContents[]>,
  notice: string
): OperationPreview {
  if (outcome.status === 'pending_approval') {
    return {
      kind: 'resource',
      title: uri,
      text: '',
      pendingExecutionId: outcome.pending_approval?.execution_id ?? outcome.execution_id ?? '',
    }
  }
  const contents = outcome.result ?? []
  const body = contentText(contents)
  const binary = contents.find((item) => item.blob)
  const draft = body.text ? draftText(notice, body.text) : null
  return {
    kind: 'resource',
    title: uri,
    text: draft?.text ?? '',
    truncated: body.truncated,
    binary: binary ? { uri: binary.uri, mimeType: binary.mime_type } : undefined,
  }
}

function promptPreview(
  name: string,
  outcome: McpOperation<McpPromptResult>,
  notice: string
): OperationPreview {
  if (outcome.status === 'pending_approval') {
    return {
      kind: 'prompt',
      title: name,
      text: '',
      pendingExecutionId: outcome.pending_approval?.execution_id ?? outcome.execution_id ?? '',
    }
  }
  const messages = (outcome.result?.messages ?? []).map((message) => ({
    role: message.role,
    text: messageText(message.content),
  }))
  const body = messages
    .map((message) => `[${message.role}] ${message.text}`)
    .filter((line) => line.trim().length > 0)
    .join('\n')
  const draft = draftText(notice, body)
  return {
    kind: 'prompt',
    title: name,
    text: draft.text,
    truncated: draft.truncated,
    messages,
  }
}

export type { McpToolBrowserProps }
