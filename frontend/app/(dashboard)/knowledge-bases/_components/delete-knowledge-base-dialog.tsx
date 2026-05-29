'use client'

import { useTranslations } from 'next-intl'
import { toast } from 'sonner'
import { adminKnowledgeBasesApi, type KnowledgeBase } from '@/lib/api'
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

interface DeleteKnowledgeBaseDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  knowledgeBase: KnowledgeBase | null
  onSuccess: () => void
}

export function DeleteKnowledgeBaseDialog({
  open,
  onOpenChange,
  knowledgeBase,
  onSuccess,
}: DeleteKnowledgeBaseDialogProps) {
  const t = useTranslations('knowledgeBases')
  const commonT = useTranslations('common')
  
  const handleDelete = async () => {
    if (!knowledgeBase) return
    
    try {
      await adminKnowledgeBasesApi.deleteKnowledgeBase(knowledgeBase.id)
      toast.success(t('kbDeleted'))
      onOpenChange(false)
      onSuccess()
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
            {t('deleteKbConfirm', { name: knowledgeBase?.name || '' })}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>{commonT('cancel')}</AlertDialogCancel>
          <AlertDialogAction variant="destructive" onClick={handleDelete}>
            {commonT('delete')}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
