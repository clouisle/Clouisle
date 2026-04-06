'use client'

import * as React from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { toast } from 'sonner'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { usersApi, ApiError } from '@/lib/api'
import { Loader2, AlertCircle } from 'lucide-react'
import { Alert, AlertDescription } from '@/components/ui/alert'

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
      if (err instanceof ApiError) {
        if (err.isValidationError()) {
          setFieldErrors(err.getFieldErrors())
        }
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
          <div className="space-y-2">
            <Label htmlFor="currentPassword">{t('currentPassword')}</Label>
            <Input
              id="currentPassword"
              type="password"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              required
              autoComplete="current-password"
            />
            {fieldErrors.current_password && (
              <p className="text-sm text-destructive">{fieldErrors.current_password}</p>
            )}
          </div>

          <div className="space-y-2">
            <Label htmlFor="newPassword">{t('newPassword')}</Label>
            <Input
              id="newPassword"
              type="password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              required
              autoComplete="new-password"
            />
            {fieldErrors.new_password && (
              <p className="text-sm text-destructive">{fieldErrors.new_password}</p>
            )}
          </div>

          <div className="space-y-2">
            <Label htmlFor="confirmPassword">{t('confirmNewPassword')}</Label>
            <Input
              id="confirmPassword"
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              required
              autoComplete="new-password"
            />
            {fieldErrors.confirmPassword && (
              <p className="text-sm text-destructive">{fieldErrors.confirmPassword}</p>
            )}
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
