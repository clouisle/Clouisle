'use client'

import { useEffect } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { useTranslations, useLocale } from 'next-intl'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { authApi, usersApi } from '@/lib/api'

export function isInactiveSsoCallbackError(error: string | null): boolean {
  return error === 'inactive' || error === 'pending_approval'
}

export function getSsoCallbackRedirect(redirect: string | null): string {
  return redirect || '/app'
}

export default function SSOCallbackPage() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const t = useTranslations('auth')
  const locale = useLocale()
  const error = searchParams.get('error')

  useEffect(() => {
    const token = searchParams.get('token')
    const redirect = getSsoCallbackRedirect(searchParams.get('redirect'))

    if (error) {
      return
    }

    if (token) {
      localStorage.setItem('access_token', token)

      // 同步当前浏览器语言设置到后端用户数据
      const syncLocale = async () => {
        try {
          const user = await authApi.getCurrentUser({ skipAuthRedirect: true })
          if (!user.locale || user.locale !== locale) {
            await usersApi.updateProfile({ locale }, { skipAuthRedirect: true })
          }
        } catch {
          // 同步语言设置失败，不影响登录流程
        }
      }

      syncLocale()
      toast.success(t('loginSuccess'))
      router.push(redirect)
    } else {
      toast.error(t('loginFailed'))
      router.push('/login')
    }
  }, [error, router, searchParams, locale, t])

  return (
    <div className="flex min-h-screen items-center justify-center">
      <div className="text-center">
        {error ? (
          <>
            <p className="mb-2 text-lg font-medium">
              {isInactiveSsoCallbackError(error)
                ? t('ssoCallbackInactiveTitle')
                : t('ssoCallbackFailedTitle')}
            </p>
            <p className="mb-6 text-sm text-muted-foreground">
              {isInactiveSsoCallbackError(error)
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
