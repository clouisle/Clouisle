'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { toast } from 'sonner'
import { type Tool } from '@/lib/api'
import { adminToolsApi } from '@/lib/api/admin'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

interface DeleteToolDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  tool: Tool | null
  onSuccess?: () => void
}

export function DeleteToolDialog({ open, onOpenChange, tool, onSuccess }: DeleteToolDialogProps) {
  const t = useTranslations('tools')
  const commonT = useTranslations('common')

  const [isDeleting, setIsDeleting] = React.useState(false)

  const handleDelete = async () => {
    if (!tool?.id) return

    setIsDeleting(true)
    try {
      await adminToolsApi.delete(tool.id)
      toast.success(t('toolDeleted'))
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
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{t('deleteTool')}</DialogTitle>
          <DialogDescription>
            {t('deleteToolConfirm', { name: tool?.display_name ?? '' })}
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
          <Button type="button" variant="destructive" onClick={handleDelete} disabled={isDeleting}>
            {isDeleting ? commonT('loading') : commonT('delete')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
