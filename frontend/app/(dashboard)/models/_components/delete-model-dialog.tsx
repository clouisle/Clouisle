'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { toast } from 'sonner'
import { modelsApi, type Model } from '@/lib/api/admin/models'
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

interface DeleteModelDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  model: Model | null
  onSuccess: () => void
}

export function DeleteModelDialog({
  open,
  onOpenChange,
  model,
  onSuccess,
}: DeleteModelDialogProps) {
  const t = useTranslations('models')
  const commonT = useTranslations('common')
  const [isLoading, setIsLoading] = React.useState(false)

  const handleDelete = async () => {
    if (!model) return
    
    setIsLoading(true)
    try {
      await modelsApi.deleteModel(model.id)
      toast.success(t('modelDeleted'))
      onOpenChange(false)
      onSuccess()
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
          <AlertDialogTitle>{t('confirmDelete')}</AlertDialogTitle>
          <AlertDialogDescription>
            {t('deleteModelConfirm', { name: model?.name || '' })}
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
