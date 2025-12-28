'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { toast } from 'sonner'
import { apiKeysApi, ApiError, type APIKey, type APIKeyCreateInput, type APIKeyUpdateInput } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

interface APIKeyDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  apiKey?: APIKey | null // 编辑时传入，创建时为 null
  onSuccess?: (key?: string) => void
}

export function APIKeyDialog({ open, onOpenChange, apiKey, onSuccess }: APIKeyDialogProps) {
  const t = useTranslations('apiKeys')
  const commonT = useTranslations('common')
  
  const isEditing = !!apiKey
  
  const [formData, setFormData] = React.useState({
    name: '',
    rate_limit: 0,
    expires_at: '',
    is_active: true,
  })
  const [fieldErrors, setFieldErrors] = React.useState<Record<string, string>>({})
  const [isSubmitting, setIsSubmitting] = React.useState(false)
  
  // 当 apiKey 改变或 dialog 打开时重置表单
  React.useEffect(() => {
    if (open) {
      if (apiKey) {
        setFormData({
          name: apiKey.name,
          rate_limit: apiKey.rate_limit,
          expires_at: apiKey.expires_at 
            ? new Date(apiKey.expires_at).toISOString().split('T')[0] 
            : '',
          is_active: apiKey.is_active,
        })
      } else {
        setFormData({
          name: '',
          rate_limit: 0,
          expires_at: '',
          is_active: true,
        })
      }
      setFieldErrors({})
    }
  }, [open, apiKey])
  
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setFieldErrors({})
    
    // 验证
    if (!formData.name.trim()) {
      setFieldErrors({ name: t('nameRequired') })
      return
    }
    
    setIsSubmitting(true)
    
    try {
      if (isEditing && apiKey) {
        // 编辑
        const updateData: APIKeyUpdateInput = {
          name: formData.name,
          rate_limit: formData.rate_limit,
          expires_at: formData.expires_at ? new Date(formData.expires_at).toISOString() : null,
          is_active: formData.is_active,
        }
        await apiKeysApi.updateAPIKey(apiKey.id, updateData)
        toast.success(t('keyUpdated'))
        onSuccess?.()
      } else {
        // 创建
        const createData: APIKeyCreateInput = {
          name: formData.name,
          rate_limit: formData.rate_limit,
          expires_at: formData.expires_at ? new Date(formData.expires_at).toISOString() : null,
        }
        const result = await apiKeysApi.createAPIKey(createData)
        toast.success(t('keyCreated'))
        onSuccess?.(result.key) // 传递新创建的 key
      }
      
      onOpenChange(false)
    } catch (error) {
      if (error instanceof ApiError && error.isValidationError()) {
        setFieldErrors(error.getFieldErrors())
      }
    } finally {
      setIsSubmitting(false)
    }
  }
  
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[425px]">
        <DialogHeader>
          <DialogTitle>{isEditing ? t('editKey') : t('createKey')}</DialogTitle>
          <DialogDescription>
            {isEditing ? t('editKeyDescription') : t('createKeyDescription')}
          </DialogDescription>
        </DialogHeader>
        
        <form onSubmit={handleSubmit} className="grid gap-4">
          <div className="grid gap-2">
            <Label htmlFor="name">{t('name')}</Label>
            <Input
              id="name"
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              placeholder={t('namePlaceholder')}
              required
              autoFocus
            />
            {fieldErrors.name && (
              <p className="text-sm text-destructive">{fieldErrors.name}</p>
            )}
          </div>
          
          <div className="grid gap-2">
            <Label htmlFor="rate_limit">{t('rateLimit')}</Label>
            <Input
              id="rate_limit"
              type="number"
              min="0"
              value={formData.rate_limit}
              onChange={(e) => setFormData({ ...formData, rate_limit: parseInt(e.target.value) || 0 })}
            />
            <p className="text-xs text-muted-foreground">{t('rateLimitHint')}</p>
          </div>
          
          <div className="grid gap-2">
            <Label htmlFor="expires_at">{t('expiresAt')}</Label>
            <Input
              id="expires_at"
              type="date"
              value={formData.expires_at}
              onChange={(e) => setFormData({ ...formData, expires_at: e.target.value })}
            />
            <p className="text-xs text-muted-foreground">{t('expiresAtHint')}</p>
          </div>
          
          {isEditing && (
            <div className="flex items-center justify-between">
              <Label htmlFor="is_active">{t('active')}</Label>
              <Switch
                id="is_active"
                checked={formData.is_active}
                onCheckedChange={(checked) => setFormData({ ...formData, is_active: checked })}
              />
            </div>
          )}
          
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={isSubmitting}
            >
              {commonT('cancel')}
            </Button>
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting
                ? commonT('loading')
                : isEditing
                  ? commonT('save')
                  : commonT('create')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
