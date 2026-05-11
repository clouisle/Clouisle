'use client'

import * as React from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { toast } from 'sonner'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { usersApi } from '@/lib/api'
import {
  clearValidationError,
  formatValidationSummaryMessage,
  getValidationSummaryEntries,
  normalizeValidationErrors,
} from '@/lib/validation'
import { Loader2, AlertCircle } from 'lucide-react'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { FieldError } from '@/components/ui/field'

export default function ChangePasswordPage() {
  const t = useTranslations('auth')
  const router = useRouter()
  const searchParams = useSearchParams()

  const [currentPassword, setCurrentPassword] = React.useState('')
  const [newPassword, setNewPassword] = React.useState('')
  const [confirmPassword, setConfirmPassword] = React.useState('')
  const [fieldErrors, setFieldErrors] = React.useState<Record<string, string>>({})
  const [loading, setLoading] = React.useState(false)

  const reason = searchParams.get('reason') // 'expired' or 'force'
  const summaryEntries = React.useMemo(
    () => getValidationSummaryEntries(fieldErrors, ['current_password', 'new_password', 'confirmPassword']),
    [fieldErrors]
  )
  const summaryFieldLabels = React.useMemo(
    () => ({
      current_password: t('currentPassword'),
      new_password: t('newPassword'),
      confirmPassword: t('confirmNewPassword'),
    }),
    [t]
  )

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setFieldErrors({})

    // Validate passwords match
    if (newPassword !== confirmPassword) {
      setFieldErrors({ confirmPassword: t('passwordMismatch') })
      return
    }

    setLoading(true)

    try {
      await usersApi.changePassword({
        current_password: currentPassword,
        new_password: newPassword,
      })

      toast.success(t('password_changed'))

      // Redirect to app after successful change
      const redirect = searchParams.get('redirect')
      router.push(redirect || '/app')
    } catch (err) {
      const errors = normalizeValidationErrors(err)
      if (Object.keys(errors).length > 0) {
        setFieldErrors(errors)
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <Card className="w-full max-w-md">
      <CardHeader className="text-center">
        <CardTitle className="text-2xl">
          {reason === 'expired' ? t('passwordExpired') : t('forcePasswordChange')}
        </CardTitle>
        <CardDescription>
          {reason === 'expired' ? t('passwordExpiredDescription') : t('forcePasswordChangeDescription')}
        </CardDescription>
      </CardHeader>
      <CardContent>
        {reason && (
          <Alert className="mb-4">
            <AlertCircle className="h-4 w-4" />
            <AlertDescription>
              {reason === 'expired' ? t('passwordExpiredDescription') : t('forcePasswordChangeDescription')}
            </AlertDescription>
          </Alert>
        )}

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

          <div className="space-y-2">
            <Label htmlFor="currentPassword">{t('currentPassword')}</Label>
            <Input
              id="currentPassword"
              type="password"
              value={currentPassword}
              onChange={(e) => {
                setCurrentPassword(e.target.value)
                setFieldErrors((prev) => clearValidationError(prev, 'current_password'))
              }}
              required
              autoComplete="current-password"
              aria-invalid={!!fieldErrors.current_password}
            />
            <FieldError>{fieldErrors.current_password}</FieldError>
          </div>

          <div className="space-y-2">
            <Label htmlFor="newPassword">{t('newPassword')}</Label>
            <Input
              id="newPassword"
              type="password"
              value={newPassword}
              onChange={(e) => {
                setNewPassword(e.target.value)
                setFieldErrors((prev) => clearValidationError(prev, 'new_password'))
              }}
              required
              autoComplete="new-password"
              aria-invalid={!!fieldErrors.new_password}
            />
            <FieldError>{fieldErrors.new_password}</FieldError>
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
              autoComplete="new-password"
              aria-invalid={!!fieldErrors.confirmPassword}
            />
            <FieldError>{fieldErrors.confirmPassword}</FieldError>
          </div>

          <Button type="submit" className="w-full" disabled={loading}>
            {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {t('changePasswordNow')}
          </Button>
        </form>
      </CardContent>
    </Card>
  )
}
