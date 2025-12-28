'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { toast } from 'sonner'
import { apiKeysApi, type APIKey } from '@/lib/api'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

interface DeleteAPIKeyDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  apiKey: APIKey | null
  onSuccess?: () => void
}

export function DeleteAPIKeyDialog({ open, onOpenChange, apiKey, onSuccess }: DeleteAPIKeyDialogProps) {
  const t = useTranslations('apiKeys')
  const commonT = useTranslations('common')
  
  const [isDeleting, setIsDeleting] = React.useState(false)
  
  const handleDelete = async () => {
    if (!apiKey) return
    
    setIsDeleting(true)
    try {
      await apiKeysApi.deleteAPIKey(apiKey.id)
      toast.success(t('keyDeleted'))
      onSuccess?.()
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
          <DialogTitle>{t('deleteKey')}</DialogTitle>
          <DialogDescription>
            {t('deleteKeyConfirm', { name: apiKey?.name ?? '' })}
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
