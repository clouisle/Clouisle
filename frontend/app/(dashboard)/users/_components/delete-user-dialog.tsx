'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { toast } from 'sonner'
import { usersApi, type User } from '@/lib/api/admin/users'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

interface DeleteUserDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  user: User | null
  onSuccess?: (user: User) => void
}

export function DeleteUserDialog({ open, onOpenChange, user, onSuccess }: DeleteUserDialogProps) {
  const t = useTranslations('users')
  const commonT = useTranslations('common')
  
  const [isDeleting, setIsDeleting] = React.useState(false)
  
  const handleDelete = async () => {
    if (!user) return
    
    setIsDeleting(true)
    try {
      const deletedUser = await usersApi.deleteUser(user.id)
      toast.success(t('userDeleted'))
      onSuccess?.(deletedUser)
      onOpenChange(false)
    } catch {
      // 错误已由 API 客户端处理
    } finally {
      setIsDeleting(false)
    }
  }
  
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[425px]">
        <DialogHeader>
          <DialogTitle>{t('deleteUser')}</DialogTitle>
          <DialogDescription>
            {t('deleteUserConfirm', { username: user?.username ?? '' })}
          </DialogDescription>
        </DialogHeader>
        
        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={isDeleting}
          >
            {commonT('cancel')}
          </Button>
          <Button
            type="button"
            variant="destructive"
            onClick={handleDelete}
            disabled={isDeleting}
          >
            {isDeleting ? commonT('loading') : commonT('delete')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
