'use client'

import { usePathname } from 'next/navigation'
import { useEffect, useState } from 'react'
import Link from 'next/link'
import { useTranslations } from 'next-intl'
import { Button } from '@/components/ui/button'
import { Home, ArrowLeft } from 'lucide-react'

export default function NotFound() {
  const t = useTranslations('errors')
  const pathname = usePathname()
  const [referrer, setReferrer] = useState<string>('')

  useEffect(() => {
    // Get the referrer URL (where user came from)
    setReferrer(document.referrer)
  }, [])

  // Determine home page based on referrer or current path
  const getHomePath = () => {
    // First, try to determine from referrer if it's from our site
    if (referrer) {
      try {
        const referrerUrl = new URL(referrer)
        const currentHost = window.location.host

        // Only use referrer if it's from the same site
        if (referrerUrl.host === currentHost) {
          if (referrerUrl.pathname.startsWith('/dashboard')) {
            return '/dashboard'
          }
          if (referrerUrl.pathname.startsWith('/app')) {
            return '/app'
          }
        }
      } catch {
        // Invalid URL, ignore
      }
    }

    // Fallback: determine from current 404 path
    if (pathname?.startsWith('/dashboard')) {
      return '/dashboard'
    }

    // Default to platform workspace
    return '/app'
  }

  const homePath = getHomePath()
  const isInDashboard = homePath === '/dashboard'

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-gradient-to-b from-background to-muted/20">
      <div className="text-center space-y-6 px-4 max-w-md">
        {/* 404 Number with gradient */}
        <div className="relative">
          <h1 className="text-9xl font-bold bg-gradient-to-br from-primary/80 to-primary/40 bg-clip-text text-transparent">
            404
          </h1>
          <div className="absolute inset-0 blur-3xl bg-primary/10 -z-10" />
        </div>

        {/* Error message */}
        <div className="space-y-2">
          <h2 className="text-2xl font-semibold tracking-tight">
            {t('notFound')}
          </h2>
          <p className="text-muted-foreground text-sm">
            {t('notFoundDescription')}
          </p>
        </div>

        {/* Action buttons */}
        <div className="flex flex-col sm:flex-row gap-3 justify-center pt-4">
          <Button
            onClick={() => window.history.back()}
            variant="outline"
            className="gap-2"
          >
            <ArrowLeft className="h-4 w-4" />
            {t('goBack')}
          </Button>
          <Link href={homePath}>
            <Button className="gap-2 w-full sm:w-auto">
              <Home className="h-4 w-4" />
              {isInDashboard ? t('goHome') : t('goHome')}
            </Button>
          </Link>
        </div>

        {/* Helpful hint */}
        <p className="text-xs text-muted-foreground pt-4">
          {isInDashboard
            ? t('backToDashboard')
            : t('backToWorkspace')}
        </p>
      </div>
    </div>
  )
}
