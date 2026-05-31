'use client'

import { adminAgentsApi } from '@/lib/api/admin'
import type { AgentUpdateInput } from '@/lib/api/agents'
import { AgentEditor } from '@/app/(platform)/app/apps/[id]/page'

export function AdminAgentEditClient({ agentId }: { agentId: string }) {
  return (
    <AgentEditor
      agentId={agentId}
      api={{
        getAgent: adminAgentsApi.getById,
        updateAgent: (id: string, data: AgentUpdateInput) => adminAgentsApi.update(id, data),
        publishAgent: adminAgentsApi.publish,
        unpublishAgent: adminAgentsApi.unpublish,
      }}
      backHref="/apps"
      updatePermission="admin:app:update"
      baseUrl={`/apps/agents/${agentId}/edit`}
    />
  )
}
