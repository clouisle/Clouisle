'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { Check, ChevronDown, ChevronRight, Copy, Loader2, RefreshCw, Save } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { integrationsApi } from '@/lib/api/admin/integrations'
import type { FeishuAgentChatConfig, FeishuConfig, FeishuDepartment, FeishuTestRecipient, Integration } from '@/lib/api/admin/integrations'
import { ApiError } from '@/lib/api/client'
import { API_BASE_URL } from '@/lib/constants'

export type FeishuSettingsTab = 'configuration' | 'directory' | 'notification' | 'agentChat' | 'knowledge'

/**
 * The axios interceptor already toasts backend messages, so only fill the gap it leaves:
 * validation errors (reserved for field level feedback) and non-API failures.
 */
function toastFallback(error: unknown, fallback: string) {
  if (error instanceof ApiError && !error.isValidationError()) return
  toast.error(fallback)
}

function collectDepartmentIds(department: FeishuDepartment): string[] {
  return [department.department_id, ...department.children.flatMap(collectDepartmentIds)]
}

function DepartmentRow({
  department,
  depth,
  selectedIds,
  onToggle,
  canUpdate,
}: {
  department: FeishuDepartment
  depth: number
  selectedIds: Record<string, true>
  onToggle: (department: FeishuDepartment, checked: boolean) => void
  canUpdate: boolean
}) {
  const [expanded, setExpanded] = React.useState(true)
  const childIds = department.children.flatMap(collectDepartmentIds)
  const allIds = [department.department_id, ...childIds]
  const checkedCount = allIds.filter((id) => Boolean(selectedIds[id])).length
  const checked = checkedCount === allIds.length
  const indeterminate = checkedCount > 0 && !checked
  return (
    <div>
      <div className="flex min-h-10 items-center gap-2" style={{ paddingInlineStart: `${depth * 20}px` }}>
        {department.children.length > 0 ? (
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="h-7 w-7 shrink-0"
            aria-label={expanded ? 'Collapse department' : 'Expand department'}
            aria-expanded={expanded}
            onClick={() => setExpanded((value) => !value)}
          >
            {expanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
          </Button>
        ) : <span className="w-7 shrink-0" />}
        <Checkbox
          checked={checked || indeterminate}
          disabled={!canUpdate}
          aria-label={department.name}
          onCheckedChange={(value) => onToggle(department, value === true)}
        />
        <span className="truncate text-sm">{department.name}</span>
      </div>
      {expanded && department.children.length > 0 && (
        <div role="group">
          {department.children.map((child) => (
            <DepartmentRow key={child.department_id} department={child} depth={depth + 1} selectedIds={selectedIds} onToggle={onToggle} canUpdate={canUpdate} />
          ))}
        </div>
      )}
    </div>
  )
}

export function FeishuIntegrationTab({
  config,
  onConfigChange,
  canUpdate,
  integration,
  canUpdateLogin,
  onIntegrationChange,
  tab,
}: {
  config: FeishuConfig
  onConfigChange: (config: FeishuConfig) => void
  canUpdate: boolean
  integration: Integration | null
  canUpdateLogin: boolean
  onIntegrationChange: (integration: Integration) => void
  tab: FeishuSettingsTab
}) {
  const t = useTranslations('siteSettings')
  const [appId, setAppId] = React.useState(config.app_id)
  const [appSecret, setAppSecret] = React.useState('')
  const [departments, setDepartments] = React.useState<FeishuDepartment[]>([])
  const [selectedIds, setSelectedIds] = React.useState<Record<string, true>>(() => Object.fromEntries(config.department_ids.map((id) => [id, true])) as Record<string, true>)
  const [loadingDepartments, setLoadingDepartments] = React.useState(false)
  const [saving, setSaving] = React.useState(false)
  const [savingScope, setSavingScope] = React.useState(false)
  const [syncing, setSyncing] = React.useState(false)
  const [checkingConnection, setCheckingConnection] = React.useState(false)
  const [testRecipients, setTestRecipients] = React.useState<FeishuTestRecipient[]>([])
  const [testRecipientId, setTestRecipientId] = React.useState('')
  const [testTitle, setTestTitle] = React.useState('Clouisle Feishu test')
  const [testContent, setTestContent] = React.useState('This is a test message from Clouisle.')
  const [sendingTest, setSendingTest] = React.useState(false)
  const [agentChatConfig, setAgentChatConfig] = React.useState<FeishuAgentChatConfig | null>(null)
  const [agentChatConnectionMode, setAgentChatConnectionMode] = React.useState<FeishuAgentChatConfig['connection_mode']>('callback')
  const [agentChatVerificationToken, setAgentChatVerificationToken] = React.useState('')
  const [agentChatEncryptKey, setAgentChatEncryptKey] = React.useState('')
  const [loadingAgentChat, setLoadingAgentChat] = React.useState(false)
  const [savingAgentChat, setSavingAgentChat] = React.useState(false)

  const enabledCapabilities = integration?.enabled_capabilities
  const savedButtonText = integration?.button_text ?? ''
  const savedDirectorySync = Boolean(integration?.is_enabled && integration.enabled_capabilities.includes('directory_sync'))
  const savedLoginEnabled = Boolean(integration?.is_enabled && integration.enabled_capabilities.includes('user_login'))
  const savedNotificationEnabled = Boolean(integration?.is_enabled && integration.enabled_capabilities.includes('notification'))
  const savedAgentChatEnabled = Boolean(integration?.is_enabled && integration.enabled_capabilities.includes('agent_chat'))
  const [directorySyncEnabled, setDirectorySyncEnabled] = React.useState(savedDirectorySync)
  const [loginEnabled, setLoginEnabled] = React.useState(savedLoginEnabled)
  const [notificationEnabled, setNotificationEnabled] = React.useState(savedNotificationEnabled)
  const [agentChatEnabled, setAgentChatEnabled] = React.useState(savedAgentChatEnabled)
  const [buttonText, setButtonText] = React.useState(savedButtonText)
  const [savingCapabilities, setSavingCapabilities] = React.useState(false)
  const [copiedRedirect, setCopiedRedirect] = React.useState(false)
  const copyTimeoutRef = React.useRef<number | undefined>(undefined)

  React.useEffect(() => {
    setAppId(config.app_id)
    setSelectedIds(Object.fromEntries(config.department_ids.map((id) => [id, true])) as Record<string, true>)
  }, [config.app_id, config.department_ids])

  React.useEffect(() => {
    setDirectorySyncEnabled(savedDirectorySync)
    setLoginEnabled(savedLoginEnabled)
    setNotificationEnabled(savedNotificationEnabled)
    setAgentChatEnabled(savedAgentChatEnabled)
    setButtonText(savedButtonText)
  }, [enabledCapabilities, savedDirectorySync, savedLoginEnabled, savedNotificationEnabled, savedAgentChatEnabled, savedButtonText])

  // Feature selection stays editable even when a legacy record was disabled.
  const capabilitiesReadOnly = !integration
  const canEditDirectorySync = tab === 'configuration' && canUpdate && !capabilitiesReadOnly
  const canEditNotification = tab === 'configuration' && canUpdate && !capabilitiesReadOnly
  const canEditAgentChat = tab === 'configuration' && canUpdate && !capabilitiesReadOnly
  const canEditLogin = tab === 'configuration' && canUpdateLogin && !capabilitiesReadOnly
  const nextCapabilities = integration
    ? integration.supported_capabilities.filter((capability) => {
        if (capability === 'directory_sync') {
          return canEditDirectorySync
            ? directorySyncEnabled
            : integration.is_enabled && integration.enabled_capabilities.includes(capability)
        }
        if (capability === 'user_login') {
          return canEditLogin ? loginEnabled : integration.is_enabled && integration.enabled_capabilities.includes(capability)
        }
        if (capability === 'notification') {
          return canEditNotification
            ? notificationEnabled
            : integration.is_enabled && integration.enabled_capabilities.includes(capability)
        }
        if (capability === 'agent_chat') {
          return canEditAgentChat
            ? agentChatEnabled
            : integration.is_enabled && integration.enabled_capabilities.includes(capability)
        }
        return false
      })
    : []
  const capabilitiesChanged = integration
    ? nextCapabilities.join() !== (integration.is_enabled ? integration.enabled_capabilities : []).join()
    : false
  const canSaveCapabilities = Boolean(integration) && !capabilitiesReadOnly
    && (capabilitiesChanged || (canEditLogin && buttonText.trim() !== savedButtonText.trim()))
  const configChanged = appId.trim() !== config.app_id || appSecret.trim().length > 0
  const canSaveConfiguration = canUpdate && Boolean(appId.trim()) && configChanged
  // Departments require saved app credentials and an enabled directory capability.
  const departmentsAvailable = config.app_secret_configured && config.is_enabled && savedDirectorySync

  // The Feishu app must allowlist this exact URL before event delivery works.
  const agentChatCallbackUrl = React.useMemo(() => {
    if (typeof window === 'undefined') return ''
    try {
      const base = new URL(API_BASE_URL, window.location.origin)
      return `${base.origin}${base.pathname.replace(/\/$/, '')}/integrations/feishu/callback`
    } catch {
      return ''
    }
  }, [])

  // Agent chat settings load lazily: only the administrator who opens the tab
  // pays for them, and a capability that is off never issues the requests.
  const agentChatAvailable = Boolean(config.app_secret_configured && config.app_id)
  React.useEffect(() => {
    if (tab !== 'agentChat' || !agentChatAvailable || !savedAgentChatEnabled) return
    let active = true
    setLoadingAgentChat(true)
    void integrationsApi.getFeishuAgentChatConfig()
      .then((agentChat) => {
        if (!active) return
        setAgentChatConfig(agentChat)
        setAgentChatConnectionMode(agentChat.connection_mode)
      })
      .catch((error) => {
        console.error('Failed to load Feishu agent chat configuration:', error)
        if (active) toastFallback(error, t('integrations.feishuAgentChatConfigFailed'))
      })
      .finally(() => {
        if (active) setLoadingAgentChat(false)
      })
    return () => { active = false }
  }, [tab, agentChatAvailable, savedAgentChatEnabled, t])

  React.useEffect(() => {
    if (tab !== 'agentChat' || !agentChatAvailable || !savedAgentChatEnabled) return
    let active = true
    let inFlight = false
    const timer = window.setInterval(() => {
      if (inFlight) return
      inFlight = true
      void integrationsApi.getFeishuAgentChatConfig().then(result => {
        if (active) setAgentChatConfig(current => current ? { ...current, receiver_status: result.receiver_status } : current)
      }).catch(() => {
        if (active) setAgentChatConfig(current => current ? { ...current, receiver_status: { state: 'error', managed: true } } : current)
      }).finally(() => { inFlight = false })
    }, 5000)
    return () => { active = false; window.clearInterval(timer) }
  }, [tab, agentChatAvailable, savedAgentChatEnabled])

  // The Feishu app must allowlist this exact URL before sign-in callbacks work.
  const redirectUrl = React.useMemo(() => {
    if (!integration || typeof window === 'undefined') return ''
    try {
      const base = new URL(API_BASE_URL, window.location.origin)
      return `${base.origin}${base.pathname.replace(/\/$/, '')}/sso/callback/${integration.name}`
    } catch {
      return ''
    }
  }, [integration])

  React.useEffect(() => () => {
    window.clearTimeout(copyTimeoutRef.current)
  }, [])

  const copyRedirectUrl = async () => {
    if (!redirectUrl) return
    await navigator.clipboard.writeText(redirectUrl)
    setCopiedRedirect(true)
    window.clearTimeout(copyTimeoutRef.current)
    copyTimeoutRef.current = window.setTimeout(() => setCopiedRedirect(false), 2000)
  }

  const loadDepartments = React.useCallback(async () => {
    if (!departmentsAvailable) return
    setLoadingDepartments(true)
    try {
      setDepartments(await integrationsApi.getFeishuDepartments())
    } catch (error) {
      console.error('Failed to load Feishu departments:', error)
      toastFallback(error, t('integrations.feishuDepartmentsFailed'))
    } finally {
      setLoadingDepartments(false)
    }
  }, [departmentsAvailable, t])

  React.useEffect(() => {
    loadDepartments()
  }, [loadDepartments])

  const toggleDepartment = (department: FeishuDepartment, checked: boolean) => {
    if (!canUpdate) return
    setSelectedIds((current) => {
      const next = { ...current }
      for (const id of collectDepartmentIds(department)) {
        if (checked) next[id] = true
        else delete next[id]
      }
      return next
    })
  }

  const saveConfiguration = async () => {
    if (saving || savingCapabilities) return
    const shouldSaveConfig = canSaveConfiguration
    const shouldSaveCapabilities = canSaveCapabilities
    if (!shouldSaveConfig && !shouldSaveCapabilities) return

    setSaving(true)
    setSavingCapabilities(true)
    try {
      if (shouldSaveConfig) {
        const result = await integrationsApi.updateFeishuConfig({
          app_id: appId.trim(),
          app_secret: appSecret.trim() || undefined,
        })
        setAppSecret('')
        onConfigChange({ ...config, ...result })
      }
      if (shouldSaveCapabilities && integration) {
        const updated = await integrationsApi.update(integration.id, {
          enabled_capabilities: nextCapabilities,
          ...(canEditLogin ? { button_text: buttonText.trim() || null } : {}),
        })
        onIntegrationChange(updated)
      }
      toast.success(t('saveSuccess'))
    } catch (error) {
      console.error('Failed to save Feishu settings:', error)
      toastFallback(error, t('integrations.feishuSaveFailed'))
    } finally {
      setSaving(false)
      setSavingCapabilities(false)
    }
  }


  const agentChatSecretsChanged = agentChatConnectionMode === 'callback'
    && (agentChatVerificationToken.trim().length > 0 || agentChatEncryptKey.trim().length > 0)
  const agentChatModeChanged = Boolean(agentChatConfig)
    && agentChatConnectionMode !== agentChatConfig?.connection_mode
  const canSaveAgentChat = canUpdate && !loadingAgentChat && Boolean(agentChatConfig)
    && (agentChatSecretsChanged || agentChatModeChanged)
  const agentChatConnectionModes = [
    { value: 'callback', label: t('integrations.feishuAgentChatCallbackMode') },
    { value: 'long_connection', label: t('integrations.feishuAgentChatLongConnectionMode') },
  ] as const

  const saveAgentChat = async () => {
    if (savingAgentChat || !canSaveAgentChat) return
    setSavingAgentChat(true)
    try {
      const result = await integrationsApi.updateFeishuAgentChatConfig({
        connection_mode: agentChatConnectionMode,
        ...(agentChatSecretsChanged ? {
          event_verification_token: agentChatVerificationToken.trim() || undefined,
          event_encrypt_key: agentChatEncryptKey.trim() || undefined,
        } : {}),
      })
      setAgentChatConfig(result)
      setAgentChatConnectionMode(result.connection_mode)
      setAgentChatVerificationToken('')
      setAgentChatEncryptKey('')
      toast.success(t('integrations.feishuAgentChatSaved'))
    } catch (error) {
      console.error('Failed to save Feishu agent chat configuration:', error)
      toastFallback(error, t('integrations.feishuAgentChatSaveFailed'))
    } finally {
      setSavingAgentChat(false)
    }
  }

  const saveScope = async () => {
    if (!canUpdate) return
    setSavingScope(true)
    try {
      const result = await integrationsApi.updateFeishuDepartmentScope(Object.keys(selectedIds))
      setSelectedIds(Object.fromEntries(result.department_ids.map((id) => [id, true])) as Record<string, true>)
      onConfigChange({ ...config, department_ids: result.department_ids })
      toast.success(t('integrations.feishuScopeSaved'))
    } catch (error) {
      console.error('Failed to save Feishu department scope:', error)
      toastFallback(error, t('integrations.feishuScopeSaveFailed'))
    } finally {
      setSavingScope(false)
    }
  }

  const sync = async () => {
    if (!canUpdate || !config.is_enabled) return
    setSyncing(true)
    try {
      const result = await integrationsApi.syncFeishuContacts()
      toast.success(t('integrations.feishuSyncResult', { ...result, teams_created: result.teams_created }))
    } catch (error) {
      console.error('Failed to sync Feishu directory:', error)
      toastFallback(error, t('integrations.feishuSyncFailed'))
    } finally {
      setSyncing(false)
    }
  }

  const checkConnection = async () => {
    if (!canUpdate || !config.is_enabled) return
    setCheckingConnection(true)
    try {
      await integrationsApi.checkFeishuConnection()
      toast.success(t('integrations.feishuConnectionCheckSuccess'))
    } catch (error) {
      console.error('Feishu connection check failed:', error)
      toastFallback(error, t('integrations.feishuConnectionCheckFailed'))
    } finally {
      setCheckingConnection(false)
    }
  }

  const loadTestRecipients = React.useCallback(async () => {
    try {
      const result = await integrationsApi.getFeishuTestRecipients()
      setTestRecipients(result)
      setTestRecipientId((current) => result.some((recipient) => recipient.id === current) ? current : '')
    } catch (error) {
      console.error('Failed to load Feishu test recipients:', error)
      toastFallback(error, t('integrations.feishuTestFailed'))
    }
  }, [t])

  const sendTestMessage = async () => {
    setSendingTest(true)
    try {
      await integrationsApi.sendFeishuTestMessage(testRecipientId, testTitle.trim(), testContent.trim())
      toast.success(t('integrations.feishuTestSent'))
    } catch (error) {
      console.error('Failed to send Feishu test message:', error)
      toastFallback(error, t('integrations.feishuTestFailed'))
    } finally {
      setSendingTest(false)
    }
  }

  React.useEffect(() => {
    if (tab === 'notification' && savedNotificationEnabled && config.is_enabled) loadTestRecipients()
  }, [tab, savedNotificationEnabled, config.is_enabled, loadTestRecipients])

  return (
    <Card>
      <CardContent className="space-y-5">
        {tab === 'configuration' && <div className="space-y-5">
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="feishu-app-id">{t('integrations.feishuAppId')}</Label>
                <Input id="feishu-app-id" value={appId} onChange={(event) => setAppId(event.target.value)} disabled={!canUpdate} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="feishu-app-secret">{t('integrations.feishuAppSecret')}</Label>
                <Input
                  id="feishu-app-secret"
                  type="password"
                  autoComplete="new-password"
                  value={appSecret}
                  onChange={(event) => setAppSecret(event.target.value)}
                  placeholder={config.app_secret_configured ? t('integrations.feishuSecretConfigured') : ''}
                  disabled={!canUpdate}
                />
                <p className="text-xs text-muted-foreground">{t('integrations.feishuAppSecretDesc')}</p>
              </div>
            </div>
            <section data-testid="feishu-capabilities" className="space-y-4">
              {canUpdate && (
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <h3 className="text-sm font-medium">{t('integrations.capabilities.directory_sync')}</h3>
                    <p className="text-xs text-muted-foreground">{t('integrations.feishuDirectorySyncDescription')}</p>
                  </div>
                  <Switch
                    aria-label={t('integrations.capabilities.directory_sync')}
                    checked={directorySyncEnabled}
                    disabled={!canEditDirectorySync || savingCapabilities}
                    onCheckedChange={setDirectorySyncEnabled}
                  />
                </div>
              )}
              {canUpdateLogin && (
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <h3 className="text-sm font-medium">{t('integrations.feishuLogin')}</h3>
                    <p className="text-xs text-muted-foreground">{t('integrations.feishuLoginDescription')}</p>
                  </div>
                  <Switch
                    aria-label={t('integrations.feishuLogin')}
                    checked={loginEnabled}
                    disabled={!canEditLogin || savingCapabilities}
                    onCheckedChange={setLoginEnabled}
                  />
                </div>
              )}
              {canEditLogin && (
                <div className="space-y-2">
                  <Label htmlFor="feishu-button-text">{t('integrations.feishuButtonText')}</Label>
                  <Input
                    id="feishu-button-text"
                    value={buttonText}
                    onChange={(event) => setButtonText(event.target.value)}
                    disabled={!canEditLogin || savingCapabilities}
                  />
                  <p className="text-xs text-muted-foreground">{t('integrations.feishuButtonTextDesc')}</p>
                </div>
              )}
              {canUpdate && (
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <h3 className="text-sm font-medium">{t('integrations.feishuAgentChat')}</h3>
                    <p className="text-xs text-muted-foreground">{t('integrations.feishuAgentChatDescription')}</p>
                  </div>
                  <Switch
                    aria-label={t('integrations.feishuAgentChat')}
                    checked={agentChatEnabled}
                    disabled={!canEditAgentChat || savingCapabilities}
                    onCheckedChange={setAgentChatEnabled}
                  />
                </div>
              )}
              <div className="space-y-2">
                <Label htmlFor="feishu-redirect-url">{t('integrations.callbackUrl')}</Label>
                <div className="flex items-center gap-2">
                  <code
                    id="feishu-redirect-url"
                    className="min-w-0 flex-1 overflow-x-auto rounded-md bg-muted px-3 py-2 font-mono text-xs"
                  >
                    {redirectUrl}
                  </code>
                  <Button
                    type="button"
                    variant="outline"
                    size="icon-sm"
                    aria-label={t('integrations.callbackUrl')}
                    onClick={copyRedirectUrl}
                  >
                    {copiedRedirect ? <Check className="h-4 w-4 text-green-600" /> : <Copy className="h-4 w-4" />}
                  </Button>
                </div>
                <p className="text-xs text-muted-foreground">{t('integrations.callbackUrlDesc')}</p>
              </div>
              {canUpdate && (
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <h3 className="text-sm font-medium">{t('integrations.capabilities.notification')}</h3>
                    <p className="text-xs text-muted-foreground">{t('integrations.feishuNotificationDescription')}</p>
                  </div>
                  <Switch
                    aria-label={t('integrations.capabilities.notification')}
                    checked={notificationEnabled}
                    disabled={!canEditNotification || savingCapabilities}
                    onCheckedChange={setNotificationEnabled}
                  />
                </div>
              )}
            </section>
            {(canUpdate || canEditDirectorySync || canEditLogin || canEditNotification || canEditAgentChat) && (
              <div className="flex justify-end">
                <Button type="button" data-testid="feishu-settings-save" variant="outline" onClick={saveConfiguration} disabled={(!canSaveConfiguration && !canSaveCapabilities) || saving || savingCapabilities}>
                  {saving || savingCapabilities ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                  {t('save')}
                </Button>
              </div>
            )}
        </div>}
        {tab === 'directory' && <div className="space-y-5">
            {!savedDirectorySync ? (
              <p className="rounded-md border p-3 text-sm text-muted-foreground">{t('integrations.feishuDirectorySyncDisabledHint')}</p>
            ) : !config.app_secret_configured || !config.is_enabled ? (
              <p className="rounded-md border p-3 text-sm text-muted-foreground">{t('integrations.feishuDirectorySyncUnavailable')}</p>
            ) : (
              <section className="space-y-3" aria-labelledby="feishu-departments-title">
                <div>
                  <h3 id="feishu-departments-title" className="text-sm font-medium">{t('integrations.feishuDepartments')}</h3>
                  <p className="text-xs text-muted-foreground">{t('integrations.feishuDepartmentsDesc')}</p>
                </div>
                {loadingDepartments ? (
                  <div className="flex items-center gap-2 py-4 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" />{t('integrations.feishuLoadingDepartments')}</div>
                ) : departments.length > 0 ? (
                  <ScrollArea className="max-h-72 rounded-md border p-2">
                    <div role="tree" aria-label={t('integrations.feishuDepartments')}>
                      {departments.map((department) => (
                        <DepartmentRow key={department.department_id} department={department} depth={0} selectedIds={selectedIds} onToggle={toggleDepartment} canUpdate={canUpdate} />
                      ))}
                    </div>
                  </ScrollArea>
                ) : (
                  <p className="rounded-md border p-3 text-sm text-muted-foreground">{t('integrations.feishuNoDepartments')}</p>
                )}
                {canUpdate && (
                  <div className="flex flex-wrap justify-end gap-2">
                    <Button type="button" variant="outline" onClick={loadDepartments} disabled={loadingDepartments}>
                      {loadingDepartments ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
                      {t('integrations.feishuRefreshDepartments')}
                    </Button>
                    <Button type="button" variant="outline" onClick={saveScope} disabled={savingScope || Object.keys(selectedIds).length === 0}>
                      {savingScope ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                      {t('integrations.feishuSaveScope')}
                    </Button>
                    <Button type="button" onClick={sync} disabled={syncing || !config.is_enabled || config.department_ids.length === 0}>
                      {syncing ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
                      {t('integrations.feishuSync')}
                    </Button>
                  </div>
                )}
              </section>
            )}
        </div>}
        {tab === 'agentChat' && <div className="space-y-5" data-testid="feishu-agent-chat">
            <section className="space-y-2 rounded-md border p-3 text-sm" aria-labelledby="feishu-agent-chat-requirements-title">
              <h3 id="feishu-agent-chat-requirements-title" className="font-medium">{t('integrations.feishuAgentChatRequirementsTitle')}</h3>
              <p className="text-muted-foreground">{t('integrations.feishuAgentChatRequirementsIntro')}</p>
              <ul className="list-disc space-y-1 pl-5 text-muted-foreground">
                <li><code className="break-all text-xs">im:message.p2p_msg:readonly</code> — {t('integrations.feishuAgentChatReceivePermission')}</li>
                <li><code className="break-all text-xs">im:message:send_as_bot</code> — {t('integrations.feishuAgentChatSendPermission')}</li>
                <li><code className="break-all text-xs">im:resource</code> — {t('integrations.feishuAgentChatMediaPermission')}</li>
                <li><code className="break-all text-xs">contact:user.base:readonly</code> — {t('integrations.feishuAgentChatIdentityPermission')}</li>
              </ul>
              <p className="text-muted-foreground">{t('integrations.feishuAgentChatPublishRequirements')}</p>
              <p className="text-muted-foreground">{t('integrations.feishuAgentChatConnectionNotice')}</p>
            </section>
            {!savedAgentChatEnabled ? (
              <p className="rounded-md border p-3 text-sm text-muted-foreground">{t('integrations.feishuAgentChatDisabledHint')}</p>
            ) : !agentChatAvailable ? (
              <p className="rounded-md border p-3 text-sm text-muted-foreground">{t('integrations.feishuAgentChatUnavailable')}</p>
            ) : (
              <>
                <div className="space-y-2">
                  <Label htmlFor="feishu-agent-chat-connection-mode">{t('integrations.feishuAgentChatConnectionMode')}</Label>
                  <Select
                    value={agentChatConnectionMode}
                    disabled={!canUpdate || loadingAgentChat || savingAgentChat || !agentChatConfig}
                    onValueChange={(value) => {
                      if (value === 'callback' || value === 'long_connection') setAgentChatConnectionMode(value)
                    }}
                  >
                    <SelectTrigger id="feishu-agent-chat-connection-mode" className="w-full">
                      <SelectValue>{agentChatConnectionModes.find((mode) => mode.value === agentChatConnectionMode)?.label}</SelectValue>
                    </SelectTrigger>
                    <SelectContent>
                      {agentChatConnectionModes.map((mode) => (
                        <SelectItem key={mode.value} value={mode.value}>{mode.label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                {agentChatConnectionMode === 'long_connection' ? (
                  <section className="space-y-2 rounded-md border p-3" data-testid="feishu-agent-chat-long-connection">
                    <p className="text-sm">{t('integrations.feishuAgentChatLongConnectionDesc')}</p>
                    <p className="text-xs text-muted-foreground">{t('integrations.feishuAgentChatLongConnectionSetup')}</p>
                    <p role="status" className="text-sm">{t('integrations.feishuReceiverStatus')}: {t(`integrations.feishuReceiverStates.${agentChatConfig?.receiver_status.state ?? 'waiting'}`)}</p>
                    <p className="text-xs text-muted-foreground">{t('integrations.feishuAgentChatLongConnectionProcess')}</p>
                  </section>
                ) : <>
                <div className="space-y-2">
                  <Label htmlFor="feishu-agent-chat-callback-url">{t('integrations.feishuAgentChatCallbackUrl')}</Label>
                  <div className="flex items-center gap-2">
                    <code
                      id="feishu-agent-chat-callback-url"
                      className="min-w-0 flex-1 overflow-x-auto rounded-md bg-muted px-3 py-2 font-mono text-xs"
                    >
                      {agentChatCallbackUrl}
                    </code>
                    <Button
                      type="button"
                      variant="outline"
                      size="icon-sm"
                      aria-label={t('integrations.feishuAgentChatCallbackUrl')}
                      onClick={() => void navigator.clipboard.writeText(agentChatCallbackUrl)}
                    >
                      <Copy className="h-4 w-4" />
                    </Button>
                  </div>
                  <p className="text-xs text-muted-foreground">{t('integrations.feishuAgentChatCallbackUrlDesc')}</p>
                </div>
                <div className="grid gap-4 sm:grid-cols-2">
                  <div className="space-y-2">
                    <Label htmlFor="feishu-agent-chat-verification-token">{t('integrations.feishuAgentChatVerificationToken')}</Label>
                    <Input
                      id="feishu-agent-chat-verification-token"
                      type="password"
                      autoComplete="new-password"
                      value={agentChatVerificationToken}
                      onChange={(event) => setAgentChatVerificationToken(event.target.value)}
                      placeholder={agentChatConfig?.event_verification_token_configured ? t('integrations.feishuSecretConfigured') : ''}
                      disabled={!canUpdate}
                    />
                    <p className="text-xs text-muted-foreground">{t('integrations.feishuAgentChatVerificationTokenDesc')}</p>
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="feishu-agent-chat-encrypt-key">{t('integrations.feishuAgentChatEncryptKey')}</Label>
                    <Input
                      id="feishu-agent-chat-encrypt-key"
                      type="password"
                      autoComplete="new-password"
                      value={agentChatEncryptKey}
                      onChange={(event) => setAgentChatEncryptKey(event.target.value)}
                      placeholder={agentChatConfig?.event_encrypt_key_configured ? t('integrations.feishuSecretConfigured') : ''}
                      disabled={!canUpdate}
                    />
                    <p className="text-xs text-muted-foreground">{t('integrations.feishuAgentChatEncryptKeyDesc')}</p>
                  </div>
                </div>
                </>}
                <p className="rounded-md border p-3 text-sm text-muted-foreground">{t('integrations.feishuAgentChatPersonalSelection')}</p>
                {canUpdate && (
                  <div className="flex justify-end">
                    <Button
                      type="button"
                      data-testid="feishu-agent-chat-save"
                      variant="outline"
                      onClick={saveAgentChat}
                      disabled={!canSaveAgentChat || savingAgentChat}
                    >
                      {savingAgentChat ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                      {t('save')}
                    </Button>
                  </div>
                )}
              </>
            )}
        </div>}
        {tab === 'notification' && <div className="space-y-5">
            {!savedNotificationEnabled ? (
              <p className="rounded-md border p-3 text-sm text-muted-foreground">{t('integrations.feishuNotificationDisabledHint')}</p>
            ) : (
              <section className="space-y-4" aria-labelledby="feishu-notification-test-title">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <h3 id="feishu-notification-test-title" className="text-sm font-medium">{t('integrations.feishuTestMessage')}</h3>
                    <p className="text-xs text-muted-foreground">{t('integrations.feishuNotificationDescription')}</p>
                  </div>
                  <Button type="button" variant="outline" onClick={checkConnection} disabled={checkingConnection || !config.is_enabled}>
                    {checkingConnection && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                    {t('integrations.feishuConnectionCheck')}
                  </Button>
                </div>
                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="space-y-2">
                    <Label htmlFor="feishu-test-recipient-trigger">{t('integrations.feishuTestRecipient')}</Label>
                    <Select value={testRecipientId} onValueChange={(value) => setTestRecipientId(value ?? '')}>
                      <SelectTrigger id="feishu-test-recipient-trigger" aria-label={t('integrations.feishuTestRecipient')} className="w-full">
                        <SelectValue placeholder={testRecipients.length ? t('integrations.feishuTestRecipientPlaceholder') : t('integrations.feishuNoTestRecipients')}>
                          {testRecipients.find((recipient) => recipient.id === testRecipientId)?.username ?? ''}
                        </SelectValue>
                      </SelectTrigger>
                      <SelectContent>
                        {testRecipients.map((recipient) => (
                          <SelectItem key={recipient.id} value={recipient.id}>
                            {recipient.username}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="feishu-test-title">{t('integrations.feishuTestTitle')}</Label>
                    <Input id="feishu-test-title" value={testTitle} onChange={(event) => setTestTitle(event.target.value)} maxLength={200} />
                  </div>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="feishu-test-content">{t('integrations.feishuTestContent')}</Label>
                  <Textarea id="feishu-test-content" value={testContent} onChange={(event) => setTestContent(event.target.value)} maxLength={2000} rows={3} />
                </div>
                <div className="flex justify-end">
                  <Button type="button" onClick={sendTestMessage} disabled={sendingTest || !testRecipientId || !testTitle.trim() || !testContent.trim() || !savedNotificationEnabled}>
                    {sendingTest && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                    {t('integrations.feishuTestSend')}
                  </Button>
                </div>
              </section>
            )}
        </div>}
      </CardContent>
    </Card>
  )
}
