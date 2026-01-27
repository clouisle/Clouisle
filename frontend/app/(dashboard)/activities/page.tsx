import { Metadata } from 'next'
import { getTranslations } from 'next-intl/server'
import { Header } from '@/components/layout/header'
import { ActivitiesClient } from './_components/activities-client'

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations('activities')
  return {
    title: t('title'),
    description: t('description'),
  }
}

export default function ActivitiesPage() {
  return (
    <div className="flex h-full flex-col">
      <Header />
      <div className="flex flex-1 flex-col gap-4 overflow-auto p-4">
        <ActivitiesClient />
      </div>
    </div>
  )
}
