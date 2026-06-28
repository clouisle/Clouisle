'use client'

import * as React from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { Megaphone, ShieldAlert, Sparkles } from 'lucide-react'
import { notificationsApi, type NotificationItem } from '@/lib/api'
import { getNotificationDisplayMeta, type NotificationDisplayKind } from '@/lib/notifications/display'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

const KIND_ICON: Record<NotificationDisplayKind, React.ComponentType<{ className?: string }>> = {
  announcement: Megaphone,
  security: ShieldAlert,
  action: Sparkles,
  delivery: Sparkles,
  general: Sparkles,
}

export function ProminentNotificationDialog() {
  const t = useTranslations('notifications')
  const pathname = usePathname()
  const dismissedIds = React.useRef(new Set<string>())
  const [items, setItems] = React.useState<NotificationItem[]>([])
  const [selectedItem, setSelectedItem] = React.useState<NotificationItem | null>(null)

  const selectNext = React.useCallback((nextItems: NotificationItem[]) => {
    setSelectedItem(nextItems.find((item) => !dismissedIds.current.has(item.id)) ?? null)
  }, [])

  const fetchProminentNotifications = React.useCallback(async () => {
    try {
      const response = await notificationsApi.list({ page: 1, page_size: 10, unread_only: true })
      const prominentItems = response.items.filter((item) => getNotificationDisplayMeta(item).isProminent).slice(0, 3)
      setItems(prominentItems)
      selectNext(prominentItems)
    } catch (error) {
      console.error('Failed to fetch prominent notifications:', error)
      setItems([])
      setSelectedItem(null)
    }
  }, [selectNext])

  React.useEffect(() => {
    fetchProminentNotifications()
  }, [fetchProminentNotifications, pathname])

  const closeDialog = () => {
    if (selectedItem) {
      dismissedIds.current.add(selectedItem.id)
    }
    setSelectedItem(null)
  }

  const handleMarkRead = async () => {
    if (!selectedItem) return

    try {
      await notificationsApi.markRead({ notification_ids: [selectedItem.id] })
      const nextItems = items.filter((item) => item.id !== selectedItem.id)
      setItems(nextItems)
      selectNext(nextItems)
    } catch (error) {
      console.error('Failed to mark notification read:', error)
    }
  }

  if (!selectedItem) {
    return null
  }

  const meta = getNotificationDisplayMeta(selectedItem)
  const Icon = KIND_ICON[meta.kind]
  const href = selectedItem.link_url || '/app/notifications'

  return (
    <Dialog open={Boolean(selectedItem)} onOpenChange={(open) => !open && closeDialog()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <div className="mb-2 flex items-center gap-2">
            <Badge variant={meta.priorityScore >= 5 ? 'default' : 'secondary'} className="gap-1">
              <Icon className="size-3" />
              {t(`kindOptions.${meta.kind}`)}
            </Badge>
          </div>
          <DialogTitle>{t('prominentTitle')}</DialogTitle>
          <DialogDescription>{t('prominentDescription')}</DialogDescription>
        </DialogHeader>

        <div className="space-y-2">
          <p className="font-medium">{selectedItem.title}</p>
          <p className="whitespace-pre-wrap text-sm leading-6 text-foreground/90">{selectedItem.content}</p>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={handleMarkRead}>
            {t('markRead')}
          </Button>
          <Link href={href} onClick={closeDialog}>
            <Button>{t('viewNotification')}</Button>
          </Link>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
