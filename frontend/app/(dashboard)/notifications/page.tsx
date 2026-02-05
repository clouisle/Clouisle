import { Header } from '@/components/layout/header'
import { NotificationsAdminClient } from './_components/notifications-admin-client'

export default function NotificationsAdminPage() {
  return (
    <div className="flex h-full flex-col">
      <Header />
      <div className="flex flex-1 flex-col gap-4 overflow-auto p-4">
        <NotificationsAdminClient />
      </div>
    </div>
  )
}
