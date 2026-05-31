'use client'

import { ReactFlowProvider } from '@xyflow/react'
import { adminWorkflowsApi } from '@/lib/api/admin'
import type { WorkflowUpdateInput } from '@/lib/api/workflows'
import { WorkflowEditorContent } from '@/app/(platform)/app/apps/workflow/[id]/page'

export function AdminWorkflowEditClient({ workflowId }: { workflowId: string }) {
  return (
    <ReactFlowProvider>
      <WorkflowEditorContent
        workflowId={workflowId}
        api={{
          getWorkflow: adminWorkflowsApi.getById,
          updateWorkflow: (id: string, data: WorkflowUpdateInput) => adminWorkflowsApi.update(id, data),
          publishWorkflow: adminWorkflowsApi.publish,
          unpublishWorkflow: adminWorkflowsApi.unpublish,
        }}
        backHref="/apps?tab=workflows"
        updatePermission="admin:app:update"
      />
    </ReactFlowProvider>
  )
}
