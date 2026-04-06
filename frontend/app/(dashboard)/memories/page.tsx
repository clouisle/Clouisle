import { RoutePermissionGuard } from '@/components/auth/permission-guard'
import { Header } from '@/components/layout/header'
import { MemoriesClient } from './_components'

export default function MemoriesPage() {
  return (
    <RoutePermissionGuard>
      <div className="flex h-full flex-col">
        <Header />
        <div className="flex flex-1 flex-col gap-4 overflow-auto p-4">
          <MemoriesClient />
        </div>
      </div>
    </RoutePermissionGuard>
  )
}
