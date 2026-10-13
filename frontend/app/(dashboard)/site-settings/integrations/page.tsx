'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Globe, Mail, Settings2 } from 'lucide-react'
import { siteSettingsApi } from '@/lib/api/admin/site-settings'
import type { EmailSettings, WebhookSettings } from '@/lib/api/site-settings'
import { EmailSettingsTab, FeishuIntegrationTab, WebhookSettingsTab } from './_components'
import { useCanPerform } from '@/components/permission-guard'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'

type IntegrationId = 'email' | 'webhook' | 'feishu'


export default function SiteSettingsIntegrationsPage() {
  const t = useTranslations('siteSettings')
  const { canPerform } = useCanPerform()
  const canUpdate = canPerform('admin:settings:update')
  const [activeIntegration, setActiveIntegration] = React.useState<IntegrationId | null>(null)
  const [loading, setLoading] = React.useState(true)
  const [feishuConfig, setFeishuConfig] = React.useState({ app_id: '', app_secret_configured: false, department_ids: [] as string[] })
  const [emailSettings, setEmailSettings] = React.useState<EmailSettings>({
    smtp_enabled: false,
    smtp_host: '',
    smtp_port: 587,
    smtp_encryption: 'tls',
    smtp_username: '',
    smtp_password: '',
    email_from_name: 'Clouisle',
    email_from_address: '',
  })
  const [webhookSettings, setWebhookSettings] = React.useState<WebhookSettings>({
    webhook_enabled: false,
    webhook_url: '',
    webhook_method: 'POST',
    webhook_headers: {},
    webhook_body_template: '{"title": "{{title}}", "content": "{{content}}", "link_url": "{{link_url}}"}',
    webhook_secret: '',
  })

  const loadSettings = React.useCallback(async () => {
    try {
      setLoading(true)
      const [emailData, webhookData, feishuData] = await Promise.all([
        siteSettingsApi.getEmail(),
        siteSettingsApi.getWebhook(),
        siteSettingsApi.getFeishuConfig(),
      ])
      setEmailSettings(emailData)
      setWebhookSettings(webhookData)
      setFeishuConfig(feishuData)
    } catch (error) {
      console.error('Failed to load integration settings:', error)
    } finally {
      setLoading(false)
    }
  }, [])

  React.useEffect(() => {
    loadSettings()
  }, [loadSettings])
  const handleEmailToggle = async (checked: boolean) => {
    try {
      await siteSettingsApi.updateEmail({ smtp_enabled: checked })
      setEmailSettings((current) => ({ ...current, smtp_enabled: checked }))
    } catch (error) {
      console.error('Failed to update email integration:', error)
    }
  }

  const handleWebhookToggle = async (checked: boolean) => {
    try {
      await siteSettingsApi.updateWebhook({ webhook_enabled: checked })
      setWebhookSettings((current) => ({ ...current, webhook_enabled: checked }))
    } catch (error) {
      console.error('Failed to update webhook integration:', error)
    }
  }
  const handleFeishuToggle = () => setActiveIntegration('feishu')

  if (loading) {
    return (
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {[1, 2, 3].map((index) => <Card key={index}><CardHeader><Skeleton className="h-6 w-32" /><Skeleton className="h-4 w-48" /></CardHeader><CardContent><Skeleton className="h-9 w-28" /></CardContent></Card>)}
      </div>
    )
  }

  return (
    <>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4">
        <Card size="sm" className="group relative cursor-pointer !gap-0 !py-0" role="button" tabIndex={0} onClick={() => setActiveIntegration('email')} onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); setActiveIntegration('email') } }}><div className="grid grid-cols-[2.75rem_minmax(0,1fr)_auto] items-center gap-2 px-3 py-3"><div className="flex items-center justify-center"><Mail className="h-7 w-7 text-muted-foreground" /></div><div className="min-w-0"><CardTitle>{t('integrations.email')}</CardTitle><CardDescription className="text-xs">{t('email.basicSettingsDesc')}</CardDescription></div><div className="flex h-full items-center justify-end gap-1"><Button type="button" variant="ghost" size="icon-sm" aria-label={t('integrations.configure')} className="opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100" onClick={(event) => { event.stopPropagation(); setActiveIntegration('email') }}><Settings2 className="h-5 w-5" /></Button><Switch checked={emailSettings.smtp_enabled} disabled={!canUpdate} aria-label={t('email.smtpEnabled')} onClick={(event) => event.stopPropagation()} onCheckedChange={handleEmailToggle} /></div></div></Card>
        <Card size="sm" className="group relative cursor-pointer !gap-0 !py-0" role="button" tabIndex={0} onClick={() => setActiveIntegration('webhook')} onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); setActiveIntegration('webhook') } }}><div className="grid grid-cols-[2.75rem_minmax(0,1fr)_auto] items-center gap-2 px-3 py-3"><div className="flex items-center justify-center"><Globe className="h-7 w-7 text-muted-foreground" /></div><div className="min-w-0"><CardTitle>{t('integrations.webhook')}</CardTitle><CardDescription className="text-xs">{t('webhook.basicSettingsDesc')}</CardDescription></div><div className="flex h-full items-center justify-end gap-1"><Button type="button" variant="ghost" size="icon-sm" aria-label={t('integrations.configure')} className="opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100" onClick={(event) => { event.stopPropagation(); setActiveIntegration('webhook') }}><Settings2 className="h-4 w-4" /></Button><Switch checked={webhookSettings.webhook_enabled} disabled={!canUpdate} aria-label={t('webhook.enabled')} onClick={(event) => event.stopPropagation()} onCheckedChange={handleWebhookToggle} /></div></div></Card>
        <Card size="sm" className="group relative cursor-pointer !gap-0 !py-0" role="button" tabIndex={0} onClick={() => setActiveIntegration('feishu')} onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); setActiveIntegration('feishu') } }}><div className="grid grid-cols-[2.75rem_minmax(0,1fr)_auto] items-center gap-2 px-3 py-3"><div className="flex items-center justify-center"><img src="/integrations/feishu.png" alt="" className="h-7 w-7 object-contain" /></div><div className="min-w-0"><CardTitle>{t('integrations.feishu')}</CardTitle><CardDescription className="text-xs">{t('integrations.feishuDescription')}</CardDescription></div><div className="flex h-full items-center justify-end gap-1"><Button type="button" variant="ghost" size="icon-sm" aria-label={t('integrations.configure')} className="opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100" onClick={(event) => { event.stopPropagation(); setActiveIntegration('feishu') }}><Settings2 className="h-4 w-4" /></Button><Switch checked={feishuConfig.app_secret_configured} disabled={!canUpdate} aria-label={t('integrations.feishu')} onClick={(event) => event.stopPropagation()} onCheckedChange={handleFeishuToggle} /></div></div></Card>
      </div>
      <Dialog open={activeIntegration !== null} onOpenChange={(open) => { if (!open) setActiveIntegration(null) }}>
        <DialogContent className="!w-[64vw] !max-w-[64vw] max-h-[85vh] overflow-y-auto"><DialogHeader><DialogTitle>{activeIntegration ? t(`integrations.${activeIntegration}`) : ''}</DialogTitle><DialogDescription>{activeIntegration === 'feishu' ? t('integrations.feishuDescription') : activeIntegration === 'email' ? t('email.basicSettingsDesc') : t('webhook.basicSettingsDesc')}</DialogDescription></DialogHeader>
          {activeIntegration === 'email' && <EmailSettingsTab settings={emailSettings} onSettingsChange={setEmailSettings} canUpdate={canUpdate} />}
          {activeIntegration === 'webhook' && <WebhookSettingsTab settings={webhookSettings} onSettingsChange={setWebhookSettings} canUpdate={canUpdate} />}
          {activeIntegration === 'feishu' && <FeishuIntegrationTab config={feishuConfig} onConfigChange={setFeishuConfig} canUpdate={canUpdate} />}
        </DialogContent>
      </Dialog>
    </>
  )
}
