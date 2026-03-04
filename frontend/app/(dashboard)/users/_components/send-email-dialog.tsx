'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { toast } from 'sonner'
import { Loader2 } from 'lucide-react'
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
import { usersApi, type User } from '@/lib/api/admin/users'

interface SendEmailDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  users: User[]
  onSuccess?: () => void
}

export function SendEmailDialog({
  open,
  onOpenChange,
  users,
  onSuccess,
}: SendEmailDialogProps) {
  const t = useTranslations('users')
  const commonT = useTranslations('common')
  
  const [subject, setSubject] = React.useState('')
  const [content, setContent] = React.useState('')
  const [sending, setSending] = React.useState(false)
  
  // 重置表单
  React.useEffect(() => {
    if (open) {
      setSubject('')
      setContent('')
    }
  }, [open])
  
  const handleSend = async () => {
    if (!subject.trim()) {
      toast.error(t('emailSubjectRequired'))
      return
    }
    if (!content.trim()) {
      toast.error(t('emailContentRequired'))
      return
    }
    
    setSending(true)
    try {
      const result = await usersApi.sendEmail(
        users.map(u => u.id),
        subject,
        content
      )
      
      if (result.skipped_count > 0) {
        // 部分发送成功，部分被限制
        toast.warning(t('emailSentPartial', { 
          sent: result.sent_count,
          skipped: result.skipped_count,
        }))
      } else {
        toast.success(t('emailSent', { count: result.sent_count }))
      }
      
      onOpenChange(false)
      onSuccess?.()
    } catch {
      // 错误已由 API 客户端处理
    } finally {
      setSending(false)
    }
  }
  
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle>{t('sendEmailTitle')}</DialogTitle>
          <DialogDescription>
            {t('sendEmailDescription', { count: users.length })}
          </DialogDescription>
        </DialogHeader>
        
        <div className="space-y-4 py-4">
          <div className="space-y-2">
            <Label htmlFor="subject">{t('emailSubject')}</Label>
            <Input
              id="subject"
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              placeholder={t('emailSubjectPlaceholder')}
              disabled={sending}
            />
          </div>
          
          <div className="space-y-2">
            <Label htmlFor="content">{t('emailContent')}</Label>
            <Textarea
              id="content"
              value={content}
              onChange={(e) => setContent(e.target.value)}
              placeholder={t('emailContentPlaceholder')}
              rows={6}
              disabled={sending}
            />
          </div>
          
          {users.length > 0 && (
            <div className="text-sm text-muted-foreground">
              {t('recipients')}: {users.slice(0, 3).map(u => u.email).join(', ')}
              {users.length > 3 && ` +${users.length - 3} ${t('more')}`}
            </div>
          )}
        </div>
        
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={sending}>
            {commonT('cancel')}
          </Button>
          <Button onClick={handleSend} disabled={sending}>
            {sending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {t('send')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
