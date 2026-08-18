'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { Copy, Check, AlertTriangle } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Alert, AlertDescription } from '@/components/ui/alert'

interface ShowKeyDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  apiKey: string | null
}

export function ShowKeyDialog({ open, onOpenChange, apiKey }: ShowKeyDialogProps) {
  const t = useTranslations('apiKeys')
  const commonT = useTranslations('common')
  
  const [copied, setCopied] = React.useState(false)
  
  const handleCopy = async () => {
    if (!apiKey) return
    
    try {
      await navigator.clipboard.writeText(apiKey)
      setCopied(true)
      toast.success(t('copied'))
      setTimeout(() => setCopied(false), 2000)
    } catch {
      toast.error(t('copyFailed'))
    }
  }
  
  // 重置复制状态
  React.useEffect(() => {
    if (open) {
      setCopied(false)
    }
  }, [open])
  
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle>{t('keyCreatedTitle')}</DialogTitle>
          <DialogDescription>
            {t('keyCreatedDescription')}
          </DialogDescription>
        </DialogHeader>
        
        <div className="space-y-4">
          <Alert variant="warning">
            <AlertTriangle className="h-4 w-4" />
            <AlertDescription>
              {t('keyWarning')}
            </AlertDescription>
          </Alert>
          
          <div className="flex gap-2">
            <Input
              readOnly
              value={apiKey || ''}
              className="font-mono text-sm"
            />
            <Button
              variant="outline"
              size="icon"
              onClick={handleCopy}
            >
              {copied ? (
                <Check className="h-4 w-4 text-green-500" />
              ) : (
                <Copy className="h-4 w-4" />
              )}
            </Button>
          </div>
        </div>
        
        <DialogFooter>
          <Button onClick={() => onOpenChange(false)}>
            {commonT('close')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
