'use client'

import * as React from 'react'
import { useRouter } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { toast } from 'sonner'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { authApi, ApiError } from '@/lib/api'
import {
  clearValidationError,
  formatValidationSummaryMessage,
  getValidationSummaryEntries,
  normalizeValidationErrorsRaw,
} from '@/lib/validation'
import { FieldError } from '@/components/ui/field'
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

  const summaryEntries = React.useMemo(
    () => getValidationSummaryEntries(fieldErrors, ['newPassword', 'confirmPassword', 'token']),
    [fieldErrors]
  )
  const summaryFieldLabels = React.useMemo(
    () => ({
      newPassword: t('newPassword'),
      confirmPassword: t('confirmNewPassword'),
      token: t('verificationCode'),
    }),
    [t]
  )

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
          const rawErrors = normalizeValidationErrorsRaw(err)
          const renamedErrors = Object.fromEntries(
            Object.entries(rawErrors).map(([field, messages]) => [field === 'password' ? 'newPassword' : field, messages.join('; ')])
          )
          setFieldErrors(renamedErrors)
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
      {summaryEntries.length > 0 && (
        <div className="rounded-md border border-destructive/30 bg-destructive/5 p-3 space-y-1">
          {summaryEntries.map(([field, message]) => (
            <FieldError key={field}>
              {formatValidationSummaryMessage(field, message, summaryFieldLabels)}
            </FieldError>
          ))}
        </div>
      )}

      <FieldError className="text-center">{fieldErrors.token}</FieldError>

      <div className="space-y-2">
        <Label htmlFor="newPassword">{t('newPassword')}</Label>
        <Input
          id="newPassword"
          type="password"
          value={newPassword}
          onChange={(e) => {
            setNewPassword(e.target.value)
            setFieldErrors((prev) => clearValidationError(prev, 'newPassword'))
          }}
          required
          placeholder={t('newPasswordPlaceholder')}
          disabled={loading}
          aria-invalid={!!fieldErrors.newPassword}
        />
        <FieldError>{fieldErrors.newPassword}</FieldError>
      </div>

      <div className="space-y-2">
        <Label htmlFor="confirmPassword">{t('confirmNewPassword')}</Label>
        <Input
          id="confirmPassword"
          type="password"
          value={confirmPassword}
          onChange={(e) => {
            setConfirmPassword(e.target.value)
            setFieldErrors((prev) => clearValidationError(prev, 'confirmPassword'))
          }}
          required
          placeholder={t('confirmPasswordPlaceholder')}
          disabled={loading}
          aria-invalid={!!fieldErrors.confirmPassword}
        />
        <FieldError>{fieldErrors.confirmPassword}</FieldError>
      </div>

      <Button type="submit" className="w-full" disabled={loading}>
        {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
        {t('resetPassword')}
      </Button>
    </form>
  )
}
