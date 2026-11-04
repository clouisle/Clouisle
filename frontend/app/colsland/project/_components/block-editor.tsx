'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import dynamic from 'next/dynamic'

const RichEditor = dynamic(() => import('./rich-editor').then(module => module.RichEditor), { ssr: false })

export function BlockEditor() {
  const t = useTranslations('platform.colslandEditor')
  const [title, setTitle] = React.useState('')

  return (
    <section className="mx-auto w-full max-w-4xl px-5 pb-36 pt-12 sm:px-12 sm:pt-20" aria-label={t('document')}>
      <div className="mb-8 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        <span className="font-medium text-foreground">Colsland</span>
        <span aria-hidden="true">/</span>
        <span>{t('document')}</span>
        <span className="rounded-full border border-amber-500/30 bg-amber-500/10 px-2.5 py-1 text-amber-700 dark:text-amber-300">{t('unsaved')}</span>
      </div>
      <input aria-label={t('title')} placeholder={t('untitled')} value={title} onChange={event => setTitle(event.target.value)}
        className="mb-8 w-full border-0 bg-transparent px-2 text-4xl font-semibold tracking-tight outline-none placeholder:text-muted-foreground/45 sm:text-5xl" />
      <RichEditor />
    </section>
  )
}
