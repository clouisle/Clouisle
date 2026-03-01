'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { toast } from 'sonner'
import { permissionsApi, type Permission } from '@/lib/api/admin/roles'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

interface PermissionDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  permission: Permission | null
  onSuccess: () => void
}

export function PermissionDialog({ open, onOpenChange, permission, onSuccess }: PermissionDialogProps) {
  const t = useTranslations('permissions')
  const commonT = useTranslations('common')
  
  const [scope, setScope] = React.useState('')
  const [code, setCode] = React.useState('')
  const [description, setDescription] = React.useState('')
  const [isLoading, setIsLoading] = React.useState(false)
  
  const isEdit = !!permission
  
  // 初始化表单
  React.useEffect(() => {
    if (open) {
      if (permission) {
        setScope(permission.scope)
        setCode(permission.code)
        setDescription(permission.description || '')
      } else {
        setScope('')
        setCode('')
        setDescription('')
      }
    }
  }, [open, permission])
  
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setIsLoading(true)
    
    try {
      if (isEdit && permission) {
        await permissionsApi.updatePermission(permission.id, { scope, code, description })
        toast.success(t('permissionUpdated'))
      } else {
        await permissionsApi.createPermission({ scope, code, description })
        toast.success(t('permissionCreated'))
      }
      onSuccess()
      onOpenChange(false)
    } catch {
      // 错误已由 API 客户端处理
    } finally {
      setIsLoading(false)
    }
  }
  
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{isEdit ? t('editPermission') : t('createPermission')}</DialogTitle>
          <DialogDescription>
            {isEdit ? t('editPermissionDescription') : t('createPermissionDescription')}
          </DialogDescription>
        </DialogHeader>
        
        <form onSubmit={handleSubmit}>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="scope">{t('scope')} *</Label>
              <Input
                id="scope"
                value={scope}
                onChange={(e) => setScope(e.target.value)}
                placeholder={t('scopePlaceholder')}
                required
              />
              <p className="text-xs text-muted-foreground">{t('scopeHint')}</p>
            </div>
            
            <div className="space-y-2">
              <Label htmlFor="code">{t('code')} *</Label>
              <Input
                id="code"
                value={code}
                onChange={(e) => setCode(e.target.value)}
                placeholder={t('codePlaceholder')}
                required
              />
              <p className="text-xs text-muted-foreground">{t('codeHint')}</p>
            </div>
            
            <div className="space-y-2">
              <Label htmlFor="description">{t('permissionDescription')}</Label>
              <Textarea
                id="description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder={t('descriptionPlaceholder')}
                rows={2}
              />
            </div>
          </div>
          
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={isLoading}
            >
              {commonT('cancel')}
            </Button>
            <Button type="submit" disabled={isLoading || !scope || !code}>
              {isLoading ? commonT('loading') : (isEdit ? commonT('save') : commonT('create'))}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
