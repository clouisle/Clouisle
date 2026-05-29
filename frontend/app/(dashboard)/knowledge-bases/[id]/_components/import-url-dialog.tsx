'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { useRouter } from 'next/navigation'
import { Link, Loader2 } from 'lucide-react'
import { toast } from 'sonner'
import { adminKnowledgeBasesApi } from '@/lib/api'
import {
  clearValidationError,
  getValidationSummaryEntries,
  normalizeValidationErrors,
  formatValidationSummaryMessage
} from '@/lib/validation'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Field, FieldError } from '@/components/ui/field'

interface ImportUrlDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  knowledgeBaseId: string
  onSuccess: () => void
}

export function ImportUrlDialog({
  open,
  onOpenChange,
  knowledgeBaseId,
  onSuccess,
}: ImportUrlDialogProps) {
  const t = useTranslations('knowledgeBases')
  const commonT = useTranslations('common')
  const router = useRouter()
  
  const [url, setUrl] = React.useState('')
  const [name, setName] = React.useState('')
  const [isLoading, setIsLoading] = React.useState(false)
  const [fieldErrors, setFieldErrors] = React.useState<Record<string, string>>({})
  const summaryEntries = React.useMemo(
    () => getValidationSummaryEntries(fieldErrors, ['url', 'name']),
    [fieldErrors]
  )

  const updateUrl = React.useCallback((value: string) => {
    setUrl(value)
    setFieldErrors((prev) => clearValidationError(prev, 'url'))
  }, [])

  const updateName = React.useCallback((value: string) => {
    setName(value)
    setFieldErrors((prev) => clearValidationError(prev, 'name'))
  }, [])
  
  // 重置状态
  React.useEffect(() => {
    if (open) {
      setUrl('')
      setName('')
      setFieldErrors({})
    }
  }, [open])
  
  // 提交
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    
    // 验证 URL
    if (!url.trim()) {
      setFieldErrors({ url: t('urlRequired') })
      return
    }
    
    try {
      new URL(url.trim())
    } catch {
      setFieldErrors({ url: t('urlInvalid') })
      return
    }
    
    setIsLoading(true)
    setFieldErrors({})
    
    try {
      const doc = await adminKnowledgeBasesApi.importUrl(knowledgeBaseId, url.trim(), name.trim() || undefined)
      toast.success(t('urlImported'))
      onOpenChange(false)
      onSuccess()

      // 跳转到预览页面配置分段
      router.push(`/knowledge-bases/${knowledgeBaseId}/documents/preview?docs=${doc.id}`)
    } catch (error) {
      const validationErrors = normalizeValidationErrors(error)
      if (Object.keys(validationErrors).length > 0) {
        setFieldErrors(validationErrors)
      }
      // 其他错误已由 API 客户端处理
    } finally {
      setIsLoading(false)
    }
  }
  
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[500px]">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>{t('importUrl')}</DialogTitle>
            <DialogDescription>{t('importUrlDescription')}</DialogDescription>
          </DialogHeader>
          
          <div className="grid gap-4 py-4">
            {summaryEntries.length > 0 && (
              <div className="rounded-md border border-destructive/30 bg-destructive/5 p-3 space-y-1">
                {summaryEntries.map(([field, message]) => (
                  <FieldError key={field}>
                    {formatValidationSummaryMessage(field, message)}
                  </FieldError>
                ))}
              </div>
            )}
            {/* URL */}
            <Field>
              <Label htmlFor="url">{t('url')}</Label>
              <Input
                id="url"
                type="url"
                value={url}
                onChange={(e) => updateUrl(e.target.value)}
                placeholder={t('urlPlaceholder')}
                aria-invalid={!!fieldErrors.url}
              />
              <p className="text-xs text-muted-foreground">{t('urlHint')}</p>
              {fieldErrors.url && <FieldError>{fieldErrors.url}</FieldError>}
            </Field>
            
            {/* 名称（可选） */}
            <Field>
              <Label htmlFor="name">{t('documentName')} ({t('optional')})</Label>
              <Input
                id="name"
                value={name}
                onChange={(e) => updateName(e.target.value)}
                placeholder={t('documentNamePlaceholder')}
                aria-invalid={!!fieldErrors.name}
              />
              {fieldErrors.name && <FieldError>{fieldErrors.name}</FieldError>}
            </Field>
          </div>
          
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              {commonT('cancel')}
            </Button>
            <Button type="submit" disabled={isLoading}>
              {isLoading ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  {t('importing')}
                </>
              ) : (
                <>
                  <Link className="mr-2 h-4 w-4" />
                  {t('import')}
                </>
              )}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
