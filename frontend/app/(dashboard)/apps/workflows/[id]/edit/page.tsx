import { RoutePermissionGuard } from '@/components/auth/permission-guard'
import { Header } from '@/components/layout/header'
import { AdminWorkflowEditClient } from '../../../_components/admin-workflow-edit-client'
import { AdminAppEditProviders } from '../../../_components/admin-app-edit-providers'

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
        <div className="flex-1 overflow-hidden">
          <AdminAppEditProviders>
            <AdminWorkflowEditClient workflowId={id} />
          </AdminAppEditProviders>
        </div>
      </div>
    </RoutePermissionGuard>
  )
}
