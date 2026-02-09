'use client'

import * as React from 'react'
import { useRouter } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { toast } from 'sonner'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { authApi, ApiError } from '@/lib/api'
import { Loader2, CheckCircle2, KeyRound } from 'lucide-react'

interface ResetPasswordByTokenFormProps {
  token: string
}

export function ResetPasswordByTokenForm({ token }: ResetPasswordByTokenFormProps) {
  const t = useTranslations('auth')
  const router = useRouter()

  const [newPassword, setNewPassword] = React.useState('')
  const [confirmPassword, setConfirmPassword] = React.useState('')
  const [fieldErrors, setFieldErrors] = React.useState<Record<string, string>>({})
  const [loading, setLoading] = React.useState(false)
  const [success, setSuccess] = React.useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setFieldErrors({})

    if (newPassword.length < 6) {
      setFieldErrors({ newPassword: t('passwordTooShort') })
      return
    }

    if (newPassword !== confirmPassword) {
      setFieldErrors({ confirmPassword: t('passwordMismatch') })
      return
    }

    setLoading(true)

    try {
      await authApi.resetPasswordByToken(token, newPassword)
      toast.success(t('passwordResetSuccess'))
      setSuccess(true)
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.isValidationError()) {
          setFieldErrors(err.getFieldErrors())
        } else if (err.code === 5005) {
          setFieldErrors({ token: t('verificationTokenInvalid') })
        }
      }
    } finally {
      setLoading(false)
    }
  }

  if (success) {
    return (
      <div className="space-y-6">
        <div className="flex flex-col items-center text-center space-y-2">
          <div className="flex h-12 w-12 items-center justify-center rounded-full bg-green-500/10">
            <CheckCircle2 className="h-6 w-6 text-green-500" />
          </div>
          <h3 className="font-semibold">{t('passwordResetComplete')}</h3>
          <p className="text-sm text-muted-foreground">
            {t('passwordResetSuccessMessage')}
          </p>
        </div>
        <Button onClick={() => router.push('/login')} className="w-full">
          <KeyRound className="mr-2 h-4 w-4" />
          {t('goToLogin')}
        </Button>
      </div>
    )
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      {fieldErrors.token && (
        <p className="text-sm text-destructive text-center">{fieldErrors.token}</p>
      )}

      <div className="space-y-2">
        <Label htmlFor="newPassword">{t('newPassword')}</Label>
        <Input
          id="newPassword"
          type="password"
          value={newPassword}
          onChange={(e) => {
            setNewPassword(e.target.value)
            if (fieldErrors.newPassword) {
              setFieldErrors(prev => { const next = { ...prev }; delete next.newPassword; return next })
            }
          }}
          required
          disabled={loading}
          aria-invalid={!!fieldErrors.newPassword}
        />
        {fieldErrors.newPassword && (
          <p className="text-sm text-destructive">{fieldErrors.newPassword}</p>
        )}
      </div>

      <div className="space-y-2">
        <Label htmlFor="confirmPassword">{t('confirmNewPassword')}</Label>
        <Input
          id="confirmPassword"
          type="password"
          value={confirmPassword}
          onChange={(e) => {
            setConfirmPassword(e.target.value)
            if (fieldErrors.confirmPassword) {
              setFieldErrors(prev => { const next = { ...prev }; delete next.confirmPassword; return next })
            }
          }}
          required
          disabled={loading}
          aria-invalid={!!fieldErrors.confirmPassword}
        />
        {fieldErrors.confirmPassword && (
          <p className="text-sm text-destructive">{fieldErrors.confirmPassword}</p>
        )}
      </div>

      <Button type="submit" className="w-full" disabled={loading}>
        {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
        {t('resetPassword')}
      </Button>
    </form>
  )
}
