'use client'

import * as React from 'react'
import Image from 'next/image'
import { LocaleSwitcher } from '@/components/locale-switcher'
import {
  Dialog,
  DialogTrigger,
} from '@/components/ui/dialog'
import { useTranslations } from 'next-intl'
import type { AuthPageLayout, PublicSiteSettings } from '@/lib/api/site-settings'
import { LegalMarkdownDialogContent, preloadLegalMarkdown } from './legal-markdown'
import { DefaultSiteIcon } from '@/components/default-site-icon'
import { getBrandingVisibility } from '@/lib/theme-config'

type LegalSettings = Pick<
  PublicSiteSettings,
  | 'icp_record_number'
  | 'icp_record_url'
  | 'terms_enabled'
  | 'terms_url'
  | 'terms_text'
  | 'privacy_enabled'
  | 'privacy_url'
  | 'privacy_text'
>

type BrandingSettings = Pick<
  PublicSiteSettings,
  'site_name' | 'site_description' | 'site_icon' | 'theme_branding_display'
>

interface AuthLayoutShellProps {
  children: React.ReactNode
  layout: AuthPageLayout
  previewImageAlt: string
  brandingSettings: BrandingSettings
  legalSettings: LegalSettings
}

function LegalEntry({ label, url, text }: { label: string; url: string; text: string }) {
  if (url) {
    return (
      <a href={url} target="_blank" rel="noreferrer" className="hover:text-foreground underline underline-offset-4">
        {label}
      </a>
    )
  }

  if (!text) {
    return null
  }

  return (
    <Dialog>
      <DialogTrigger className="hover:text-foreground underline underline-offset-4">
        {label}
      </DialogTrigger>
      <LegalMarkdownDialogContent title={label} source={text} />
    </Dialog>
  )
}

function LegalFooter({ legalSettings, fixed = false }: { legalSettings: LegalSettings; fixed?: boolean }) {
  const t = useTranslations('auth')
  const hasIcp = !!legalSettings.icp_record_number
  const hasTerms = legalSettings.terms_enabled && (legalSettings.terms_url || legalSettings.terms_text)
  const hasPrivacy = legalSettings.privacy_enabled && (legalSettings.privacy_url || legalSettings.privacy_text)

  if (!hasIcp && !hasTerms && !hasPrivacy) {
    return null
  }

  return (
    <div className={`${fixed ? 'fixed inset-x-0 bottom-0' : ''} flex items-center justify-center gap-x-3 gap-y-1 pb-4 text-center text-xs text-muted-foreground`}>
        {hasTerms && (
          <LegalEntry label={t('termsOfService')} url={legalSettings.terms_url} text={legalSettings.terms_text} />
        )}
        {hasPrivacy && (
          <LegalEntry label={t('privacyPolicy')} url={legalSettings.privacy_url} text={legalSettings.privacy_text} />
        )}
      {hasIcp && (hasTerms || hasPrivacy) && <span>|</span>}
      {hasIcp && (
        legalSettings.icp_record_url ? (
          <a href={legalSettings.icp_record_url} target="_blank" rel="noreferrer" className="hover:text-foreground underline underline-offset-4">
            {legalSettings.icp_record_number}
          </a>
        ) : (
          <span>{legalSettings.icp_record_number}</span>
        )
      )}
    </div>
  )
}

function AuthBranding({ brandingSettings }: { brandingSettings: BrandingSettings }) {
  const { showIcon, showName } = getBrandingVisibility(brandingSettings.theme_branding_display)

  if (!showIcon && !showName) {
    return null
  }

  return (
    <div className="mb-6 flex flex-col items-center gap-2 text-center">
      {showIcon && (
        <div className={`flex size-14 items-center justify-center overflow-hidden rounded-xl ${brandingSettings.site_icon ? 'bg-primary text-primary-foreground' : ''}`}>
          {brandingSettings.site_icon ? (
            <Image
              src={brandingSettings.site_icon}
              alt={brandingSettings.site_name}
              width={56}
              height={56}
              className="size-full object-cover"
              unoptimized
            />
          ) : (
            <DefaultSiteIcon width={56} height={56} className="size-full" />
          )}
        </div>
      )}
      {showName && (
        <div className="space-y-1">
          <h1 className="text-2xl font-bold">{brandingSettings.site_name || 'Clouisle'}</h1>
          {brandingSettings.site_description && (
            <p className="text-sm text-muted-foreground">{brandingSettings.site_description}</p>
          )}
        </div>
      )}
    </div>
  )
}

function AuthPreviewPanel({ previewImageAlt }: Pick<AuthLayoutShellProps, 'previewImageAlt'>) {
  return (
    <aside className="relative hidden min-h-screen flex-1 overflow-hidden bg-muted/45 dark:bg-muted/25 lg:block">
      <img
        src="/clouisle.png"
        alt={previewImageAlt}
        className="absolute left-12 top-40 max-w-none rounded-2xl border border-slate-300/80 shadow-[0_32px_90px_rgba(15,23,42,0.28)] dark:border-white/20 dark:shadow-[0_32px_100px_rgba(0,0,0,0.78)] xl:left-16 xl:top-48"
        style={{ height: '80vh', width: 'auto' }}
      />
    </aside>
  )
}

export function AuthLayoutShell({
  children,
  layout,
  previewImageAlt,
  brandingSettings,
  legalSettings,
}: AuthLayoutShellProps) {
  const isSplit = layout === 'split'

  React.useEffect(() => {
    if (
      (legalSettings.terms_enabled && legalSettings.terms_text && !legalSettings.terms_url) ||
      (legalSettings.privacy_enabled && legalSettings.privacy_text && !legalSettings.privacy_url)
    ) {
      preloadLegalMarkdown()
    }
  }, [legalSettings])

  if (!isSplit) {
    return (
      <div className="flex min-h-screen flex-col bg-muted/50">
        <div className="fixed right-4 top-4 z-10">
          <LocaleSwitcher />
        </div>
        <div className="flex flex-1 items-center justify-center">
          <div className="w-full max-w-md p-4">
            <AuthBranding brandingSettings={brandingSettings} />
            {children}
          </div>
        </div>
        <LegalFooter legalSettings={legalSettings} fixed />
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-background lg:flex">
      <div className="fixed right-4 top-4 z-10">
        <LocaleSwitcher />
      </div>
      <main className="relative flex min-h-screen w-full items-center justify-center bg-background px-4 py-12 lg:w-[48%] lg:px-10 lg:pr-16 xl:pr-20">
        <div className="auth-layout-split w-full max-w-md">
          <AuthBranding brandingSettings={brandingSettings} />
          {children}
        </div>
        <div className="absolute inset-x-0 bottom-4 flex justify-center">
          <LegalFooter legalSettings={legalSettings} />
        </div>
      </main>
      <AuthPreviewPanel previewImageAlt={previewImageAlt} />
    </div>
  )
}
