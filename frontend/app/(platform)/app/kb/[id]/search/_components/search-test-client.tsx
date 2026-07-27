'use client'

import { knowledgeBasesApi } from '@/lib/api/knowledge-bases'
import { RetrievalLab } from '@/components/knowledge-bases/retrieval-lab'
import { usePermissions } from '@/hooks/use-permissions'
import { useRouter } from 'next/navigation'

export function SearchTestClient({ knowledgeBaseId }: { knowledgeBaseId: string }) {
  const { hasPermission } = usePermissions()
  const router = useRouter()
  return (
    <RetrievalLab
      knowledgeBaseId={knowledgeBaseId}
      api={knowledgeBasesApi}
      backHref={`/app/kb/${knowledgeBaseId}`}
      canUpdate={hasPermission('kb:update')}
      onLoadError={() => router.push('/app/kb')}
      authenticatedMarkdown
    />
  )
}
