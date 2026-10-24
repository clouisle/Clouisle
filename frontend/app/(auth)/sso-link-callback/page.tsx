'use client'

import * as React from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { toast } from 'sonner'
import { CheckCircle2, Loader2, XCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { ApiError } from '@/lib/api/client'
import { ssoApi, ssoLinkState } from '@/lib/api/sso'

type LinkStatus = 'confirm' | 'completing' | 'success' | 'invalid' | 'error'

/**
 * The backend redirects here after staging the Feishu identity for the
 * authenticated account. The pending session id stored by the settings dialog
 * must match the URL state; otherwise this is an unsolicited link attempt and
 * no completion request is sent.
 */
export default function SSOLinkCallbackPage() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const t = useTranslations('auth')
  const [status, setStatus] = React.useState<LinkStatus>('confirm')
  const [sessionId, setSessionId] = React.useState<string | null>(null)

  React.useEffect(() => {
    // A backend-side rejection (stale, disabled, or failed authorization)
    // arrives without a session id and must never trigger a completion call.
    if (searchParams.get('error')) {
      ssoLinkState.clear()
      setStatus('error')
      return
    }

    const state = searchParams.get('session_id')
    const pending = ssoLinkState.read()

    if (!state || !pending || state !== pending) {
      ssoLinkState.clear()
      setStatus('invalid')
      return
    }

    setSessionId(state)
  }, [searchParams])

  const handleConfirm = async () => {
    if (!sessionId) return

    setStatus('completing')
    try {
      await ssoApi.completeLink(sessionId)
      ssoLinkState.clear()
      setStatus('success')
    } catch (error) {
      ssoLinkState.clear()
      if (error instanceof ApiError) {
        toast.error(error.message)
      } else {
        toast.error(t('ssoLinkCallbackFailedTitle'))
      }
      setStatus('error')
    }
  }

  return (
    <Card className="bg-transparent shadow-none ring-0">
      <CardHeader className="text-center">
        <CardTitle className="text-2xl">{t('ssoLinkCallbackTitle')}</CardTitle>
        <CardDescription>{t('ssoLinkCallbackDescription')}</CardDescription>
      </CardHeader>
      <CardContent>
        {(status === 'confirm' || status === 'completing') && (
          <div className="space-y-6">
            <div className="flex flex-col items-center space-y-2 text-center">
              <Loader2 className="h-8 w-8 animate-spin text-primary" />
              <p className="text-sm text-muted-foreground">{t('ssoLinkCallbackProcessing')}</p>
            </div>
            <Button
              onClick={handleConfirm}
              className="w-full"
              disabled={status === 'completing'}
            >
              {status === 'completing' && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {t('ssoLinkCallbackConfirm')}
            </Button>
          </div>
        )}

        {status === 'success' && (
          <div className="space-y-6">
            <div className="flex flex-col items-center space-y-2 text-center">
              <div className="flex h-12 w-12 items-center justify-center rounded-full bg-green-500/10">
                <CheckCircle2 className="h-6 w-6 text-green-500" />
              </div>
              <h3 className="font-semibold">{t('ssoLinkCallbackSuccessTitle')}</h3>
              <p className="text-sm text-muted-foreground">
                {t('ssoLinkCallbackSuccessDescription')}
              </p>
            </div>
            <Button onClick={() => router.push('/app')} className="w-full">
              {t('ssoLinkCallbackReturnToApp')}
            </Button>
          </div>
        )}

        {status === 'invalid' && (
          <div className="space-y-6">
            <div className="flex flex-col items-center space-y-2 text-center">
              <div className="flex h-12 w-12 items-center justify-center rounded-full bg-destructive/10">
                <XCircle className="h-6 w-6 text-destructive" />
              </div>
              <h3 className="font-semibold text-destructive">{t('ssoLinkCallbackInvalidTitle')}</h3>
              <p className="text-sm text-muted-foreground">
                {t('ssoLinkCallbackInvalidDescription')}
              </p>
            </div>
            <Button onClick={() => router.push('/app')} className="w-full">
              {t('ssoLinkCallbackBackToSettings')}
            </Button>
          </div>
        )}

        {status === 'error' && (
          <div className="space-y-6">
            <div className="flex flex-col items-center space-y-2 text-center">
              <div className="flex h-12 w-12 items-center justify-center rounded-full bg-destructive/10">
                <XCircle className="h-6 w-6 text-destructive" />
              </div>
              <h3 className="font-semibold text-destructive">{t('ssoLinkCallbackFailedTitle')}</h3>
              <p className="text-sm text-muted-foreground">
                {t('ssoLinkCallbackFailedDescription')}
              </p>
            </div>
            <Button onClick={() => router.push('/app')} className="w-full">
              {t('ssoLinkCallbackBackToSettings')}
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
