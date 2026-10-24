import { Metadata } from 'next'
import { getTranslations } from 'next-intl/server'
import { RoutePermissionGuard } from '@/components/auth/permission-guard'
import { Header } from '@/components/layout/header'
import { DeliveryLogClient } from './_components/delivery-log-client'

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations('deliveryLog')
  return {
    title: t('title'),
    description: t('description'),
  }
}

export default function DeliveriesPage() {
  return (
    <RoutePermissionGuard>
      <div className="flex h-full flex-col">
        <Header />
        <div className="flex flex-1 flex-col gap-4 overflow-auto p-4">
          <DeliveryLogClient />
        </div>
      </div>
    </RoutePermissionGuard>
  )
}
