import { RoutePermissionGuard } from '@/components/auth/permission-guard'
import { Header } from '@/components/layout/header'
import { ModelsClient } from './_components'

export default function ModelsPage() {
  return (
    <RoutePermissionGuard>
      <div className="flex h-full flex-col">
        <Header />
        <div className="flex flex-1 flex-col gap-4 overflow-auto p-4">
          <ModelsClient />
        </div>
      </div>
    </RoutePermissionGuard>
  )
}
