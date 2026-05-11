'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { toast } from 'sonner'
import { Loader2 } from 'lucide-react'
import {
  clearValidationError,
  getValidationSummaryEntries,
  normalizeValidationErrors,
  formatValidationSummaryMessage
} from '@/lib/validation'
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
import { FieldError } from '@/components/ui/field'
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
  const [fieldErrors, setFieldErrors] = React.useState<Record<string, string>>({})
  const [sending, setSending] = React.useState(false)
  const summaryEntries = React.useMemo(
    () => getValidationSummaryEntries(fieldErrors, ['subject', 'content']),
    [fieldErrors]
  )

  // 重置表单
  React.useEffect(() => {
    if (open) {
      setSubject('')
      setContent('')
      setFieldErrors({})
    }
  }, [open])
  
  const handleSend = async () => {
    setFieldErrors({})

    if (!subject.trim()) {
      setFieldErrors({ subject: t('emailSubjectRequired') })
      return
    }
    if (!content.trim()) {
      setFieldErrors({ content: t('emailContentRequired') })
      return
    }

    setSending(true)
    try {
      const result = await usersApi.sendEmail(
        users.map(u => u.id),
        subject,
        content,
        { silent: true }
      )

      if (result.skipped_count > 0) {
        toast.warning(t('emailSentPartial', {
          sent: result.sent_count,
          skipped: result.skipped_count,
        }))
      } else {
        toast.success(t('emailSent', { count: result.sent_count }))
      }

      setFieldErrors({})
      onOpenChange(false)
      onSuccess?.()
    } catch (error) {
      const errors = normalizeValidationErrors(error)
      if (Object.keys(errors).length > 0) {
        setFieldErrors(errors)
      }
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
          {summaryEntries.length > 0 && (
            <div className="rounded-md border border-destructive/30 bg-destructive/5 p-3 space-y-1">
              {summaryEntries.map(([field, message]) => (
                <FieldError key={field}>
                  {formatValidationSummaryMessage(field, message)}
                </FieldError>
              ))}
            </div>
          )}

          <div className="space-y-2">
            <Label htmlFor="subject">{t('emailSubject')}</Label>
            <Input
              id="subject"
              value={subject}
              onChange={(e) => {
                setSubject(e.target.value)
                setFieldErrors((prev) => clearValidationError(prev, 'subject'))
              }}
              placeholder={t('emailSubjectPlaceholder')}
              disabled={sending}
              aria-invalid={!!fieldErrors.subject}
            />
            <FieldError>{fieldErrors.subject}</FieldError>
          </div>

          <div className="space-y-2">
            <Label htmlFor="content">{t('emailContent')}</Label>
            <Textarea
              id="content"
              value={content}
              onChange={(e) => {
                setContent(e.target.value)
                setFieldErrors((prev) => clearValidationError(prev, 'content'))
              }}
              placeholder={t('emailContentPlaceholder')}
              rows={6}
              disabled={sending}
              aria-invalid={!!fieldErrors.content}
            />
            <FieldError>{fieldErrors.content}</FieldError>
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
