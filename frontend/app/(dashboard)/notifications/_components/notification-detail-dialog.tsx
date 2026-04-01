'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { Mail, MessageSquare, CheckCircle2, XCircle, Loader2, Clock } from 'lucide-react'
import { Streamdown } from 'streamdown'
import type { NotificationItem } from '@/lib/api/admin/notifications'
import type { NotificationDelivery } from '@/lib/api/notifications'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Badge } from '@/components/ui/badge'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { formatDateTime } from '@/lib/utils'

interface NotificationDetailDialogProps {
  notification: NotificationItem | null
  open: boolean
  onOpenChange: (open: boolean) => void
}

function DeliveryStatusIcon({ delivery }: { delivery: NotificationDelivery }) {
  const t = useTranslations('notifications')

  const channelIcon = delivery.channel === 'email' ? (
    <Mail className="h-3.5 w-3.5" />
  ) : delivery.channel === 'dingtalk' ? (
    <MessageSquare className="h-3.5 w-3.5" />
  ) : null

  const statusIcon = delivery.status === 'success' ? (
    <CheckCircle2 className="h-3 w-3 text-green-500" />
  ) : delivery.status === 'failed' ? (
    <XCircle className="h-3 w-3 text-destructive" />
  ) : delivery.status === 'sending' ? (
    <Loader2 className="h-3 w-3 text-blue-500 animate-spin" />
  ) : (
    <Clock className="h-3 w-3 text-muted-foreground" />
  )

  const tooltipContent = delivery.error_message
    ? `${t(`deliveryStatus.${delivery.status}`)}: ${delivery.error_message}`
    : t(`deliveryStatus.${delivery.status}`)

  return (
    <Tooltip>
      <TooltipTrigger>
        <div className="inline-flex items-center gap-0.5 cursor-default">
          {channelIcon}
          {statusIcon}
        </div>
      </TooltipTrigger>
      <TooltipContent>
        <p>{t(`channel.${delivery.channel}`)}: {tooltipContent}</p>
        {delivery.retry_count > 0 && (
          <p className="text-xs text-muted-foreground">
            {t('retryCount', { count: delivery.retry_count })}
          </p>
        )}
      </TooltipContent>
    </Tooltip>
  )
}

export function NotificationDetailDialog({
  notification,
  open,
  onOpenChange,
}: NotificationDetailDialogProps) {
  const t = useTranslations('notifications')

  if (!notification) return null

  // 处理类型显示 - 将点号替换为下划线以匹配翻译键
  const getTypeLabel = (type: string) => {
    const typeKey = type.replace(/\./g, '_')
    const translated = t(`admin.typeOptions.${typeKey}`, { defaultValue: '' })
    return translated || type
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{t('admin.viewDetail')}</DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          {/* Title */}
          <div>
            <div className="text-sm font-medium text-muted-foreground mb-1">
              {t('admin.createTitle')}
            </div>
            <div className="text-base font-semibold">{notification.title}</div>
          </div>

          {/* Content */}
          <div>
            <div className="text-sm font-medium text-muted-foreground mb-1">
              {t('admin.createContent')}
            </div>
            <div className="text-sm bg-muted/50 rounded-md p-3 prose prose-sm dark:prose-invert max-w-none [&>*:first-child]:mt-0 [&>*:last-child]:mb-0">
              <Streamdown>{notification.content}</Streamdown>
            </div>
          </div>

          {/* Metadata */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <div className="text-sm font-medium text-muted-foreground mb-1">
                {t('scope')}
              </div>
              <Badge variant="secondary">{t(`scopeOptions.${notification.scope}`)}</Badge>
            </div>

            <div>
              <div className="text-sm font-medium text-muted-foreground mb-1">
                {t('level')}
              </div>
              <Badge variant="outline">{t(`levelOptions.${notification.level}`)}</Badge>
            </div>

            <div>
              <div className="text-sm font-medium text-muted-foreground mb-1">
                {t('type')}
              </div>
              <div className="text-sm">
                {getTypeLabel(notification.type)}
              </div>
            </div>

            <div>
              <div className="text-sm font-medium text-muted-foreground mb-1">
                {t('createdAt')}
              </div>
              <div className="text-sm">{formatDateTime(notification.created_at)}</div>
            </div>
          </div>

          {/* Link URL */}
          {notification.link_url && (
            <div>
              <div className="text-sm font-medium text-muted-foreground mb-1">
                {t('admin.createLink')}
              </div>
              <a
                href={notification.link_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-sm text-primary hover:underline break-all"
              >
                {notification.link_url}
              </a>
            </div>
          )}

          {/* Expires At */}
          {notification.expires_at && (
            <div>
              <div className="text-sm font-medium text-muted-foreground mb-1">
                {t('admin.createExpiresAt')}
              </div>
              <div className="text-sm">{formatDateTime(notification.expires_at)}</div>
            </div>
          )}

          {/* Delivery Status */}
          {notification.deliveries && notification.deliveries.length > 0 && (
            <div>
              <div className="text-sm font-medium text-muted-foreground mb-2">
                {t('deliveryStatus.title')}
              </div>
              <div className="space-y-2">
                {notification.deliveries.map((delivery, idx) => (
                  <div
                    key={idx}
                    className="flex items-center justify-between p-2 rounded-md bg-muted/30"
                  >
                    <div className="flex items-center gap-2">
                      <DeliveryStatusIcon delivery={delivery} />
                      <span className="text-sm">{t(`channel.${delivery.channel}`)}</span>
                    </div>
                    <div className="text-sm text-muted-foreground">
                      {t(`deliveryStatus.${delivery.status}`)}
                      {delivery.sent_at && ` • ${formatDateTime(delivery.sent_at)}`}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}
