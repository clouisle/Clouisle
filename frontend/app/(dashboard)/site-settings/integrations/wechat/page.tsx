'use client'

import * as React from 'react'
import Link from 'next/link'
import { ArrowLeft, Loader2, Save } from 'lucide-react'
import { useTranslations } from 'next-intl'
import { toast } from 'sonner'
import { useCanPerform } from '@/components/permission-guard'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Switch } from '@/components/ui/switch'
import { integrationsApi, type Integration } from '@/lib/api/admin/integrations'

const features = ['agent_chat', 'knowledge_collection'] as const

export default function WeChatIntegrationPage() {
  const t = useTranslations('siteSettings')
  const tCommon = useTranslations('common')
  const { canPerform } = useCanPerform()
  const canUpdate = canPerform('admin:integrations:settings:update')
  const [integration, setIntegration] = React.useState<Integration | null>(null)
  const [selected, setSelected] = React.useState<string[]>([])
  const [loading, setLoading] = React.useState(true)
  const [saving, setSaving] = React.useState(false)

  React.useEffect(() => {
    let active = true
    void integrationsApi.list().then(instances => {
      if (!active) return
      const instance = instances.find(item => item.provider_type === 'wechat') ?? null
      setIntegration(instance)
      setSelected(instance?.is_enabled ? instance.enabled_capabilities : [])
    }).catch(() => {
      // API interceptor handles backend errors.
    }).finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [])

  const saved = integration?.is_enabled ? integration.enabled_capabilities : []
  const changed = features.some(feature => selected.includes(feature) !== saved.includes(feature))
  const save = async () => {
    if (!integration || !canUpdate || saving || !changed) return
    setSaving(true)
    try {
      const updated = await integrationsApi.update(integration.id, {
        enabled_capabilities: features.filter(feature => selected.includes(feature)),
      })
      setIntegration(updated)
      setSelected(updated.enabled_capabilities)
      toast.success(t('saveSuccess'))
    } catch {
      // API interceptor handles backend errors.
    } finally {
      setSaving(false)
    }
  }

  return <div className="space-y-6">
    <div className="flex items-center gap-3">
      <Link href="/site-settings/integrations" aria-label={t('integrations.back')} className="inline-flex size-9 shrink-0 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground">
        <ArrowLeft className="size-4" aria-hidden="true" />
      </Link>
      <div><h1 className="text-2xl font-semibold">{t('integrations.wechat')}</h1><p className="mt-1 text-sm text-muted-foreground">{t('integrations.wechatDescription')}</p></div>
    </div>
    {loading ? <p className="text-muted-foreground">{tCommon('loading')}</p> : !integration ? <p role="alert" className="text-muted-foreground">{t('integrations.wechatUnavailable')}</p> : <Card><CardContent className="space-y-5 pt-6">
      <p className="text-sm text-muted-foreground">{t('integrations.wechatFeaturesHint')}</p>
      {features.map(feature => <div key={feature} className="flex items-start justify-between gap-4">
        <div><h2 className="text-sm font-medium">{t(`integrations.capabilities.${feature}`)}</h2><p className="text-xs text-muted-foreground">{t(`integrations.wechatFeatureDescriptions.${feature}`)}</p></div>
        <Switch aria-label={t(`integrations.capabilities.${feature}`)} checked={selected.includes(feature)} disabled={!canUpdate || saving} onCheckedChange={checked => {
          if (!canUpdate || saving) return
          setSelected(current => checked ? [...current, feature] : current.filter(item => item !== feature))
        }} />
      </div>)}
      <p className="rounded-md border p-3 text-sm text-muted-foreground">{t('integrations.wechatRuntimeHint')}</p>
      {canUpdate && <div className="flex justify-end"><Button onClick={() => void save()} disabled={!changed || saving}>{saving ? <Loader2 className="mr-2 size-4 animate-spin" /> : <Save className="mr-2 size-4" />}{t('save')}</Button></div>}
    </CardContent></Card>}
  </div>
}
