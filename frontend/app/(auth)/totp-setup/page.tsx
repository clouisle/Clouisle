'use client'

import * as React from 'react'
import { useRouter } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { toast } from 'sonner'
import { authApi } from '@/lib/api'
import { TOTPSetupWizardForced } from '@/components/totp-setup-wizard-forced'

export function getTotpSetupRedirect(hasTempToken: boolean, setupSucceeded: boolean): string {
  if (!hasTempToken) return '/login'
  return setupSucceeded ? '/' : '/login'
}

export default function TOTPSetupPage() {
  const t = useTranslations('auth')
  const router = useRouter()
  const [tempToken, setTempToken] = React.useState('')

  React.useEffect(() => {
    const token = localStorage.getItem('temp_token')
    if (!token) {
      toast.error(t('sessionExpired'))
      router.push(getTotpSetupRedirect(false, false))
      return
    }
    setTempToken(token)
  }, [router, t])

  const handleComplete = async () => {
    try {
      // Clear temp token
      localStorage.removeItem('temp_token')

      // Get new access token by calling getCurrentUser with temp token
      // The temp token is now a valid access token after TOTP setup
      localStorage.setItem('access_token', tempToken)
      await authApi.getCurrentUser()

      toast.success(t('setupStep5Description'))

      // Redirect to home
      router.push(getTotpSetupRedirect(true, true))
    } catch {
      toast.error(t('setupFailed'))
      router.push(getTotpSetupRedirect(true, false))
    }
  }

  if (!tempToken) {
    return null
  }

  return (
    <div className="flex min-h-screen items-center justify-center p-4 bg-muted/30">
      <div className="w-full max-w-2xl">
        <TOTPSetupWizardForced
          tempToken={tempToken}
          onComplete={handleComplete}
          onCancel={() => router.push('/login')}
        />
      </div>
    </div>
  )
}
