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
import { FieldError } from '@/components/ui/field'
import { siteSettingsApi, type AutoNotificationConfig } from '@/lib/api/admin/site-settings'
import {
  clearValidationErrorsByPrefix,
  getValidationSummaryEntries,
  mapValidationErrors,
  normalizeValidationErrors,
  formatValidationSummaryMessage
} from '@/lib/validation'

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
  canUpdate: boolean
}

export function AutoNotificationsSettingsTab({ enabledChannels, canUpdate }: AutoNotificationsSettingsTabProps) {
  const t = useTranslations('siteSettings')

  const getNotificationChannelLabel = (channel: string) => {
    const key = `notifications.${channel}`
    return t.has(key) ? t(key) : channel
  }

  const getNotificationCategoryLabel = (categoryKey: string) => {
    const key = `autoNotifications.categories.${categoryKey}`
    return t.has(key) ? t(key) : categoryKey
  }

  const getNotificationCategoryDescription = (categoryKey: string) => {
    const key = `autoNotifications.categories.${categoryKey}Desc`
    return t.has(key) ? t(key) : categoryKey
  }

  const getNotificationTypeLabel = (type: string) => {
    const normalizedType = type.replace('.', '_')
    const key = `autoNotifications.types.${normalizedType}`
    return t.has(key) ? t(key) : type
  }

  const getNotificationTypeDescription = (type: string) => {
    const normalizedType = type.replace('.', '_')
    const key = `autoNotifications.types.${normalizedType}Desc`
    return t.has(key) ? t(key) : type
  }

  const [loading, setLoading] = React.useState(true)
  const [saving, setSaving] = React.useState(false)
  const [fieldErrors, setFieldErrors] = React.useState<Record<string, string>>({})
  const [config, setConfig] = React.useState<AutoNotificationConfig>({
    channels: [],
    enabled_types: [],
  })

  const summaryEntries = React.useMemo(
    () => getValidationSummaryEntries(fieldErrors, ['channels', 'enabled_types']),
    [fieldErrors]
  )

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
    setFieldErrors((prev) => clearValidationErrorsByPrefix(prev, 'enabled_types'))
    setConfig((prev) => ({
      ...prev,
      enabled_types: prev.enabled_types.includes(type)
        ? prev.enabled_types.filter((t) => t !== type)
        : [...prev.enabled_types, type],
    }))
  }

  const toggleChannel = (channel: string) => {
    setFieldErrors((prev) => clearValidationErrorsByPrefix(prev, 'channels'))
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
      const errors = mapValidationErrors(normalizeValidationErrors(error), {
        channels: 'channels',
        enabled_types: 'enabled_types',
      })
      if (Object.keys(errors).length > 0) {
        setFieldErrors(errors)
      }
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
      {summaryEntries.length > 0 && (
        <div className="rounded-md border border-destructive/30 bg-destructive/5 p-3 space-y-1">
          {summaryEntries.map(([field, message]) => (
            <FieldError key={field}>{formatValidationSummaryMessage(field, message)}</FieldError>
          ))}
        </div>
      )}
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
                        disabled={!canUpdate}
                      />
                      <Label htmlFor={`global-${channel}`} className="text-sm cursor-pointer">
                        {getNotificationChannelLabel(channel)}
                      </Label>
                    </div>
                  ))}
                </div>
              ) : (

                <p className="text-sm text-muted-foreground">
                  {t('autoNotifications.noChannelsConfigured')}
                </p>
              )}
              <FieldError>{fieldErrors.channels}</FieldError>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Notification Types by Category */}
      {Object.entries(NOTIFICATION_CATEGORIES).map(([categoryKey, types]) => (
        <Card key={categoryKey}>
          <CardHeader>
            <CardTitle>{getNotificationCategoryLabel(categoryKey)}</CardTitle>
            <CardDescription>{getNotificationCategoryDescription(categoryKey)}</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              <FieldError>{fieldErrors.enabled_types}</FieldError>
              {types.map((type) => (
                <div key={type} className="flex items-center justify-between py-2">
                  <div className="space-y-0.5">
                    <Label className="text-sm font-medium">
                      {getNotificationTypeLabel(type)}
                    </Label>
                    <p className="text-xs text-muted-foreground">
                      {getNotificationTypeDescription(type)}
                    </p>
                  </div>
                  <Switch
                    checked={config.enabled_types.includes(type)}
                    onCheckedChange={() => toggleType(type)}
                    disabled={!canUpdate}
                  />
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      ))}

      {/* Save button */}
      {canUpdate && (
        <div className="flex justify-end">
          <Button onClick={handleSave} disabled={saving}>
            {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {t('save')}
          </Button>
        </div>
      )}
    </div>
  )
}
