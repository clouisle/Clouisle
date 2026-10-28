'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import {
  Check,
  ExternalLink,
  KeyRound,
  Link2,
  Loader2,
  Plus,
  RefreshCw,
  Star,
  Trash2,
  X,
} from 'lucide-react'
import { toast } from 'sonner'

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { FieldError } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { renderToolIcon } from '@/components/tools/tool-icons'
import { useTeam } from '@/contexts/team-context'
import type { Tool } from '@/lib/api/tools'
import { toolsApi } from '@/lib/api/tools'
import {
  toolConnectionsApi,
  type ConnectionOAuthStatus,
  type ToolConnection,
  type ToolConnectionScope,
} from '@/lib/api/tool-connections'

export function UserToolConnections() {
  const t = useTranslations('settings.connections')
  const tTools = useTranslations('tools.connections')
  const tCommon = useTranslations('common')
  const { currentTeam } = useTeam()

  const [connections, setConnections] = React.useState<ToolConnection[]>([])
  const [tools, setTools] = React.useState<Tool[]>([])
  const [oauthStatus, setOauthStatus] = React.useState<Record<string, ConnectionOAuthStatus>>({})
  const [isLoading, setIsLoading] = React.useState(true)
  const [isRefreshing, setIsRefreshing] = React.useState(false)

  // Quick creation state
  const [isCreating, setIsCreating] = React.useState(false)
  const [selectedToolKey, setSelectedToolKey] = React.useState<string>('')
  const [name, setName] = React.useState('')
  const [accountLabel, setAccountLabel] = React.useState('')
  const [secretValues, setSecretValues] = React.useState<Record<string, string>>({})
  const [inputMode, setInputMode] = React.useState<'url' | 'host'>('host')
  const [createError, setCreateError] = React.useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = React.useState(false)

  // OAuth actions state
  const [oauthStarting, setOauthStarting] = React.useState<string | null>(null)
  const [clientSecretFor, setClientSecretFor] = React.useState<string | null>(null)
  const [clientSecretValue, setClientSecretValue] = React.useState('')
  const [pendingAction, setPendingAction] = React.useState<
    { kind: 'revoke' | 'disconnect'; connection: ToolConnection } | null
  >(null)

  const teamId = currentTeam?.id

  // Load all connections and connectable tools for the team
  const loadData = React.useCallback(async (silent = false) => {
    if (!teamId) {
      setConnections([])
      setTools([])
      setIsLoading(false)
      return
    }

    if (!silent) setIsLoading(true)
    else setIsRefreshing(true)

    try {
      const [connectionsData, toolsData] = await Promise.all([
        toolConnectionsApi.list(teamId, { includeSite: true, includeRevoked: false }),
        toolsApi.list(teamId),
      ])

      setConnections(connectionsData)

      const allTools = [
        ...(toolsData.builtin || []),
        ...(toolsData.mcp || []),
        ...(toolsData.custom || []),
      ]
      setTools(allTools)

      // Fetch OAuth status for connections concurrently
      const statusEntries = await Promise.all(
        connectionsData.map(async (connection) => {
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
      toast.error(tTools('loadFailed'))
    } finally {
      setIsLoading(false)
      setIsRefreshing(false)
    }
    // Translator identity is stable in next-intl; excluding it keeps loading
    // pinned to the team rather than re-fetching on every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [teamId])

  React.useEffect(() => {
    void loadData()
  }, [loadData])

  // Filter tools that require or allow identity connections
  const connectableTools = React.useMemo(() => {
    return tools.filter((tool) => tool.identity_policy && tool.identity_policy !== 'none')
  }, [tools])

  const selectedTool = React.useMemo(() => {
    if (!selectedToolKey) return null
    return connectableTools.find((t) => t.id === selectedToolKey || t.name === selectedToolKey) || null
  }, [selectedToolKey, connectableTools])

  // Base UI renders the raw value in the trigger unless the select knows the
  // value-to-label mapping; never show an opaque tool id to the user.
  const toolItems = React.useMemo(
    () =>
      connectableTools.map((tool) => ({
        value: tool.id || tool.name,
        label: tool.display_name || tool.name,
      })),
    [connectableTools]
  )

  // Fields visible for current tool and inputMode
  const visibleFields = React.useMemo(() => {
    if (!selectedTool?.connection_fields) return []
    return selectedTool.connection_fields.filter(
      (field) => !field.input_mode || field.input_mode === inputMode
    )
  }, [selectedTool, inputMode])

  const resetCreateState = () => {
    setIsCreating(false)
    setSelectedToolKey('')
    setName('')
    setAccountLabel('')
    setSecretValues({})
    setInputMode('host')
    setCreateError(null)
    setIsSubmitting(false)
  }

  const handleSelectTool = (key: string | null) => {
    if (!key) return
    setSelectedToolKey(key)
    setSecretValues({})
    setCreateError(null)
    const tool = connectableTools.find((t) => t.id === key || t.name === key)
    if (tool) {
      setName(`${tool.display_name || tool.name}`)
    }
  }

  const handleCreate = async () => {
    if (!teamId || !selectedTool) return
    const trimmedName = name.trim()
    if (!trimmedName) {
      setCreateError(tTools('nameRequired'))
      return
    }

    const missing = visibleFields.filter(
      (field) => field.required && !(secretValues[field.name] || field.default || '').trim()
    )
    if (missing.length > 0) {
      setCreateError(
        tTools('secretRequired', {
          fields: missing.map((f) => (f.label_key ? tTools(f.label_key) : f.label || f.name)).join(', '),
        })
      )
      return
    }

    setIsSubmitting(true)
    setCreateError(null)
    try {
      const configPayload = Object.fromEntries(
        visibleFields
          .map((field) => [field.name, (secretValues[field.name] ?? field.default ?? '').trim()])
          .filter(([, value]) => value.length > 0)
      )

      const payload = {
        team_id: teamId,
        scope: 'user' as ToolConnectionScope,
        name: trimmedName,
        account_label: accountLabel.trim() || null,
        config: configPayload,
      }

      if (selectedTool.id) {
        await toolConnectionsApi.createForTool(selectedTool.id, payload)
      } else {
        await toolConnectionsApi.create({ ...payload, builtin_tool_key: selectedTool.name })
      }

      toast.success(t('createdSuccess'))
      resetCreateState()
      await loadData(true)
    } catch {
      setCreateError(tTools('createFailed'))
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleSetDefault = async (connection: ToolConnection) => {
    try {
      await toolConnectionsApi.update(connection.id, { is_default: true })
      toast.success(t('setDefaultSuccess'))
      await loadData(true)
    } catch {
      toast.error(tTools('updateFailed'))
    }
  }

  const handleRevoke = async (connection: ToolConnection) => {
    try {
      await toolConnectionsApi.revoke(connection.id)
      toast.success(t('revokeSuccess'))
      await loadData(true)
    } catch {
      toast.error(tTools('revokeFailed'))
    }
  }

  const handleDisconnectOAuth = async (connection: ToolConnection) => {
    setOauthStarting(connection.id)
    try {
      await toolConnectionsApi.disconnectOAuth(connection.id)
      toast.success(tTools('oauthDisconnect'))
      await loadData(true)
    } catch {
      toast.error(tTools('oauthDisconnectFailed'))
    } finally {
      setOauthStarting(null)
    }
  }

  const handleConfirmPendingAction = async () => {
    const action = pendingAction
    setPendingAction(null)
    if (!action) return
    if (action.kind === 'revoke') {
      await handleRevoke(action.connection)
    } else {
      await handleDisconnectOAuth(action.connection)
    }
  }

  const handleStartOAuth = async (connection: ToolConnection, clientSecret?: string) => {
    setOauthStarting(connection.id)
    try {
      const redirectPath = typeof window !== 'undefined' ? window.location.pathname : undefined
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
      toast.error(tTools('oauthFailed'))
    } finally {
      setOauthStarting(null)
    }
  }

  // Resolve matching tool metadata for a connection
  const resolveToolForConnection = (connection: ToolConnection): Tool | null => {
    if (connection.tool_id) {
      return tools.find((t) => t.id === connection.tool_id) || null
    }
    if (connection.builtin_tool_key) {
      return tools.find((t) => t.name === connection.builtin_tool_key) || null
    }
    return null
  }

  if (!teamId) {
    return (
      <div className="py-6 text-center text-sm text-muted-foreground">
        {t('noTeam')}
      </div>
    )
  }

  return (
    <div className="space-y-5">
      {/* Header bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b pb-4">
        <div>
          <h3 className="text-base font-semibold text-foreground flex items-center gap-2">
            <Link2 className="h-4 w-4 text-primary" />
            {t('title')}
          </h3>
          <p className="text-xs text-muted-foreground mt-0.5">
            {t('description')}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="h-8 text-xs"
            onClick={() => void loadData(true)}
            disabled={isLoading || isRefreshing}
            title={tTools('loading')}
          >
            <RefreshCw className={`h-3.5 w-3.5 mr-1 ${isRefreshing ? 'animate-spin' : ''}`} />
            {t('refresh')}
          </Button>
          {!isCreating && (
            <Button
              type="button"
              size="sm"
              className="h-8 text-xs"
              onClick={() => setIsCreating(true)}
              disabled={isLoading || connectableTools.length === 0}
            >
              <Plus className="h-3.5 w-3.5 mr-1" />
              {t('add')}
            </Button>
          )}
        </div>
      </div>

      {/* Quick-create Card */}
      {isCreating && (
        <div className="rounded-lg border bg-card p-4 space-y-4 shadow-sm">
          <div className="flex items-center justify-between border-b pb-2">
            <h4 className="text-sm font-semibold flex items-center gap-2">
              <KeyRound className="h-4 w-4 text-primary" />
              {t('createTitle')}
            </h4>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="h-6 w-6"
              onClick={resetCreateState}
            >
              <X className="h-4 w-4" />
            </Button>
          </div>

          <div className="space-y-3">
            {/* Tool Selection */}
            <div className="space-y-1.5">
              <Label className="text-xs font-medium">{t('selectTool')}</Label>
              <Select items={toolItems} value={selectedToolKey} onValueChange={handleSelectTool}>
                <SelectTrigger className="h-9 text-xs">
                  <SelectValue placeholder={t('selectToolPlaceholder')} />
                </SelectTrigger>
                <SelectContent side="bottom">
                  <SelectGroup>
                    <SelectLabel className="text-[11px] text-muted-foreground font-semibold">
                      {t('toolTypeBuiltin')}
                    </SelectLabel>
                    {connectableTools
                      .filter((t) => t.type === 'builtin')
                      .map((tool) => (
                        <SelectItem key={tool.name} value={tool.name} className="text-xs">
                          <span className="flex items-center gap-2">
                            {renderToolIcon({ name: tool.name, type: 'builtin', category: tool.category, size: 14 })}
                            <span>{tool.display_name || tool.name}</span>
                          </span>
                        </SelectItem>
                      ))}
                  </SelectGroup>
                  <SelectGroup>
                    <SelectLabel className="text-[11px] text-muted-foreground font-semibold">
                      {t('toolTypeMcp')}
                    </SelectLabel>
                    {connectableTools
                      .filter((t) => t.type === 'mcp')
                      .map((tool) => (
                        <SelectItem key={tool.id || tool.name} value={tool.id || tool.name} className="text-xs">
                          <span className="flex items-center gap-2">
                            {renderToolIcon({ name: tool.name, icon: tool.icon, type: 'mcp', size: 14 })}
                            <span>{tool.display_name || tool.name}</span>
                          </span>
                        </SelectItem>
                      ))}
                  </SelectGroup>
                  <SelectGroup>
                    <SelectLabel className="text-[11px] text-muted-foreground font-semibold">
                      {t('toolTypeCustom')}
                    </SelectLabel>
                    {connectableTools
                      .filter((t) => t.type === 'custom')
                      .map((tool) => (
                        <SelectItem key={tool.id || tool.name} value={tool.id || tool.name} className="text-xs">
                          <span className="flex items-center gap-2">
                            {renderToolIcon({ name: tool.name, icon: tool.icon, type: 'custom', custom_type: tool.custom_type, size: 14 })}
                            <span>{tool.display_name || tool.name}</span>
                          </span>
                        </SelectItem>
                      ))}
                  </SelectGroup>
                </SelectContent>
              </Select>
            </div>

            {selectedTool && (
              <>
                {selectedTool.description && (
                  <p className="text-xs text-muted-foreground bg-muted/30 rounded p-2">
                    {selectedTool.description}
                  </p>
                )}

                {/* Connection Name & Label */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div className="space-y-1">
                    <Label htmlFor="create-connection-name" className="text-xs">
                      {tTools('namePlaceholder')} <span className="text-destructive">*</span>
                    </Label>
                    <Input
                      id="create-connection-name"
                      value={name}
                      placeholder={tTools('namePlaceholder')}
                      className="h-8 text-xs"
                      onChange={(e) => setName(e.target.value)}
                    />
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor="create-account-label" className="text-xs">
                      {tTools('accountLabelPlaceholder')}
                    </Label>
                    <Input
                      id="create-account-label"
                      value={accountLabel}
                      placeholder={tTools('accountLabelPlaceholder')}
                      className="h-8 text-xs"
                      onChange={(e) => setAccountLabel(e.target.value)}
                    />
                  </div>
                </div>

                {/* Input mode switcher if URL/host modes are supported */}
                {selectedTool.connection_fields?.some((f) => f.input_mode) && (
                  <div className="space-y-1">
                    <Label className="text-xs">{tTools('connectionMethod')}</Label>
                    <Tabs
                      value={inputMode}
                      onValueChange={(val) => setInputMode(val as 'url' | 'host')}
                      className="w-full"
                    >
                      <TabsList className="h-7 text-xs grid grid-cols-2 w-48">
                        <TabsTrigger value="host" className="text-xs py-1">
                          {tTools('inputModes.host')}
                        </TabsTrigger>
                        <TabsTrigger value="url" className="text-xs py-1">
                          {tTools('inputModes.url')}
                        </TabsTrigger>
                      </TabsList>
                    </Tabs>
                  </div>
                )}

                {/* Credential Fields */}
                {visibleFields.length > 0 && (
                  <div className="space-y-2 border-t pt-2">
                    <p className="text-[11px] text-muted-foreground font-medium">
                      {tTools('secretFieldsHint')}
                    </p>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                      {visibleFields.map((field) => {
                        const fieldLabel = field.label_key ? tTools(field.label_key) : field.label || field.name
                        const fieldValue = secretValues[field.name] ?? field.default ?? ''
                        return (
                          <div key={field.name} className="space-y-1">
                            <Label htmlFor={`field-${field.name}`} className="text-xs">
                              {fieldLabel} {field.required && <span className="text-destructive">*</span>}
                            </Label>
                            {field.input_type === 'select' ? (
                              <Select
                                value={fieldValue}
                                onValueChange={(value) =>
                                  setSecretValues((prev) => ({ ...prev, [field.name]: value ?? '' }))
                                }
                              >
                                <SelectTrigger id={`field-${field.name}`} className="h-8 text-xs">
                                  <SelectValue>
                                    {field.name === 'ssl' ? tTools(`sslOptions.${fieldValue}`) : fieldValue}
                                  </SelectValue>
                                </SelectTrigger>
                                <SelectContent side="bottom" alignItemWithTrigger={false}>
                                  {(field.options ?? []).map((option) => (
                                    <SelectItem key={option} value={option} className="text-xs">
                                      {field.name === 'ssl' ? tTools(`sslOptions.${option}`) : option}
                                    </SelectItem>
                                  ))}
                                </SelectContent>
                              </Select>
                            ) : (
                              <Input
                                id={`field-${field.name}`}
                                type={field.input_type ?? (field.secret ? 'password' : 'text')}
                                autoComplete={
                                  field.secret || field.input_type === 'password'
                                    ? 'new-password'
                                    : 'off'
                                }
                                value={fieldValue}
                                placeholder={fieldLabel}
                                className="h-8 text-xs font-mono"
                                onChange={(e) =>
                                  setSecretValues((prev) => ({
                                    ...prev,
                                    [field.name]: e.target.value,
                                  }))
                                }
                              />
                            )}
                          </div>
                        )
                      })}
                    </div>
                  </div>
                )}

                {createError && <FieldError>{createError}</FieldError>}

                <div className="flex items-center justify-end gap-2 border-t pt-3">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="h-8 text-xs"
                    onClick={resetCreateState}
                    disabled={isSubmitting}
                  >
                    {tCommon('cancel')}
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    className="h-8 text-xs"
                    onClick={() => void handleCreate()}
                    disabled={isSubmitting}
                  >
                    {isSubmitting ? (
                      <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" />
                    ) : (
                      <Check className="h-3.5 w-3.5 mr-1.5" />
                    )}
                    {tTools('create')}
                  </Button>
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {/* Connections List */}
      <div className="space-y-3">
        {isLoading ? (
          <div className="space-y-2.5 py-4">
            <div className="h-16 w-full rounded-md border bg-muted/20 animate-pulse" />
            <div className="h-16 w-full rounded-md border bg-muted/20 animate-pulse" />
          </div>
        ) : connections.length === 0 ? (
          <div className="rounded-lg border border-dashed p-8 text-center space-y-3 bg-muted/10">
            <Link2 className="h-8 w-8 mx-auto text-muted-foreground/60" />
            <div className="space-y-1">
              <h4 className="text-sm font-semibold text-foreground">{t('emptyTitle')}</h4>
              <p className="text-xs text-muted-foreground max-w-md mx-auto">
                {t('emptyDescription')}
              </p>
            </div>
            {!isCreating && connectableTools.length > 0 && (
              <Button
                type="button"
                size="sm"
                className="h-8 text-xs mt-2"
                onClick={() => setIsCreating(true)}
              >
                <Plus className="h-3.5 w-3.5 mr-1.5" />
                {t('add')}
              </Button>
            )}
          </div>
        ) : (
          <div className="space-y-2.5">
            {connections.map((connection) => {
              const matchedTool = resolveToolForConnection(connection)
              const toolName = matchedTool?.display_name || matchedTool?.name || connection.builtin_tool_key || connection.name
              const isDefault = connection.is_default
              const isPersonal = connection.scope === 'user'
              // Team-wide connections are managed by team owners/admins; site
              // connections by site administrators in the tool manager. Hide
              // actions the caller cannot perform instead of failing later.
              const canManageConnection =
                connection.scope === 'user'
                || (connection.scope === 'team'
                  && (currentTeam.role === 'owner' || currentTeam.role === 'admin'))
              const status = connection.status
              const currentOauth = oauthStatus[connection.id]

              return (
                <div
                  key={connection.id}
                  className="rounded-lg border bg-card p-3.5 space-y-2.5 transition-colors hover:border-border/80"
                >
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2.5">
                    {/* Tool and Connection Title */}
                    <div className="flex items-start sm:items-center gap-3 min-w-0">
                      <div className="h-9 w-9 rounded-md border bg-muted/30 flex items-center justify-center shrink-0">
                        {renderToolIcon({
                          name: matchedTool?.name || connection.builtin_tool_key,
                          icon: matchedTool?.icon,
                          type: matchedTool?.type,
                          custom_type: matchedTool?.custom_type,
                          category: matchedTool?.category,
                          size: 18,
                        })}
                      </div>

                      <div className="min-w-0 space-y-0.5">
                        <div className="flex flex-wrap items-center gap-1.5">
                          <span className="text-xs font-semibold text-foreground truncate">
                            {toolName}
                          </span>
                          <span className="text-xs text-muted-foreground font-medium">
                            · {connection.name}
                          </span>

                          {/* Default badge */}
                          {isDefault && (
                            <Badge
                              variant="outline"
                              className="text-[10px] h-4.5 px-1.5 font-normal text-primary border-primary/30 flex items-center gap-0.5"
                            >
                              <Star className="h-2.5 w-2.5 fill-primary" />
                              {t('defaultBadge')}
                            </Badge>
                          )}

                          {/* Scope badge */}
                          <Badge
                            variant="secondary"
                            className="text-[10px] h-4.5 px-1.5 font-normal text-muted-foreground"
                          >
                            {isPersonal ? t('scopePersonal') : t('scopeTeam')}
                          </Badge>

                          {/* Status badge */}
                          {status === 'active' && (
                            <Badge
                              variant="outline"
                              className="text-[10px] h-4.5 px-1.5 font-normal border-emerald-500/40 text-emerald-600 dark:text-emerald-400 bg-emerald-50/50 dark:bg-emerald-950/20"
                            >
                              {tTools('status.active')}
                            </Badge>
                          )}
                          {status === 'reauth_required' && (
                            <Badge
                              variant="outline"
                              className="text-[10px] h-4.5 px-1.5 font-normal border-amber-500/40 text-amber-600 dark:text-amber-400 bg-amber-50/50 dark:bg-amber-950/20"
                            >
                              {t('reauthRequired')}
                            </Badge>
                          )}
                          {status === 'revoked' && (
                            <Badge
                              variant="outline"
                              className="text-[10px] h-4.5 px-1.5 font-normal border-destructive/40 text-destructive bg-destructive/10"
                            >
                              {tTools('status.revoked')}
                            </Badge>
                          )}
                        </div>

                        {connection.account_label && (
                          <p className="text-[11px] text-muted-foreground font-mono truncate">
                            {connection.account_label}
                          </p>
                        )}
                      </div>
                    </div>

                    {/* Actions */}
                    <div className="flex flex-wrap items-center gap-1 self-end sm:self-center shrink-0">
                      {canManageConnection && (
                        <>
                      {/* OAuth start / re-auth button */}
                      {(currentOauth?.provider_configured || status === 'reauth_required') && (
                        <Button
                          type="button"
                          variant={status === 'reauth_required' ? 'default' : 'outline'}
                          size="sm"
                          className="h-7 px-2 text-xs"
                          disabled={oauthStarting === connection.id}
                          onClick={() => void handleStartOAuth(connection)}
                        >
                          {oauthStarting === connection.id ? (
                            <Loader2 className="h-3 w-3 mr-1 animate-spin" />
                          ) : (
                            <ExternalLink className="h-3 w-3 mr-1" />
                          )}
                          {status === 'reauth_required' || currentOauth?.needs_reauth
                            ? t('reconnect')
                            : t('connect')}
                        </Button>
                      )}

                      {/* Set Default */}
                      {!isDefault && isPersonal && (
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          className="h-7 px-2 text-xs text-muted-foreground hover:text-foreground"
                          onClick={() => void handleSetDefault(connection)}
                        >
                          <Star className="h-3 w-3 mr-1" />
                          {t('setDefault')}
                        </Button>
                      )}

                      {/* Disconnect OAuth */}
                      {currentOauth?.provider_configured && (
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          className="h-7 px-2 text-xs text-muted-foreground hover:text-destructive"
                          disabled={oauthStarting === connection.id}
                          onClick={() => setPendingAction({ kind: 'disconnect', connection })}
                        >
                          {tTools('oauthDisconnect')}
                        </Button>
                      )}

                      {/* Client Secret config entry if needed */}
                      {currentOauth?.provider_configured && (
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          className="h-7 px-2 text-xs text-muted-foreground hover:text-foreground"
                          onClick={() => {
                            setClientSecretFor((cur) => (cur === connection.id ? null : connection.id))
                            setClientSecretValue('')
                          }}
                        >
                          {tTools('oauthClientSecret')}
                        </Button>
                      )}

                      {/* Revoke / Delete */}
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7 text-muted-foreground hover:text-destructive"
                        title={tTools('revoke')}
                        onClick={() => setPendingAction({ kind: 'revoke', connection })}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                        </>
                      )}
                    </div>
                  </div>

                  {/* Inline Client Secret form if opened */}
                  {canManageConnection && clientSecretFor === connection.id && (
                    <div className="space-y-1.5 rounded border border-dashed p-2.5 bg-muted/20">
                      <Label htmlFor={`client-secret-${connection.id}`} className="text-[11px] font-medium">
                        {tTools('oauthClientSecret')}
                      </Label>
                      <Input
                        id={`client-secret-${connection.id}`}
                        type="password"
                        autoComplete="new-password"
                        value={clientSecretValue}
                        placeholder={tTools('oauthClientSecretPlaceholder')}
                        className="h-7 text-xs font-mono"
                        onChange={(e) => setClientSecretValue(e.target.value)}
                      />
                      <p className="text-[10px] text-muted-foreground">
                        {tTools('oauthClientSecretHint')}
                      </p>
                      <div className="flex gap-1.5 pt-1">
                        <Button
                          type="button"
                          size="sm"
                          className="h-6 text-[11px]"
                          disabled={!clientSecretValue.trim() || oauthStarting === connection.id}
                          onClick={() => void handleStartOAuth(connection, clientSecretValue)}
                        >
                          {tTools('oauthSaveSecret')}
                        </Button>
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          className="h-6 text-[11px]"
                          onClick={() => {
                            setClientSecretFor(null)
                            setClientSecretValue('')
                          }}
                        >
                          {tCommon('cancel')}
                        </Button>
                      </div>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>

      <AlertDialog
        open={pendingAction !== null}
        onOpenChange={(open) => {
          if (!open) setPendingAction(null)
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {pendingAction?.kind === 'disconnect'
                ? t('oauthDisconnectConfirmTitle')
                : t('revokeConfirmTitle')}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {pendingAction?.kind === 'disconnect'
                ? t('oauthDisconnectConfirmDescription')
                : t('revokeConfirmDescription')}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{tCommon('cancel')}</AlertDialogCancel>
            <AlertDialogAction variant="destructive" onClick={() => void handleConfirmPendingAction()}>
              {pendingAction?.kind === 'disconnect'
                ? t('oauthDisconnectConfirmAction')
                : t('revokeConfirmAction')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
