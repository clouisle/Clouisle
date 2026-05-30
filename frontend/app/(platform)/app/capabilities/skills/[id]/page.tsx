'use client'

import { use } from 'react'
import { useRouter } from 'next/navigation'
import { SkillDetailClient } from '@/components/skill-detail-client'
import { useTeam } from '@/contexts/team-context'

export default function PlatformSkillDetailPage({
  params,
}: {
  params: Promise<{ id: string }>
}) {
  const { id } = use(params)
  const router = useRouter()
  const { currentTeam, isLoading } = useTeam()

  if (!isLoading && !currentTeam?.id) {
    router.push('/app/capabilities?tab=skills')
  }

  return (
    <div className="h-full overflow-auto px-8 py-6">
      <SkillDetailClient
        skillId={id}
        mode="platform"
        backHref="/app/capabilities?tab=skills"
        teamId={currentTeam?.id}
      />
    </div>
  )
}
