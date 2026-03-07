'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { toast } from 'sonner'
import { Loader2 } from 'lucide-react'
import { notificationsApi } from '@/lib/api/admin/notifications'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Badge } from '@/components/ui/badge'

interface SendNotificationDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  userIds: string[]
  users: Array<{ id: string; username: string; email: string }>
}

export function SendNotificationDialog({
  open,
  onOpenChange,
  userIds,
  users,
}: SendNotificationDialogProps) {
  const t = useTranslations('users')
  const commonT = useTranslations('common')
  const [title, setTitle] = React.useState('')
  const [content, setContent] = React.useState('')
  const [level, setLevel] = React.useState<'low' | 'medium' | 'high'>('medium')
  const [loading, setLoading] = React.useState(false)

  const selectedUsers = users.filter((u) => userIds.includes(u.id))

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    if (!title.trim()) {
      toast.error(t('notificationTitleRequired'))
      return
    }

    if (!content.trim()) {
      toast.error(t('notificationContentRequired'))
      return
    }

    setLoading(true)

    try {
      await notificationsApi.adminCreate({
        scope: 'user',
        user_ids: userIds,
        type: 'admin_notification',
        title,
        content,
        level,
      })

      toast.success(t('notificationSent', { count: userIds.length }))
      setTitle('')
      setContent('')
      setLevel('medium')
      onOpenChange(false)
    } catch {
      // 错误已由 API 客户端处理
    } finally {
      setLoading(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[600px]">
        <DialogHeader>
          <DialogTitle>{t('sendNotificationTitle')}</DialogTitle>
          <DialogDescription>
            {t('sendNotificationDescription', { count: userIds.length })}
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label>{t('recipients')}</Label>
            <div className="flex flex-wrap gap-2 p-3 border rounded-md bg-muted/50 max-h-32 overflow-y-auto">
              {selectedUsers.slice(0, 5).map((user) => (
                <Badge key={user.id} variant="secondary">
                  {user.username}
                </Badge>
              ))}
              {selectedUsers.length > 5 && (
                <Badge variant="outline">
                  +{selectedUsers.length - 5} {t('more')}
                </Badge>
              )}
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="title">{t('notificationTitle')}</Label>
            <Input
              id="title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder={t('notificationTitlePlaceholder')}
              required
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="level">{t('notificationLevel')}</Label>
            <Select value={level} onValueChange={(v: 'low' | 'medium' | 'high') => setLevel(v)}>
              <SelectTrigger>
                <SelectValue>
                  {level === 'low' && t('levelLow')}
                  {level === 'medium' && t('levelMedium')}
                  {level === 'high' && t('levelHigh')}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="low">{t('levelLow')}</SelectItem>
                <SelectItem value="medium">{t('levelMedium')}</SelectItem>
                <SelectItem value="high">{t('levelHigh')}</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label htmlFor="content">{t('notificationContent')}</Label>
            <Textarea
              id="content"
              value={content}
              onChange={(e) => setContent(e.target.value)}
              placeholder={t('notificationContentPlaceholder')}
              rows={6}
              required
            />
          </div>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={loading}
            >
              {commonT('cancel')}
            </Button>
            <Button type="submit" disabled={loading}>
              {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {t('send')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
