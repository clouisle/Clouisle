import { Header } from '@/components/layout/header'
import { SkillDetailClient } from '@/components/skill-detail-client'

export default async function AdminSkillDetailPage({
  params,
}: {
  params: Promise<{ id: string }>
}) {
  const { id } = await params

  return (
    <div className="flex h-full flex-col">
      <Header />
      <div className="flex-1 overflow-auto p-4">
        <SkillDetailClient skillId={id} mode="admin" backHref="/capabilities?tab=skills" />
      </div>
    </div>
  )
}
