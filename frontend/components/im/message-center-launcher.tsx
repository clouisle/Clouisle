'use client'

import * as React from 'react'
import { Bell } from 'lucide-react'
import { useTranslations } from 'next-intl'
import { authApi, imApi, type User } from '@/lib/api'
import { useTeam } from '@/contexts/team-context'
import { Button } from '@/components/ui/button'
import { MessageCenterDialog } from './message-center-dialog'

/**
 * Floating message-center entry for layouts without `PlatformHeader`
 * (the workflow editor). Keeps the same unread + SSE behavior as the header.
 */
export function MessageCenterLauncher() {
  const t = useTranslations('notifications')
  const { currentTeam } = useTeam()
  const [user, setUser] = React.useState<User | null>(null)
  const [open, setOpen] = React.useState(false)
  const [unread, setUnread] = React.useState(0)

  React.useEffect(() => {
    authApi
      .getCurrentUser({ skipAuthRedirect: true })
      .then(setUser)
      .catch(() => {})
  }, [])

  const fetchUnread = React.useCallback(async () => {
    try {
      const data = await imApi.getUnreadCount({ silent: true, skipAuthRedirect: true })
      setUnread(data.total)
    } catch {
      // 忽略读取失败
    }
  }, [])

  React.useEffect(() => {
    if (!user?.id) return
    void fetchUnread()
    const unsubscribe = imApi.subscribeEvents({
      onNewMessage: () => void fetchUnread(),
      onConversationRead: () => void fetchUnread(),
    })
    return () => unsubscribe()
  }, [user?.id, fetchUnread])

  // 首次挂载时触发一次历史通知回填，避免只显示部署后的 IM 未读数
  React.useEffect(() => {
    if (!user?.id || !currentTeam?.id || typeof window === 'undefined') return
    const marker = `im-legacy-synced:${user.id}:${currentTeam.id}`
    if (window.sessionStorage?.getItem(marker)) return
    imApi
      .listConversations(currentTeam.id)
      .then(() => {
        window.sessionStorage?.setItem(marker, '1')
        void fetchUnread()
      })
      .catch(() => {})
  }, [user?.id, currentTeam?.id, fetchUnread])

  if (!user?.id) return null

  return (
    <>
      <Button
        variant="outline"
        size="icon"
        className="relative rounded-full bg-background/90 shadow-sm"
        aria-label={t('title')}
        title={t('title')}
        onClick={() => setOpen(true)}
      >
        <Bell className="size-4" />
        {unread > 0 && (
          <span className="absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-destructive px-1 text-[10px] text-white">
            {unread > 99 ? '99+' : unread}
          </span>
        )}
      </Button>
      <MessageCenterDialog
        open={open}
        onOpenChange={setOpen}
        currentUserId={user.id}
        onUnreadUpdated={fetchUnread}
      />
    </>
  )
}
