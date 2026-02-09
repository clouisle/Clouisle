'use client'

import * as React from 'react'
import { useSearchParams, useRouter } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { authApi, ApiError } from '@/lib/api'
import { Loader2, CheckCircle2, XCircle } from 'lucide-react'

export default function VerifyPage() {
  const t = useTranslations('auth')
  const router = useRouter()
  const searchParams = useSearchParams()
  const token = searchParams.get('token')

  const [status, setStatus] = React.useState<'loading' | 'success' | 'error'>('loading')
  const [errorMessage, setErrorMessage] = React.useState('')

  React.useEffect(() => {
    if (!token) {
      setStatus('error')
      setErrorMessage(t('verificationTokenMissing'))
      return
    }

    const verify = async () => {
      try {
        await authApi.verifyEmailByToken(token)
        setStatus('success')
      } catch (err) {
        setStatus('error')
        if (err instanceof ApiError) {
          setErrorMessage(err.message || t('verificationTokenInvalid'))
        } else {
          setErrorMessage(t('verificationTokenInvalid'))
        }
      }
    }

    verify()
  }, [token, t])

  return (
    <Card>
      <CardHeader className="text-center">
        <CardTitle className="text-2xl">{t('verifyYourEmail')}</CardTitle>
      </CardHeader>
      <CardContent>
        {status === 'loading' && (
          <div className="flex flex-col items-center space-y-4 py-8">
            <Loader2 className="h-8 w-8 animate-spin text-primary" />
            <p className="text-sm text-muted-foreground">{t('verifyingEmail')}</p>
          </div>
        )}

        {status === 'success' && (
          <div className="space-y-6">
            <div className="flex flex-col items-center text-center space-y-2">
              <div className="flex h-12 w-12 items-center justify-center rounded-full bg-green-500/10">
                <CheckCircle2 className="h-6 w-6 text-green-500" />
              </div>
              <h3 className="font-semibold">{t('emailVerifiedSuccess')}</h3>
              <p className="text-sm text-muted-foreground">
                {t('accountActivated')}
              </p>
            </div>
            <Button onClick={() => router.push('/login')} className="w-full">
              {t('goToLogin')}
            </Button>
          </div>
        )}

        {status === 'error' && (
          <div className="space-y-6">
            <div className="flex flex-col items-center text-center space-y-2">
              <div className="flex h-12 w-12 items-center justify-center rounded-full bg-destructive/10">
                <XCircle className="h-6 w-6 text-destructive" />
              </div>
              <h3 className="font-semibold text-destructive">{t('verificationTokenInvalid')}</h3>
              <p className="text-sm text-muted-foreground">{errorMessage}</p>
            </div>
            <Button onClick={() => router.push('/login')} className="w-full">
              {t('goToLogin')}
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
