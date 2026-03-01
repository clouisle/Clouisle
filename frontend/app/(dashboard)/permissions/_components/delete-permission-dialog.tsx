'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { toast } from 'sonner'
import { permissionsApi, type Permission } from '@/lib/api/admin/roles'
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

interface DeletePermissionDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  permission: Permission | null
  onSuccess: () => void
}

export function DeletePermissionDialog({ open, onOpenChange, permission, onSuccess }: DeletePermissionDialogProps) {
  const t = useTranslations('permissions')
  const commonT = useTranslations('common')
  
  const handleDelete = async () => {
    if (!permission) return
    
    try {
      await permissionsApi.deletePermission(permission.id)
      toast.success(t('permissionDeleted'))
      onSuccess()
      onOpenChange(false)
    } catch {
      // 错误已由 API 客户端处理
    }
  }
  
  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{t('confirmDelete')}</AlertDialogTitle>
          <AlertDialogDescription>
            {t('deletePermissionConfirm', { code: permission?.code || '' })}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>{commonT('cancel')}</AlertDialogCancel>
          <AlertDialogAction
            variant="destructive"
            onClick={handleDelete}
          >
            {commonT('delete')}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
