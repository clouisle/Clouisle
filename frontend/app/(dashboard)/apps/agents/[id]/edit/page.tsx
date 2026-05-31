import { RoutePermissionGuard } from '@/components/auth/permission-guard'
import { Header } from '@/components/layout/header'
import { AdminAgentEditClient } from '../../../_components/admin-agent-edit-client'

export default async function AdminAgentEditPage({
  params,
}: {
  params: Promise<{ id: string }>
}) {
  const { id } = await params

  return (
    <RoutePermissionGuard>
      <div className="flex h-full flex-col">
        <Header />
        <div className="flex-1 overflow-auto p-4">
          <AdminAgentEditClient agentId={id} />
        </div>
      </div>
    </RoutePermissionGuard>
  )
}
