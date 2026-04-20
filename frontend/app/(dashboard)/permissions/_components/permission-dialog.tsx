'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { toast } from 'sonner'
import { permissionsApi, type Permission } from '@/lib/api/admin/roles'
import { normalizeValidationErrors, clearValidationError, getValidationSummaryEntries,
  formatValidationSummaryMessage
} from '@/lib/validation'
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
import { FieldError } from '@/components/ui/field'

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
  const [fieldErrors, setFieldErrors] = React.useState<Record<string, string>>({})
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
      setFieldErrors({})
    }
  }, [open, permission])
  
  const summaryEntries = React.useMemo(
    () => getValidationSummaryEntries(fieldErrors, ['scope', 'code', 'description']),
    [fieldErrors]
  )

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setFieldErrors({})
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
    } catch (error) {
      const errors = normalizeValidationErrors(error)
      if (Object.keys(errors).length > 0) {
        setFieldErrors(errors)
      }
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
          {summaryEntries.length > 0 && (
            <div className="mb-4 rounded-md border border-destructive/30 bg-destructive/5 p-3 space-y-1">
              {summaryEntries.map(([field, message]) => (
                <FieldError key={field}>
                  {formatValidationSummaryMessage(field, message)}
                </FieldError>
              ))}
            </div>
          )}
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="scope">{t('scope')} *</Label>
              <Input
                id="scope"
                value={scope}
                onChange={(e) => {
                  setScope(e.target.value)
                  setFieldErrors((prev) => clearValidationError(prev, 'scope'))
                }}
                placeholder={t('scopePlaceholder')}
                required
                aria-invalid={!!fieldErrors.scope}
              />
              <FieldError>{fieldErrors.scope}</FieldError>
              <p className="text-xs text-muted-foreground">{t('scopeHint')}</p>
            </div>
            
            <div className="space-y-2">
              <Label htmlFor="code">{t('code')} *</Label>
              <Input
                id="code"
                value={code}
                onChange={(e) => {
                  setCode(e.target.value)
                  setFieldErrors((prev) => clearValidationError(prev, 'code'))
                }}
                placeholder={t('codePlaceholder')}
                required
                aria-invalid={!!fieldErrors.code}
              />
              <FieldError>{fieldErrors.code}</FieldError>
              <p className="text-xs text-muted-foreground">{t('codeHint')}</p>
            </div>
            
            <div className="space-y-2">
              <Label htmlFor="description">{t('permissionDescription')}</Label>
              <Textarea
                id="description"
                value={description}
                onChange={(e) => {
                  setDescription(e.target.value)
                  setFieldErrors((prev) => clearValidationError(prev, 'description'))
                }}
                placeholder={t('descriptionPlaceholder')}
                rows={2}
                aria-invalid={!!fieldErrors.description}
              />
              <FieldError>{fieldErrors.description}</FieldError>
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
