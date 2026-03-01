'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { toast } from 'sonner'
import { rolesApi, type Role } from '@/lib/api/admin/roles'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'

interface DeleteRoleDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  role: Role | null
  onSuccess: () => void
}

export function DeleteRoleDialog({ open, onOpenChange, role, onSuccess }: DeleteRoleDialogProps) {
  const t = useTranslations('roles')
  const commonT = useTranslations('common')
  const [isLoading, setIsLoading] = React.useState(false)
  
  const handleDelete = async () => {
    if (!role) return
    
    setIsLoading(true)
    try {
      await rolesApi.deleteRole(role.id)
      toast.success(t('roleDeleted'))
      onSuccess()
      onOpenChange(false)
    } catch {
      // 错误已由 API 客户端处理
    } finally {
      setIsLoading(false)
    }
  }
  
  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{t('deleteRole')}</AlertDialogTitle>
          <AlertDialogDescription>
            {t('deleteRoleConfirm', { name: role?.name || '' })}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={isLoading}>{commonT('cancel')}</AlertDialogCancel>
          <AlertDialogAction
            variant="destructive"
            onClick={handleDelete}
            disabled={isLoading}
          >
            {isLoading ? commonT('loading') : commonT('delete')}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
