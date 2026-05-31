import { RoutePermissionGuard } from '@/components/auth/permission-guard'
import { Header } from '@/components/layout/header'
import { AdminWorkflowEditClient } from '../../../_components/admin-workflow-edit-client'

export default async function AdminWorkflowEditPage({
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
          <AdminWorkflowEditClient workflowId={id} />
        </div>
      </div>
    </RoutePermissionGuard>
  )
}
