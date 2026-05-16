'use client'

import { useSearchParams, useRouter } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { useEffect } from 'react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { ResetPasswordByTokenForm } from './_components'

export default function ResetPasswordPage() {
  const t = useTranslations('auth')
  const router = useRouter()
  const searchParams = useSearchParams()
  const token = searchParams.get('token')

  useEffect(() => {
    if (!token) {
      router.replace('/forgot-password')
    }
  }, [token, router])

  if (!token) {
    return null
  }

  return (
    <Card className="bg-transparent shadow-none ring-0">
      <CardHeader className="text-center">
        <CardTitle className="text-2xl">{t('resetPasswordTitle')}</CardTitle>
        <CardDescription>{t('resetPasswordByLinkDescription')}</CardDescription>
      </CardHeader>
      <CardContent>
        <ResetPasswordByTokenForm token={token} />
      </CardContent>
    </Card>
  )
}
