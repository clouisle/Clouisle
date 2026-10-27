'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { ChevronDown, Loader2, Plus, RefreshCw, Trash2 } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { FieldError } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import type { Tool, ToolConnectionField, ToolIdentityPolicy } from '@/lib/api/tools'
import {
  toolConnectionsApi,
  type ConnectionOAuthStatus,
  type ToolConnection,
  type ToolConnectionScope,
} from '@/lib/api/tool-connections'

export interface ToolConnectionBinding {
  connection_mode: 'personal' | 'team' | null
  connection_id: string | null
}

export const EMPTY_CONNECTION_BINDING: ToolConnectionBinding = {
  connection_mode: null,
  connection_id: null,
}

export function getToolConnectionBinding(config?: {
  connection_mode?: ToolConnectionBinding['connection_mode']
  connection_id?: string | null
}): ToolConnectionBinding {
  return {
    connection_mode: config?.connection_mode ?? null,
    connection_id: config?.connection_id ?? null,
  }
}

function scopesForIdentity(identity: ToolIdentityPolicy): ToolConnectionScope[] {
  if (identity === 'personal_only') return ['user']
  if (identity === 'team_only') return ['team', 'site']
  if (identity === 'selectable') return ['user', 'team', 'site']
  return []
}

function scopeAllowed(scope: ToolConnectionScope, mode: 'personal' | 'team'): boolean {
  if (mode === 'personal') return scope === 'user'
  return scope === 'team' || scope === 'site'
}

export function connectionLabel(connection: ToolConnection): string {
  return connection.account_label || connection.name
}

interface ToolConnectionPickerProps {
  tool: Pick<Tool, 'id' | 'name' | 'display_name' | 'identity_policy' | 'connection_fields'> | null
  builtinToolKey?: string
  teamId?: string
  value: ToolConnectionBinding
  onChange: (value: ToolConnectionBinding) => void
  disabled?: boolean
}

export function ToolConnectionPicker({
  tool,
  builtinToolKey,
  teamId,
  value,
  onChange,
  disabled = false,
}: ToolConnectionPickerProps) {
  const t = useTranslations('tools.connections')
  const identity = tool?.identity_policy ?? 'none'
  const [connections, setConnections] = React.useState<ToolConnection[]>([])
  const [isLoading, setIsLoading] = React.useState(false)
  const [loadError, setLoadError] = React.useState(false)
  const [reloadKey, setReloadKey] = React.useState(0)
  const [manageOpen, setManageOpen] = React.useState(false)

  const handleManagerChanged = React.useCallback(() => {
    setReloadKey((key) => key + 1)
  }, [])
  const hasService = !!tool?.id || !!builtinToolKey

  const fixedMode: 'personal' | 'team' | null =
    identity === 'personal_only' ? 'personal' : identity === 'team_only' ? 'team' : null
  const mode = fixedMode ?? value.connection_mode
  const visibleConnections = React.useMemo(
    () => connections.filter((connection) => !mode || scopeAllowed(connection.scope, mode)),
    [connections, mode]
  )

  React.useEffect(() => {
    let cancelled = false
    const load = async () => {
      if ((!tool?.id && !builtinToolKey) || !teamId || identity === 'none') {
        setConnections([])
        return
      }
      setIsLoading(true)
      setLoadError(false)
      try {
        const result = tool?.id
          ? await toolConnectionsApi.listForTool(tool.id, { teamId })
          : await toolConnectionsApi.list(teamId, { builtinToolKey })
        if (!cancelled) setConnections(result)
      } catch {
        if (!cancelled) setLoadError(true)
      } finally {
        if (!cancelled) setIsLoading(false)
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [tool?.id, builtinToolKey, teamId, identity, reloadKey])

  const selectedConnection = connections.find((connection) => connection.id === value.connection_id)
  const connectionMissing = !!mode && !value.connection_id

  const setMode = (nextMode: 'personal' | 'team') => {
    onChange({ connection_mode: nextMode, connection_id: null })
  }

  if (identity === 'none') {
    return (
      <div className="space-y-1">
        <Label className="text-xs font-medium">{t('title')}</Label>
        <p className="text-xs text-muted-foreground">{t('identityNone')}</p>
      </div>
    )
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-2">
        <Label className="text-xs font-medium">{t('title')}</Label>
        <div className="flex items-center gap-1">
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="h-6 w-6"
            title={t('refresh')}
            disabled={disabled || isLoading || !hasService || !teamId}
            onClick={() => setReloadKey((key) => key + 1)}
          >
            {isLoading ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <RefreshCw className="h-3.5 w-3.5" />
            )}
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-6 px-2 text-xs"
            disabled={disabled}
            onClick={() => setManageOpen((open) => !open)}
          >
            {manageOpen ? t('hideManage') : t('manage')}
            <ChevronDown className={`ml-1 h-3 w-3 transition-transform ${manageOpen ? 'rotate-180' : ''}`} />
          </Button>
        </div>
      </div>
      <p className="text-xs text-muted-foreground">
        {mode === 'personal'
          ? t('modePersonalHint')
          : mode === 'team'
            ? t('modeTeamHint')
            : t('modeSelectHint')}
      </p>

      {identity === 'selectable' && (
        <Select value={value.connection_mode ?? ''} onValueChange={(next) => setMode(next as 'personal' | 'team')} disabled={disabled}>
          <SelectTrigger className="w-full">
            <SelectValue>
              {value.connection_mode === 'personal'
                ? t('modePersonal')
                : value.connection_mode === 'team'
                  ? t('modeTeam')
                  : t('modePlaceholder')}
            </SelectValue>
          </SelectTrigger>
          <SelectContent side="bottom" alignItemWithTrigger={false}>
            <SelectItem value="personal">{t('modePersonal')}</SelectItem>
            <SelectItem value="team">{t('modeTeam')}</SelectItem>
          </SelectContent>
        </Select>
      )}

      {mode && (
        <Select
          value={value.connection_id ?? ''}
          onValueChange={(connectionId) => {
            onChange({ connection_mode: mode, connection_id: connectionId })
          }}
          disabled={disabled || isLoading || visibleConnections.length === 0}
        >
          <SelectTrigger className="w-full">
            <SelectValue>
              {selectedConnection ? connectionLabel(selectedConnection) : t('selectConnection')}
            </SelectValue>
          </SelectTrigger>
          <SelectContent side="bottom" alignItemWithTrigger={false}>
            {visibleConnections.map((connection) => (
              <SelectItem key={connection.id} value={connection.id}>
                {connectionLabel(connection)}
                {connection.is_default ? ` · ${t('defaultBadge')}` : ''}
                {connection.status !== 'active' ? ` · ${t(`status.${connection.status}`)}` : ''}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      )}

      {mode && visibleConnections.length === 0 && !isLoading && (
        <p className="text-xs text-muted-foreground">
          {loadError ? t('loadFailed') : t('noConnectionsForMode')}
        </p>
      )}
      {connectionMissing && visibleConnections.length > 0 && (
        <p className="text-xs text-amber-600 dark:text-amber-400">{t('selectionRequired')}</p>
      )}

      {manageOpen && !disabled && (
        <ToolConnectionManager
          tool={tool}
          builtinToolKey={builtinToolKey}
          teamId={teamId}
          identity={identity}
          onChanged={handleManagerChanged}
        />
      )}
    </div>
  )
}

interface ToolConnectionManagerProps {
  tool: Pick<Tool, 'id' | 'name' | 'display_name' | 'identity_policy' | 'connection_fields'> | null
  builtinToolKey?: string
  teamId?: string
  identity: ToolIdentityPolicy
  onChanged: () => void
}

export function ToolConnectionManager({
  tool,
  builtinToolKey,
  teamId,
  identity,
  onChanged,
}: ToolConnectionManagerProps) {
  const t = useTranslations('tools.connections')
  const [connections, setConnections] = React.useState<ToolConnection[]>([])
  const [isLoading, setIsLoading] = React.useState(false)
  const [actionError, setActionError] = React.useState<string | null>(null)
  const [creating, setCreating] = React.useState(false)
  const [name, setName] = React.useState('')
  const [accountLabel, setAccountLabel] = React.useState('')
  const [scope, setScope] = React.useState<ToolConnectionScope>(
    identity === 'team_only' ? 'team' : 'user'
  )
  const [secretValues, setSecretValues] = React.useState<Record<string, string>>({})
  const [oauthStatus, setOauthStatus] = React.useState<Record<string, ConnectionOAuthStatus>>({})
  const [oauthStarting, setOauthStarting] = React.useState<string | null>(null)
  const [clientSecretFor, setClientSecretFor] = React.useState<string | null>(null)
  const [clientSecretValue, setClientSecretValue] = React.useState('')

  const availableScopes = scopesForIdentity(identity).filter((item) => item !== 'site')
  const hasService = !!tool?.id || !!builtinToolKey
  const secretFields: ToolConnectionField[] = (tool?.connection_fields ?? []).filter(
    (field) => field.secret
  )

  const reload = React.useCallback(async () => {
    if (!hasService || !teamId) return
    setIsLoading(true)
    setActionError(null)
    try {
      const result = tool?.id
        ? await toolConnectionsApi.listForTool(tool.id, { teamId })
        : await toolConnectionsApi.list(teamId, { builtinToolKey })
      setConnections(result)
      const statusEntries = await Promise.all(
        result.map(async (connection) => {
          try {
            return [connection.id, await toolConnectionsApi.getOAuthStatus(connection.id, teamId)] as const
          } catch {
            return null
          }
        })
      )
      setOauthStatus(
        Object.fromEntries(
          statusEntries.filter(
            (entry): entry is readonly [string, ConnectionOAuthStatus] => entry !== null
          )
        )
      )
    } catch {
      setActionError(t('loadFailed'))
    } finally {
      setIsLoading(false)
    }
    // Translator identity is stable in next-intl; excluding it prevents a
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasService, tool?.id, builtinToolKey, teamId])

  React.useEffect(() => {
    reload()
  }, [reload])

  const handleCreate = async () => {
    if (!hasService || !teamId) return
    if (!name.trim()) {
      setActionError(t('nameRequired'))
      return
    }
    const missing = secretFields.filter(
      (field) => field.required && !(secretValues[field.name] ?? '').trim()
    )
    if (missing.length > 0) {
      setActionError(t('secretRequired', { fields: missing.map((field) => field.label).join(', ') }))
      return
    }
    setCreating(true)
    setActionError(null)
    try {
      const payload = {
        team_id: teamId,
        scope,
        name: name.trim(),
        account_label: accountLabel.trim() || null,
        config: Object.fromEntries(
          Object.entries(secretValues).filter(([, value]) => value.trim())
        ),
      }
      if (tool?.id) {
        await toolConnectionsApi.createForTool(tool.id, payload)
      } else {
        await toolConnectionsApi.create({ ...payload, builtin_tool_key: builtinToolKey })
      }
      setName('')
      setAccountLabel('')
      setSecretValues({})
      await reload()
      onChanged()
    } catch {
      setActionError(t('createFailed'))
    } finally {
      setCreating(false)
    }
  }

  const handleSetDefault = async (connection: ToolConnection) => {
    try {
      await toolConnectionsApi.update(connection.id, { is_default: true })
      await reload()
      onChanged()
    } catch {
      setActionError(t('updateFailed'))
    }
  }

  const handleRevoke = async (connection: ToolConnection) => {
    try {
      await toolConnectionsApi.revoke(connection.id)
      await reload()
      onChanged()
    } catch {
      setActionError(t('revokeFailed'))
    }
  }

  const handleDisconnectOAuth = async (connection: ToolConnection) => {
    setOauthStarting(connection.id)
    setActionError(null)
    try {
      await toolConnectionsApi.disconnectOAuth(connection.id)
      await reload()
      onChanged()
    } catch {
      setActionError(t('oauthDisconnectFailed'))
    } finally {
      setOauthStarting(null)
    }
  }

  const handleStartOAuth = async (connection: ToolConnection, clientSecret?: string) => {
    setOauthStarting(connection.id)
    setActionError(null)
    try {
      const redirectPath =
        typeof window !== 'undefined' ? window.location.pathname : undefined
      const result = await toolConnectionsApi.startOAuth(connection.id, {
        redirect_path: redirectPath,
        ...(clientSecret ? { client_secret: clientSecret } : {}),
      })
      setClientSecretFor(null)
      setClientSecretValue('')
      if (typeof window !== 'undefined') {
        window.open(result.authorization_url, '_blank', 'noopener,noreferrer')
      }
    } catch {
      setActionError(t('oauthFailed'))
    } finally {
      setOauthStarting(null)
    }
  }

  return (
    <div className="rounded-md border bg-muted/20 p-3 space-y-3">
      <div className="flex items-center justify-between gap-2">
        <div>
          <p className="text-xs font-medium">{t('manageTitle')}</p>
          <p className="text-[11px] text-muted-foreground">{t('manageHint')}</p>
        </div>
        <Button type="button" variant="ghost" size="sm" className="h-6 px-2 text-xs" onClick={reload} disabled={isLoading}>
          {isLoading ? <Loader2 className="h-3 w-3 animate-spin" /> : <RefreshCw className="h-3 w-3" />}
        </Button>
      </div>

      {connections.length === 0 ? (
        <p className="text-xs text-muted-foreground">{isLoading ? t('loading') : t('empty')}</p>
      ) : (
        <div className="space-y-2">
          {connections.map((connection) => (
            <div key={connection.id} className="rounded border bg-background p-2 space-y-2">
              <div className="flex items-start gap-2">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <span className="text-xs font-medium truncate">{connectionLabel(connection)}</span>
                    <Badge variant="outline" className="text-[9px] px-1 py-0">
                      {t(`scopeOptions.${connection.scope}`)}
                    </Badge>
                    {connection.is_default && (
                      <Badge variant="secondary" className="text-[9px] px-1 py-0">
                        {t('defaultBadge')}
                      </Badge>
                    )}
                    {connection.status !== 'active' && (
                      <Badge variant="destructive" className="text-[9px] px-1 py-0">
                        {t(`status.${connection.status}`)}
                      </Badge>
                    )}
                    {oauthStatus[connection.id]?.provider_configured && (
                      <Badge
                        variant={oauthStatus[connection.id].needs_reauth ? 'destructive' : 'secondary'}
                        className="text-[9px] px-1 py-0"
                      >
                        {oauthStatus[connection.id].needs_reauth
                          ? t('oauthNeedsReauth')
                          : oauthStatus[connection.id].authorized
                            ? t('oauthAuthorized')
                            : t('oauthNotConnected')}
                      </Badge>
                    )}
                  </div>
                  <p className="text-[11px] text-muted-foreground">
                    {connection.name} · {connection.secret_fields.join(', ') || t('noSecrets')}
                  </p>
                </div>
                <div className="flex items-center gap-0.5">
                  {(oauthStatus[connection.id]?.provider_configured ||
                    oauthStatus[connection.id]?.needs_reauth ||
                    connection.status === 'reauth_required') && (
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      className="h-6 px-1.5 text-[10px]"
                      disabled={oauthStarting === connection.id}
                      onClick={() => handleStartOAuth(connection)}
                    >
                      {oauthStarting === connection.id ? (
                        <Loader2 className="h-3 w-3 mr-1 animate-spin" />
                      ) : (
                        <RefreshCw className="h-3 w-3 mr-1" />
                      )}
                      {oauthStatus[connection.id]?.needs_reauth ||
                      connection.status === 'reauth_required'
                        ? t('oauthReconnect')
                        : t('oauthConnect')}
                    </Button>
                  )}
                  {!connection.is_default && (
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      className="h-6 px-1.5 text-[10px]"
                      onClick={() => handleSetDefault(connection)}
                    >
                      {t('setDefault')}
                    </Button>
                  )}
                  {oauthStatus[connection.id]?.provider_configured && (
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      className="h-6 px-1.5 text-[10px]"
                      onClick={() => {
                        setClientSecretFor((current) => current === connection.id ? null : connection.id)
                        setClientSecretValue('')
                      }}
                    >
                      {t('oauthClientSecret')}
                    </Button>
                  )}
                  {oauthStatus[connection.id]?.provider_configured && (
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      className="h-6 px-1.5 text-[10px] text-destructive"
                      disabled={oauthStarting === connection.id}
                      onClick={() => handleDisconnectOAuth(connection)}
                    >
                      {t('oauthDisconnect')}
                    </Button>
                  )}
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="h-6 w-6 text-destructive"
                    title={t('revoke')}
                    onClick={() => handleRevoke(connection)}
                  >
                    <Trash2 className="h-3 w-3" />
                  </Button>
                </div>
              </div>

              {clientSecretFor === connection.id && (
                <div className="space-y-1 rounded border border-dashed p-2">
                  <Label htmlFor={`oauth-client-secret-${connection.id}`} className="text-[11px]">
                    {t('oauthClientSecret')}
                  </Label>
                  <Input
                    id={`oauth-client-secret-${connection.id}`}
                    type="password"
                    value={clientSecretValue}
                    placeholder={t('oauthClientSecretPlaceholder')}
                    className="h-7 text-xs"
                    onChange={(event) => setClientSecretValue(event.target.value)}
                  />
                  <p className="text-[10px] text-muted-foreground">{t('oauthClientSecretHint')}</p>
                  <div className="flex gap-1">
                    <Button
                      type="button"
                      size="sm"
                      className="h-6 text-[10px]"
                      onClick={() => void handleStartOAuth(connection, clientSecretValue)}
                      disabled={!clientSecretValue.trim() || oauthStarting === connection.id}
                    >
                      {t('oauthSaveSecret')}
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      className="h-6 text-[10px]"
                      onClick={() => {
                        setClientSecretFor(null)
                        setClientSecretValue('')
                      }}
                    >
                      {t('oauthCancelSecret')}
                    </Button>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      <div className="space-y-2 border-t pt-2">
        <p className="text-xs font-medium">{t('createTitle')}</p>
        <div className="grid grid-cols-2 gap-1.5">
          <Input
            value={name}
            placeholder={t('namePlaceholder')}
            className="h-7 text-xs"
            onChange={(event) => setName(event.target.value)}
          />
          <Input
            value={accountLabel}
            placeholder={t('accountLabelPlaceholder')}
            className="h-7 text-xs"
            onChange={(event) => setAccountLabel(event.target.value)}
          />
        </div>
        {availableScopes.length > 1 && (
          <Select value={scope} onValueChange={(value) => setScope(value as ToolConnectionScope)}>
            <SelectTrigger className="h-7 text-xs">
              <SelectValue>{t(`scopeOptions.${scope}`)}</SelectValue>
            </SelectTrigger>
            <SelectContent side="bottom" alignItemWithTrigger={false}>
              {availableScopes.map((item) => (
                <SelectItem key={item} value={item}>
                  {t(`scopeOptions.${item}`)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
        {secretFields.map((field) => (
          <div key={field.name} className="space-y-1">
            <Label htmlFor={`connection-secret-${field.name}`} className="text-[11px]">
              {field.label}
              {field.required ? ' *' : ''}
            </Label>
            <Input
              id={`connection-secret-${field.name}`}
              type="password"
              className="h-7 text-xs"
              value={secretValues[field.name] ?? ''}
              onChange={(event) =>
                setSecretValues((current) => ({ ...current, [field.name]: event.target.value }))
              }
            />
          </div>
        ))}
        <p className="text-[10px] text-muted-foreground">{t('secretFieldsHint')}</p>
        <Button type="button" variant="outline" size="sm" className="h-7 text-xs" onClick={handleCreate} disabled={creating}>
          {creating ? <Loader2 className="h-3 w-3 mr-1 animate-spin" /> : <Plus className="h-3 w-3 mr-1" />}
          {t('create')}
        </Button>
      </div>

      {actionError && <FieldError>{actionError}</FieldError>}
    </div>
  )
}
