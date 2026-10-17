'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { useRouter } from 'next/navigation'
import { toast } from 'sonner'
import { Globe, Mail, Plus, Settings2, Shield, Trash2 } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { Badge } from '@/components/ui/badge'
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from '@/components/ui/alert-dialog'
import { useCanPerform } from '@/components/permission-guard'
import { integrationsApi, type Integration, type IntegrationType, type FeishuConfig } from '@/lib/api/admin/integrations'
import type { EmailSettings, WebhookSettings } from '@/lib/api/site-settings'
import { LoginIntegrationDialog } from './_components/login-integration-dialog'

type BuiltinType = 'email' | 'webhook' | 'feishu'

const BUILTIN_TYPES: readonly BuiltinType[] = ['email', 'webhook', 'feishu']
/** Builtins are configured through their own endpoints, even when they also support `user_login`. */
const isBuiltinType = (providerType: Integration['provider_type']): providerType is BuiltinType => (BUILTIN_TYPES as readonly string[]).includes(providerType)

export default function SiteSettingsIntegrationsPage() {
  const t = useTranslations('siteSettings')
  const tLogin = useTranslations('sso')
  const { canPerform } = useCanPerform()
  const router = useRouter()
  const canReadLogin = canPerform('admin:integrations:login:read')
  const canReadSettings = canPerform('admin:integrations:settings:read')
  const canUpdateLogin = canPerform('admin:integrations:login:update')
  const canUpdateSettings = canPerform('admin:integrations:settings:update')
  const [instances, setInstances] = React.useState<Integration[]>([])
  const [types, setTypes] = React.useState<IntegrationType[]>([])
  const [loading, setLoading] = React.useState(true)
  const [editIntegration, setEditIntegration] = React.useState<Integration | null>(null)
  const [showLoginDialog, setShowLoginDialog] = React.useState(false)
  const [deleteIntegration, setDeleteIntegration] = React.useState<Integration | null>(null)
  const [emailSettings, setEmailSettings] = React.useState<EmailSettings | null>(null)
  const [webhookSettings, setWebhookSettings] = React.useState<WebhookSettings | null>(null)
  const [feishuConfig, setFeishuConfig] = React.useState<FeishuConfig | null>(null)

  const load = React.useCallback(async () => {
    setLoading(true)
    try {
      const [data, catalog, email, webhook, feishu] = await Promise.all([
        integrationsApi.list(), integrationsApi.types(),
        canReadSettings ? integrationsApi.getEmail() : null,
        canReadSettings ? integrationsApi.getWebhook() : null,
        canReadSettings ? integrationsApi.getFeishuConfig() : null,
      ])
      setInstances(data)
      setTypes(catalog.filter((type) => !type.singleton && type.supported_capabilities.includes('user_login')))
      setEmailSettings(email)
      setWebhookSettings(webhook)
      setFeishuConfig(feishu)
    } catch {
      // API interceptor handles backend errors.
    } finally {
      setLoading(false)
    }
  }, [canReadSettings])

  React.useEffect(() => { load() }, [load])

  const toggle = async (integration: Integration, checked: boolean) => {
    const builtin = isBuiltinType(integration.provider_type)
    if (builtin ? !canUpdateSettings : !canUpdateLogin) return
    try {
      if (integration.provider_type === 'email') {
        setEmailSettings(await integrationsApi.updateEmail({ smtp_enabled: checked }))
      } else if (integration.provider_type === 'webhook') {
        setWebhookSettings(await integrationsApi.updateWebhook({ webhook_enabled: checked }))
      } else if (integration.provider_type === 'feishu') {
        setFeishuConfig(await integrationsApi.updateFeishuConfig({ is_enabled: checked }))
      } else {
        await integrationsApi.update(integration.id, { is_enabled: checked })
      }
      setInstances((current) => current.map((item) => {
        if (item.id !== integration.id) return item
        // The builtin switch grants its non-login capabilities and preserves the
        // login opt-in, which is configured separately — same as the backend.
        const enabledCapabilities = builtin
          ? item.supported_capabilities.filter((capability) => capability === 'user_login'
            ? item.enabled_capabilities.includes('user_login')
            : checked)
          : item.enabled_capabilities
        return { ...item, is_enabled: checked, enabled_capabilities: enabledCapabilities }
      }))
    } catch {
      // API interceptor handles backend errors.
    }
  }

  const testConnection = async (integration: Integration) => {
    if (!canUpdateLogin) return
    try {
      const result = await integrationsApi.testConnection(integration.id)
      if (result.status === 'success') toast.success(result.message)
      else toast.error(result.message)
    } catch {
      // API interceptor handles backend errors.
    }
  }

  const remove = async () => {
    if (!deleteIntegration || !canUpdateLogin) return
    try {
      await integrationsApi.delete(deleteIntegration.id)
      setInstances((current) => current.filter((item) => item.id !== deleteIntegration.id))
      toast.success(tLogin('deleteSuccess'))
      setDeleteIntegration(null)
    } catch {
      // API interceptor handles backend errors.
    }
  }

  if (loading) return <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">{[1, 2, 3].map((index) => <Card key={index}><CardHeader><Skeleton className="h-6 w-32" /></CardHeader><CardContent><Skeleton className="h-9 w-28" /></CardContent></Card>)}</div>

  const visibleInstances = instances.filter((integration) => isBuiltinType(integration.provider_type) ? canReadSettings : canReadLogin)

  return (
    <div className="space-y-6">
      {canReadLogin && <div className="flex justify-end"><Button disabled={!canUpdateLogin || types.length === 0} onClick={() => { setEditIntegration(null); setShowLoginDialog(true) }}><Plus className="mr-2 h-4 w-4" />{tLogin('addProvider')}</Button></div>}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4">
        {visibleInstances.map((integration) => {
          const builtin = isBuiltinType(integration.provider_type) ? integration.provider_type : null
          const editable = builtin ? canUpdateSettings : canUpdateLogin
          const enabled = builtin === 'email' ? emailSettings?.smtp_enabled : builtin === 'webhook' ? webhookSettings?.webhook_enabled : builtin === 'feishu' ? feishuConfig?.is_enabled : integration.is_enabled
          const open = () => {
            if (builtin) router.push(`/site-settings/integrations/${builtin}`)
            else { setEditIntegration(integration); setShowLoginDialog(true) }
          }
          return <Card key={integration.id} size="sm" className="!gap-0 !py-0" data-integration-id={integration.id}>
            <div className="flex items-center gap-3 px-3 py-3">
              <button type="button" className="flex min-w-0 flex-1 items-center gap-3 text-left" aria-label={builtin ? t(`integrations.${builtin}`) : integration.display_name} onClick={open}>
                {integration.icon_url ? <img src={integration.icon_url} alt="" className="h-7 w-7 object-contain" /> : builtin === 'email' ? <Mail className="h-7 w-7 shrink-0 text-muted-foreground" /> : builtin === 'webhook' ? <Globe className="h-7 w-7 shrink-0 text-muted-foreground" /> : builtin === 'feishu' ? <img src="/integrations/feishu.png" alt="" className="h-7 w-7 object-contain" /> : <Shield className="h-7 w-7 shrink-0 text-muted-foreground" />}
                <div className="min-w-0"><CardTitle>{builtin ? t(`integrations.${builtin}`) : integration.display_name}</CardTitle><CardDescription className="text-xs">{builtin ? builtin === 'email' ? t('email.basicSettingsDesc') : builtin === 'webhook' ? t('webhook.basicSettingsDesc') : t('integrations.feishuDescription') : integration.provider_type.toUpperCase()}</CardDescription></div>
              </button>
              <Button type="button" variant="ghost" size="icon-sm" aria-label={t('integrations.configure')} onClick={open}><Settings2 className="h-4 w-4" /></Button>
              <Switch aria-label={builtin ? builtin === 'email' ? t('email.smtpEnabled') : builtin === 'webhook' ? t('webhook.enabled') : t('integrations.feishu') : `${integration.display_name}: ${tLogin('enabled')}`} checked={Boolean(enabled)} disabled={!editable} onCheckedChange={(checked) => toggle(integration, checked)} />
            </div>
            <div className="flex flex-wrap items-center gap-2 px-3 pb-3">{integration.supported_capabilities.map((capability) => <Badge key={capability} variant={integration.is_enabled && integration.enabled_capabilities.includes(capability) ? 'secondary' : 'outline'}>{t(`integrations.capabilities.${capability}`)}: {integration.is_enabled && integration.enabled_capabilities.includes(capability) ? t('integrations.enabled') : t('integrations.disabled')}</Badge>)}{!builtin && <><Button variant="outline" size="sm" disabled={!editable} onClick={() => testConnection(integration)}>{tLogin('testConnection')}</Button><Button variant="ghost" size="icon-sm" aria-label={`${tLogin('deleteProvider')}: ${integration.display_name}`} disabled={!editable} onClick={() => setDeleteIntegration(integration)}><Trash2 className="h-4 w-4" /></Button></>}</div>
          </Card>
        })}
      </div>
      {canReadLogin && <LoginIntegrationDialog open={showLoginDialog} provider={editIntegration} types={types} onClose={(success) => { setShowLoginDialog(false); setEditIntegration(null); if (success) load() }} />}
      <AlertDialog open={deleteIntegration !== null} onOpenChange={(open) => { if (!open) setDeleteIntegration(null) }}><AlertDialogContent><AlertDialogHeader><AlertDialogTitle>{tLogin('deleteProvider')}</AlertDialogTitle><AlertDialogDescription>{tLogin('deleteConfirm')}</AlertDialogDescription></AlertDialogHeader><AlertDialogFooter><AlertDialogCancel>{tLogin('cancel')}</AlertDialogCancel><AlertDialogAction disabled={!canUpdateLogin} onClick={remove}>{tLogin('delete')}</AlertDialogAction></AlertDialogFooter></AlertDialogContent></AlertDialog>
    </div>
  )
}
