'use client'

import { useEffect } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'

export default function SSOCallbackPage() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const t = useTranslations('auth')
  const error = searchParams.get('error')

  useEffect(() => {
    const token = searchParams.get('token')
    const redirect = searchParams.get('redirect') || '/dashboard'

    if (error) {
      return
    }

    if (token) {
      localStorage.setItem('access_token', token)
      toast.success(t('loginSuccess'))
      router.push(redirect)
    } else {
      toast.error(t('loginFailed'))
      router.push('/login')
    }
  }, [router, searchParams])

  return (
    <div className="flex min-h-screen items-center justify-center">
      <div className="text-center">
        {error ? (
          <>
            <p className="mb-2 text-lg font-medium">
              {error === 'inactive' ? t('ssoCallbackInactiveTitle') : t('ssoCallbackFailedTitle')}
            </p>
            <p className="mb-6 text-sm text-muted-foreground">
              {error === 'inactive'
                ? t('ssoCallbackInactiveDescription')
                : t('ssoCallbackFailedDescription')}
            </p>
            <Button onClick={() => router.push('/login')}>{t('ssoCallbackBackToLogin')}</Button>
          </>
        ) : (
          <>
            <div className="mb-4 inline-block h-8 w-8 animate-spin rounded-full border-4 border-solid border-current border-r-transparent motion-reduce:animate-[spin_1.5s_linear_infinite]" />
            <p className="text-muted-foreground">{t('ssoCallbackProcessing')}</p>
          </>
        )}
      </div>
    </div>
  )
}
