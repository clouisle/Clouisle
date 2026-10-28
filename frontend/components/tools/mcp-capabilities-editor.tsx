'use client'

import { useTranslations } from 'next-intl'
import { Plus, Trash2 } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'

export interface McpRootEntry {
  uri: string
  name: string
}

export interface McpCapabilitySettings {
  enable_sampling: boolean
  enable_elicitation: boolean
  roots: McpRootEntry[]
  roots_allowlist: string[]
  elicitation_url_hosts: string[]
  callback_timeout_seconds: number
  max_sampling_requests: number
  max_elicitation_requests: number
  sampling_max_tokens: number
}

export const DEFAULT_MCP_CAPABILITIES: McpCapabilitySettings = {
  enable_sampling: false,
  enable_elicitation: false,
  roots: [],
  roots_allowlist: [],
  elicitation_url_hosts: [],
  callback_timeout_seconds: 120,
  max_sampling_requests: 4,
  max_elicitation_requests: 4,
  sampling_max_tokens: 1024,
}

type McpCapabilityConfig = Omit<Partial<McpCapabilitySettings>, 'roots'> & {
  roots?: Array<{ uri: string; name?: string }>
}

export function getMcpCapabilities(config?: McpCapabilityConfig | null): McpCapabilitySettings {
  return {
    enable_sampling: config?.enable_sampling ?? DEFAULT_MCP_CAPABILITIES.enable_sampling,
    enable_elicitation: config?.enable_elicitation ?? DEFAULT_MCP_CAPABILITIES.enable_elicitation,
    roots: (config?.roots ?? []).map((root) => ({ uri: root.uri, name: root.name ?? '' })),
    roots_allowlist: [...(config?.roots_allowlist ?? [])],
    elicitation_url_hosts: [...(config?.elicitation_url_hosts ?? [])],
    callback_timeout_seconds:
      config?.callback_timeout_seconds ?? DEFAULT_MCP_CAPABILITIES.callback_timeout_seconds,
    max_sampling_requests:
      config?.max_sampling_requests ?? DEFAULT_MCP_CAPABILITIES.max_sampling_requests,
    max_elicitation_requests:
      config?.max_elicitation_requests ?? DEFAULT_MCP_CAPABILITIES.max_elicitation_requests,
    sampling_max_tokens:
      config?.sampling_max_tokens ?? DEFAULT_MCP_CAPABILITIES.sampling_max_tokens,
  }
}

const HOST_PATTERN = /^(?=.{1,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)*[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/
const ABSOLUTE_URI_PATTERN = /^[a-z][a-z0-9+.-]*:/i

export interface McpCapabilityErrors {
  roots: Record<number, string>
  hosts: number[]
  allowlist: string | null
}

export function validateMcpCapabilities(
  value: McpCapabilitySettings,
  messages: {
    invalidRoot: string
    invalidHost: string
    missingAllowlist: string
    rootNotAllowed: string
  }
): McpCapabilityErrors {
  const roots: Record<number, string> = {}
  const allowlist = value.roots_allowlist.map((entry) => entry.trim()).filter(Boolean)
  const allowlistValid = allowlist.every((entry) => ABSOLUTE_URI_PATTERN.test(entry) && !/\s/.test(entry))
  value.roots.forEach((root, index) => {
    const uri = root.uri.trim()
    if (!ABSOLUTE_URI_PATTERN.test(uri) || /\s/.test(uri)) {
      roots[index] = messages.invalidRoot
    } else if (allowlist.length === 0) {
      roots[index] = messages.missingAllowlist
    } else if (!allowlist.some((entry) => uri.startsWith(entry))) {
      roots[index] = messages.rootNotAllowed
    }
  })
  const hosts = value.elicitation_url_hosts
    .map((host, index) => ({ host: host.trim().toLowerCase(), index }))
    .filter(({ host }) => host && !HOST_PATTERN.test(host))
    .map(({ index }) => index)
  return {
    roots,
    hosts,
    allowlist:
      value.roots_allowlist.length > 0 && !allowlistValid
        ? messages.invalidRoot
        : value.roots.length > 0 && allowlist.length === 0
          ? messages.missingAllowlist
          : null,
  }
}

export function hasMcpCapabilityErrors(errors: McpCapabilityErrors): boolean {
  return Object.keys(errors.roots).length > 0 || errors.hosts.length > 0 || errors.allowlist !== null
}

export function mcpCapabilitiesConfig(value: McpCapabilitySettings): Partial<McpCapabilitySettings> {
  const defaults = DEFAULT_MCP_CAPABILITIES
  const unchanged =
    value.enable_sampling === defaults.enable_sampling &&
    value.enable_elicitation === defaults.enable_elicitation &&
    value.roots.length === 0 &&
    value.roots_allowlist.length === 0 &&
    value.elicitation_url_hosts.length === 0 &&
    value.callback_timeout_seconds === defaults.callback_timeout_seconds &&
    value.max_sampling_requests === defaults.max_sampling_requests &&
    value.max_elicitation_requests === defaults.max_elicitation_requests &&
    value.sampling_max_tokens === defaults.sampling_max_tokens
  return unchanged ? {} : value
}

function linesToArray(value: string): string[] {
  return [...new Set(value.split(/[\n,]+/).map((item) => item.trim()).filter(Boolean))]
}

interface McpCapabilitiesEditorProps {
  value: McpCapabilitySettings
  onChange: (value: McpCapabilitySettings) => void
}

export function McpCapabilitiesEditor({ value, onChange }: McpCapabilitiesEditorProps) {
  const t = useTranslations('tools.mcpCapabilities')
  const patch = (updates: Partial<McpCapabilitySettings>) => onChange({ ...value, ...updates })
  const errors = validateMcpCapabilities(value, {
    invalidRoot: t('invalidRootUri'),
    invalidHost: t('invalidElicitationHost'),
    missingAllowlist: t('rootsRequireAllowlist'),
    rootNotAllowed: t('rootOutsideAllowlist'),
  })

  const updateRoot = (index: number, field: keyof McpRootEntry, next: string) => {
    patch({
      roots: value.roots.map((root, current) =>
        current === index ? { ...root, [field]: next } : root
      ),
    })
  }

  return (
    <div className="space-y-4 border rounded-lg p-4">
      <div className="space-y-1">
        <h4 className="font-medium">{t('title')}</h4>
        <p className="text-xs text-muted-foreground">{t('hint')}</p>
      </div>

      <div className="space-y-3">
        <div className="flex items-center justify-between gap-3">
          <div>
            <Label htmlFor="mcp-enable-sampling" className="text-xs font-medium">
              {t('sampling')}
            </Label>
            <p className="text-xs text-muted-foreground">{t('samplingHint')}</p>
          </div>
          <Switch
            id="mcp-enable-sampling"
            checked={value.enable_sampling}
            onCheckedChange={(checked) => patch({ enable_sampling: checked })}
          />
        </div>

        <div className="flex items-center justify-between gap-3">
          <div>
            <Label htmlFor="mcp-enable-elicitation" className="text-xs font-medium">
              {t('elicitation')}
            </Label>
            <p className="text-xs text-muted-foreground">{t('elicitationHint')}</p>
          </div>
          <Switch
            id="mcp-enable-elicitation"
            checked={value.enable_elicitation}
            onCheckedChange={(checked) => patch({ enable_elicitation: checked })}
          />
        </div>
      </div>

      <div className="grid grid-cols-3 gap-3">
        <div className="space-y-1">
          <Label htmlFor="mcp-callback-timeout" className="text-xs">
            {t('callbackTimeout')}
          </Label>
          <Input
            id="mcp-callback-timeout"
            type="number"
            min={10}
            max={900}
            value={String(value.callback_timeout_seconds)}
            onChange={(event) =>
              patch({
                callback_timeout_seconds: Math.min(
                  900,
                  Math.max(10, Number(event.target.value) || 10)
                ),
              })
            }
          />
        </div>
        <div className="space-y-1">
          <Label htmlFor="mcp-max-sampling" className="text-xs">
            {t('maxSamplingRequests')}
          </Label>
          <Input
            id="mcp-max-sampling"
            type="number"
            min={0}
            max={20}
            value={String(value.max_sampling_requests)}
            onChange={(event) =>
              patch({
                max_sampling_requests: Math.min(
                  20,
                  Math.max(0, Number(event.target.value) || 0)
                ),
              })
            }
          />
        </div>
        <div className="space-y-1">
          <Label htmlFor="mcp-max-elicitation" className="text-xs">
            {t('maxElicitationRequests')}
          </Label>
          <Input
            id="mcp-max-elicitation"
            type="number"
            min={0}
            max={20}
            value={String(value.max_elicitation_requests)}
            onChange={(event) =>
              patch({
                max_elicitation_requests: Math.min(
                  20,
                  Math.max(0, Number(event.target.value) || 0)
                ),
              })
            }
          />
        </div>
      </div>

      <div className="space-y-1">
        <Label htmlFor="mcp-sampling-max-tokens" className="text-xs">
          {t('samplingMaxTokens')}
        </Label>
        <Input
          id="mcp-sampling-max-tokens"
          type="number"
          min={1}
          max={8192}
          value={String(value.sampling_max_tokens)}
          onChange={(event) =>
            patch({
              sampling_max_tokens: Math.min(
                8192,
                Math.max(1, Number(event.target.value) || 1)
              ),
            })
          }
        />
      </div>

      <div className="space-y-2 border-t pt-3">
        <div className="flex items-center justify-between gap-2">
          <div>
            <Label className="text-xs font-medium">{t('roots')}</Label>
            <p className="text-xs text-muted-foreground">{t('rootsHint')}</p>
          </div>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => patch({ roots: [...value.roots, { uri: '', name: '' }] })}
          >
            <Plus className="h-3.5 w-3.5 mr-1" />
            {t('addRoot')}
          </Button>
        </div>
        {value.roots.length === 0 ? (
          <p className="text-xs text-muted-foreground">{t('noRoots')}</p>
        ) : (
          value.roots.map((root, index) => (
            <div key={index} className="flex items-center gap-2">
              <Input
                value={root.uri}
                placeholder={t('rootUriPlaceholder')}
                className="flex-1 font-mono text-xs"
                onChange={(event) => updateRoot(index, 'uri', event.target.value)}
              />
              <Input
                value={root.name}
                placeholder={t('rootNamePlaceholder')}
                className="w-36 text-xs"
                onChange={(event) => updateRoot(index, 'name', event.target.value)}
              />
              <Button
                type="button"
                variant="ghost"
                size="icon"
                aria-label={t('removeRoot')}
                onClick={() => patch({ roots: value.roots.filter((_, current) => current !== index) })}
              >
                <Trash2 className="h-4 w-4" />
              </Button>
              {errors.roots[index] && (
                <span className="text-xs text-destructive">{errors.roots[index]}</span>
              )}
            </div>
          ))
        )}

        <div className="space-y-1">
          <Label htmlFor="mcp-roots-allowlist" className="text-xs">
            {t('rootsAllowlist')}
          </Label>
          <textarea
            id="mcp-roots-allowlist"
            value={value.roots_allowlist.join('\n')}
            placeholder="file:///workspace"
            className="flex min-h-16 w-full rounded-md border border-input bg-background px-3 py-2 text-xs font-mono"
            onChange={(event) => patch({ roots_allowlist: linesToArray(event.target.value) })}
          />
          <p className="text-xs text-muted-foreground">{t('rootsAllowlistHint')}</p>
          {errors.allowlist && <p className="text-xs text-destructive">{errors.allowlist}</p>}
        </div>
      </div>

      <div className="space-y-1 border-t pt-3">
        <Label htmlFor="mcp-elicitation-hosts" className="text-xs">
          {t('elicitationHosts')}
        </Label>
        <textarea
          id="mcp-elicitation-hosts"
          value={value.elicitation_url_hosts.join('\n')}
          placeholder="auth.example.com"
          className="flex min-h-16 w-full rounded-md border border-input bg-background px-3 py-2 text-xs font-mono"
          onChange={(event) => patch({ elicitation_url_hosts: linesToArray(event.target.value) })}
        />
        <p className="text-xs text-muted-foreground">{t('elicitationHostsHint')}</p>
        {errors.hosts.length > 0 && <p className="text-xs text-destructive">{t('invalidElicitationHost')}</p>}
      </div>
    </div>
  )
}
