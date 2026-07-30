'use client'

import { adminKnowledgeBasesApi } from '@/lib/api/knowledge-bases'
import { RetrievalLab } from '@/components/knowledge-bases/retrieval-lab'
import { usePermissions } from '@/hooks/use-permissions'
import { useRouter } from 'next/navigation'

export function SearchTestClient({ knowledgeBaseId }: { knowledgeBaseId: string }) {
  const { hasPermission } = usePermissions()
  const { push } = useRouter()
  return (
    <RetrievalLab
      knowledgeBaseId={knowledgeBaseId}
      api={adminKnowledgeBasesApi}
      backHref={`/knowledge-bases/${knowledgeBaseId}`}
      canUpdate={hasPermission('admin:knowledge-base:update')}
      canTest={hasPermission('admin:knowledge-base:test')}
      onLoadError={() => push('/knowledge-bases')}
    />
  )
}
