import { RoutePermissionGuard } from '@/components/auth/permission-guard'
import { Header } from '@/components/layout/header'
import { UsersClient } from './_components'

export default function UsersPage() {
  return (
    <RoutePermissionGuard>
      <div className="flex h-full flex-col">
        <Header />
        <div className="flex flex-1 flex-col gap-4 overflow-auto p-4">
          <UsersClient />
        </div>
      </div>
    </RoutePermissionGuard>
  )
}
