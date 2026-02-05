'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { toast } from 'sonner'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'
import { Loader2 } from 'lucide-react'
import { siteSettingsApi, type AutoNotificationConfig } from '@/lib/api'

// All notification types grouped by category
const NOTIFICATION_CATEGORIES = {
  team: ['team.member_added', 'team.member_removed', 'team.role_changed', 'team.ownership_transferred', 'team.model_granted', 'team.model_revoked'],
  user: ['user.activated', 'user.deactivated', 'user.password_reset', 'user.pending_approval'],
  kb: ['kb.doc_indexed', 'kb.doc_failed'],
  workflow: ['workflow.run_success', 'workflow.run_failed'],
  agent: ['agent.published', 'agent.unpublished'],
  apikey: ['apikey.expiring', 'apikey.expired'],
  security: ['security.login_anomaly', 'security.account_locked', 'security.password_changed'],
} as const

// Available channels
const CHANNELS = ['email', 'dingtalk', 'wechat', 'feishu', 'webhook', 'slack'] as const

interface EnabledChannels {
  email: boolean
  dingtalk: boolean
  wechat: boolean
  feishu: boolean
  webhook: boolean
  slack: boolean
}

interface AutoNotificationsSettingsTabProps {
  enabledChannels: EnabledChannels
}

export function AutoNotificationsSettingsTab({ enabledChannels }: AutoNotificationsSettingsTabProps) {
  const t = useTranslations('siteSettings')
  const [loading, setLoading] = React.useState(true)
  const [saving, setSaving] = React.useState(false)
  const [config, setConfig] = React.useState<AutoNotificationConfig>({
    channels: [],
    enabled_types: [],
  })

  const loadConfig = React.useCallback(async () => {
    try {
      setLoading(true)
      const data = await siteSettingsApi.getAutoNotifications()
      setConfig(data)
    } catch (error) {
      console.error('Failed to load auto notification config:', error)
    } finally {
      setLoading(false)
    }
  }, [])

  React.useEffect(() => {
    loadConfig()
  }, [loadConfig])

  const toggleType = (type: string) => {
    setConfig((prev) => ({
      ...prev,
      enabled_types: prev.enabled_types.includes(type)
        ? prev.enabled_types.filter((t) => t !== type)
        : [...prev.enabled_types, type],
    }))
  }

  const toggleChannel = (channel: string) => {
    setConfig((prev) => ({
      ...prev,
      channels: prev.channels.includes(channel)
        ? prev.channels.filter((c) => c !== channel)
        : [...prev.channels, channel],
    }))
  }

  const handleSave = async () => {
    try {
      setSaving(true)
      await siteSettingsApi.updateAutoNotifications(config)
      toast.success(t('saveSuccess'))
    } catch (error) {
      console.error('Failed to save auto notification config:', error)
    } finally {
      setSaving(false)
    }
  }

  // Get available channels (only show enabled ones)
  const availableChannels = CHANNELS.filter((channel) => enabledChannels[channel])

  if (loading) {
    return (
      <div className="flex items-center justify-center py-8">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Global Channels Configuration */}
      <Card>
        <CardHeader>
          <CardTitle>{t('autoNotifications.title')}</CardTitle>
          <CardDescription>{t('autoNotifications.description')}</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            <div>
              <Label className="text-sm font-medium">{t('autoNotifications.globalChannels')}</Label>
              <p className="text-xs text-muted-foreground mb-3">
                {t('autoNotifications.globalChannelsDesc')}
              </p>
              {availableChannels.length > 0 ? (
                <div className="flex flex-wrap gap-4">
                  {availableChannels.map((channel) => (
                    <div key={channel} className="flex items-center gap-2">
                      <Checkbox
                        id={`global-${channel}`}
                        checked={config.channels.includes(channel)}
                        onCheckedChange={() => toggleChannel(channel)}
                      />
                      <Label htmlFor={`global-${channel}`} className="text-sm cursor-pointer">
                        {t(`notifications.${channel}`)}
                      </Label>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">
                  {t('autoNotifications.noChannelsConfigured')}
                </p>
              )}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Notification Types by Category */}
      {Object.entries(NOTIFICATION_CATEGORIES).map(([categoryKey, types]) => (
        <Card key={categoryKey}>
          <CardHeader>
            <CardTitle>{t(`autoNotifications.categories.${categoryKey}`)}</CardTitle>
            <CardDescription>{t(`autoNotifications.categories.${categoryKey}Desc`)}</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {types.map((type) => (
                <div key={type} className="flex items-center justify-between py-2">
                  <div className="space-y-0.5">
                    <Label className="text-sm font-medium">
                      {t(`autoNotifications.types.${type.replace('.', '_')}`)}
                    </Label>
                    <p className="text-xs text-muted-foreground">
                      {t(`autoNotifications.types.${type.replace('.', '_')}Desc`)}
                    </p>
                  </div>
                  <Switch
                    checked={config.enabled_types.includes(type)}
                    onCheckedChange={() => toggleType(type)}
                  />
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      ))}

      {/* Save button */}
      <div className="flex justify-end">
        <Button onClick={handleSave} disabled={saving}>
          {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
          {t('save')}
        </Button>
      </div>
    </div>
  )
}
