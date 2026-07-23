'use client'

import { adminKnowledgeBasesApi } from '@/lib/api/knowledge-bases'
import { RetrievalLab } from '@/components/knowledge-bases/retrieval-lab'
import { usePermissions } from '@/hooks/use-permissions'
import { useRouter } from 'next/navigation'

export function SearchTestClient({ knowledgeBaseId }: { knowledgeBaseId: string }) {
  const { hasPermission } = usePermissions()
  const router = useRouter()
  return (
    <RetrievalLab
      knowledgeBaseId={knowledgeBaseId}
      api={adminKnowledgeBasesApi}
      backHref={`/knowledge-bases/${knowledgeBaseId}`}
      canUpdate={hasPermission('admin:knowledge-base:update')}
      onLoadError={() => router.push('/knowledge-bases')}
    />
  )
}
