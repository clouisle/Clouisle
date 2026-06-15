'use client'

import * as React from 'react'
import { LocaleSwitcher } from '@/components/locale-switcher'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { useTranslations } from 'next-intl'
import type { AuthPageLayout, PublicSiteSettings } from '@/lib/api/site-settings'
import { LegalMarkdown } from './legal-markdown'

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

interface AuthLayoutShellProps {
  children: React.ReactNode
  layout: AuthPageLayout
  previewImageAlt: string
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
      <DialogContent className="max-h-[80vh] overflow-hidden sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{label}</DialogTitle>
        </DialogHeader>
        <div className="max-h-[60vh] overflow-y-auto text-sm text-foreground">
          <LegalMarkdown source={text} />
        </div>
      </DialogContent>
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
  legalSettings,
}: AuthLayoutShellProps) {
  const isSplit = layout === 'split'

  if (!isSplit) {
    return (
      <div className="flex min-h-screen flex-col bg-muted/50">
        <div className="fixed right-4 top-4 z-10">
          <LocaleSwitcher />
        </div>
        <div className="flex flex-1 items-center justify-center">
          <div className="w-full max-w-md p-4">
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
