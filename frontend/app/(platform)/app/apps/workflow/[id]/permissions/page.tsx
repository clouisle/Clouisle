'use client'

import * as React from 'react'
import { useParams, useRouter } from 'next/navigation'
import { useLocale, useTranslations } from 'next-intl'
import { useTeam } from '@/contexts/team-context'
import { usePermissions } from '@/hooks/use-permissions'
import { ArrowLeft, Activity, ExternalLink, FileText, LayoutGrid, Loader2, ShieldCheck } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { workflowsApi, type Workflow } from '@/lib/api/workflows'
import { AccessPolicyEditor } from '../_components/access-policy-editor'

export default function WorkflowPermissionsPage() {
  const params = useParams()
  const router = useRouter()
  const t = useTranslations('workflow')
  const locale = useLocale()
  const { currentTeam } = useTeam()
  const { user } = usePermissions()
  const [workflow, setWorkflow] = React.useState<Workflow | null>(null)
  const [loading, setLoading] = React.useState(true)
  const workflowId = params.id as string

  const isWorkflowOwner = Boolean(user?.id && workflow?.created_by_id === user.id)
  const isWorkflowTeamAdmin = Boolean(
    workflow && currentTeam?.id === workflow.team_id && (currentTeam.role === 'owner' || currentTeam.role === 'admin'),
  )
  const canEdit = Boolean(user?.is_superuser || isWorkflowTeamAdmin || isWorkflowOwner)

  React.useEffect(() => {
    let live = true
    workflowsApi
      .getWorkflow(workflowId)
      .then((data) => { if (live) setWorkflow(data) })
      .catch(() => { if (live) setWorkflow(null) })
      .finally(() => { if (live) setLoading(false) })
    return () => { live = false }
  }, [workflowId])

  const nav = (path: string) => router.push(`/app/apps/workflow/${workflowId}${path}`)

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (!workflow) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="text-center">
          <p className="text-muted-foreground">{t('workflowNotFound')}</p>
          <Button variant="outline" className="mt-4" onClick={() => router.push('/app/apps/workflow')}>
            <ArrowLeft className="mr-2 h-4 w-4" />
            {t('backToWorkflows')}
          </Button>
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-svh flex-col">
      <div className="absolute left-4 top-4 z-50 flex items-center gap-2">
        <Button variant="ghost" size="icon" className="h-9 w-9 bg-card shadow-sm" onClick={() => router.push('/app/apps')}>
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <DropdownMenu>
          <DropdownMenuTrigger className="inline-flex h-9 items-center gap-2 rounded-md border border-input bg-card px-2 text-sm font-medium shadow-sm">
            <span className="max-w-32 truncate">{workflow.name}</span>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="w-48">
            <DropdownMenuItem className="gap-2" onClick={() => nav('')}>
              <LayoutGrid className="h-4 w-4" />
              <span>{t('orchestrate')}</span>
            </DropdownMenuItem>
            <DropdownMenuItem className="gap-2" onClick={() => nav('/api')}>
              <ExternalLink className="h-4 w-4" />
              <span>{t('accessApi')}</span>
            </DropdownMenuItem>
            <DropdownMenuItem className="gap-2" onClick={() => nav('/logs')}>
              <FileText className="h-4 w-4" />
              <span>{t('logs')}</span>
            </DropdownMenuItem>
            {canEdit && (
              <DropdownMenuItem className="gap-2" onClick={() => nav('/monitor')}>
                <Activity className="h-4 w-4" />
                <span>{t('monitor')}</span>
              </DropdownMenuItem>
            )}
            <DropdownMenuItem className="gap-2 bg-primary/10 text-primary">
              <ShieldCheck className="h-4 w-4" />
              <span>{t('permissions')}</span>
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      <div className="flex-1 overflow-auto pt-20">
        <div className="mx-auto w-full max-w-3xl space-y-6 px-4 pb-12">
          <h1 className="text-lg font-semibold">{t('permissions')}</h1>
          <AccessPolicyEditor
            key={locale}
            workflowId={workflowId}
            teamId={workflow.team_id ?? null}
            readOnly={!canEdit}
          />
        </div>
      </div>
    </div>
  )
}
