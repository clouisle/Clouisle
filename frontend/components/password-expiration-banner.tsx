'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { usersApi, type PasswordStatus } from '@/lib/api'
import { AlertCircle, X } from 'lucide-react'
import Link from 'next/link'

export function PasswordExpirationBanner() {
  const t = useTranslations('auth')
  const [status, setStatus] = React.useState<PasswordStatus | null>(null)
  const [dismissed, setDismissed] = React.useState(false)
  const [loading, setLoading] = React.useState(true)

  React.useEffect(() => {
    const loadStatus = async () => {
      try {
        const data = await usersApi.getPasswordStatus()
        setStatus(data)
      } catch {
        // Failed to load status, don't show banner
      } finally {
        setLoading(false)
      }
    }

    loadStatus()
  }, [])

  // Don't show banner if loading, dismissed, exempt, or not expiring soon
  if (loading || dismissed || !status || status.is_exempt) {
    return null
  }

  // Show warning if expiring within 7 days
  const shouldWarn = status.days_until_expiration !== null &&
                     status.days_until_expiration > 0 &&
                     status.days_until_expiration <= 7

  if (!shouldWarn) {
    return null
  }

  return (
    <Alert className="relative border-yellow-500 bg-yellow-50 dark:bg-yellow-950">
      <AlertCircle className="h-4 w-4 text-yellow-600 dark:text-yellow-400" />
      <AlertDescription className="flex items-center justify-between gap-4">
        <span className="text-yellow-800 dark:text-yellow-200">
          {t('passwordExpiringSoon', { days: status.days_until_expiration })}
        </span>
        <div className="flex items-center gap-2">
          <Link href="/profile">
            <Button variant="outline" size="sm" className="h-8">
              {t('changePasswordNow')}
            </Button>
          </Link>
          <Button
            variant="ghost"
            size="sm"
            className="h-8 w-8 p-0"
            onClick={() => setDismissed(true)}
          >
            <X className="h-4 w-4" />
          </Button>
        </div>
      </AlertDescription>
    </Alert>
  )
}
