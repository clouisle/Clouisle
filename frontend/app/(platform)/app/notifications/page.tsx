import { NotificationsClient } from './_components/notifications-client'

export default function NotificationsPage() {
  return (
    <div className="flex flex-col" style={{ height: 'calc(100vh - 64px)' }}>
      <div className="flex-1 min-h-0 overflow-auto p-6">
        <NotificationsClient />
      </div>
    </div>
  )
}
