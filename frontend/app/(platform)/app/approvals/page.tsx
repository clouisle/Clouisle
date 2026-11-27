'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { Check, ShieldCheck, X } from 'lucide-react'
import { toast } from 'sonner'
import { toolApprovalsApi, type ToolApprovalRequest } from '@/lib/api'
import { formatDateTime } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'

/**
 * Pending tool-approval inbox.
 *
 * An Agent chat shows its own approval card, but a workflow run parks in the
 * background with no open conversation. This page is where a workflow run's
 * initiator — or a team owner/admin as fallback — decides the gate so the run
 * can continue.
 */
export default function ApprovalsPage() {
  const t = useTranslations('approvals.approval')
  const entrypointLabels: Record<string, string> = {
    chat: t('entrypoints.chat'),
    agent_run: t('entrypoints.agent_run'),
    workflow: t('entrypoints.workflow'),
    api_key: t('entrypoints.api_key'),
    schedule: t('entrypoints.schedule'),
    channel: t('entrypoints.channel'),
    feishu_channel: t('entrypoints.feishu_channel'),
    wechat_channel: t('entrypoints.wechat_channel'),
    embed: t('entrypoints.embed'),
    subworkflow: t('entrypoints.subworkflow'),
    nested_agent: t('entrypoints.nested_agent'),
    tool_test: t('entrypoints.tool_test'),
    admin_test: t('entrypoints.admin_test'),
  }
  const gateKindLabels: Record<string, string> = {
    caller: t('gateKinds.caller'),
    user: t('gateKinds.user'),
    team_role: t('gateKinds.team_role'),
  }
  const runKindLabels: Record<string, string> = {
    agent: t('runKinds.agent'),
    workflow: t('runKinds.workflow'),
  }
  const [requests, setRequests] = React.useState<ToolApprovalRequest[]>([])
  const [isLoading, setIsLoading] = React.useState(true)
  const [loadError, setLoadError] = React.useState(false)
  const [decidingId, setDecidingId] = React.useState<string | null>(null)

  const load = React.useCallback(async () => {
    setIsLoading(true)
    setLoadError(false)
    try {
      const page = await toolApprovalsApi.list({ page: 1, page_size: 50 })
      setRequests(page.items)
    } catch {
      setLoadError(true)
    } finally {
      setIsLoading(false)
    }
  }, [])

  React.useEffect(() => {
    void load()
  }, [load])

  const decide = async (
    request: ToolApprovalRequest,
    decision: 'approve' | 'reject'
  ) => {
    setDecidingId(request.id)
    try {
      await toolApprovalsApi.decide(request.id, {
        decision,
        idempotency_key: `${request.id}:${decision}`,
      })
      // The decision resumes the owning run in the background, so drop the row
      // locally instead of re-reading the whole inbox.
      setRequests((current) => current.filter((item) => item.id !== request.id))
      toast.success(
        decision === 'approve' ? t('approvedToast') : t('rejectedToast')
      )
    } catch {
      toast.error(t('decisionFailed'))
    } finally {
      setDecidingId(null)
    }
  }

  return (
    <div className="flex h-full flex-col gap-4 p-4 md:p-6">
      <div className="flex items-center gap-2">
        <ShieldCheck className="h-5 w-5 text-muted-foreground" />
        <h1 className="text-lg font-semibold">{t('listTitle')}</h1>
      </div>
      <p className="text-sm text-muted-foreground">{t('listDescription')}</p>

      {isLoading ? (
        <div className="flex flex-col gap-2" aria-busy="true">
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-24 w-full" />
        </div>
      ) : loadError ? (
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-8">
            <p className="text-sm text-muted-foreground">{t('loadFailed')}</p>
            <Button variant="outline" onClick={() => void load()}>
              {t('retry')}
            </Button>
          </CardContent>
        </Card>
      ) : requests.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center gap-1 py-8 text-center">
            <p className="text-sm font-medium">{t('empty')}</p>
            <p className="text-xs text-muted-foreground">{t('emptyHint')}</p>
          </CardContent>
        </Card>
      ) : (
        <div className="flex flex-col gap-3">
          {requests.map((request) => {
            const display = request.masked_display ?? {}
            const parameters = display.parameters ?? {}
            return (
              <Card key={request.id}>
                <CardHeader className="pb-2">
                  <CardTitle className="flex flex-wrap items-center gap-2 text-base">
                    <span>
                      {display.tool_name || display.tool_id || t('tool')}
                    </span>
                    {display.operation ? (
                      <code className="text-xs text-muted-foreground">
                        {display.operation}
                      </code>
                    ) : null}
                    {display.entrypoint ? (
                      <Badge variant="secondary">
                        {entrypointLabels[display.entrypoint] ?? display.entrypoint}
                      </Badge>
                    ) : null}
                    {display.run_kind && runKindLabels[display.run_kind] ? (
                      <span className="text-xs text-muted-foreground">
                        {runKindLabels[display.run_kind]}
                      </span>
                    ) : null}
                  </CardTitle>
                </CardHeader>
                <CardContent className="flex flex-col gap-3">
                  <div className="text-xs text-muted-foreground">
                    {t('gateKind')}:{' '}
                    {gateKindLabels[request.gate_kind] ?? request.gate_kind}
                    {request.expires_at
                      ? ` · ${t('expiresAt', {
                          time: formatDateTime(request.expires_at),
                        })}`
                      : ''}
                  </div>
                  {Object.keys(parameters).length > 0 ? (
                    <div className="flex flex-col gap-1">
                      <span className="text-xs font-medium">
                        {t('parameters')}
                      </span>
                      <pre className="max-h-40 overflow-auto rounded bg-muted p-2 text-xs">
                        {JSON.stringify(parameters, null, 2)}
                      </pre>
                    </div>
                  ) : (
                    <p className="text-xs text-muted-foreground">
                      {t('noParameters')}
                    </p>
                  )}
                  <div className="flex justify-end gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={decidingId === request.id}
                      onClick={() => void decide(request, 'reject')}
                    >
                      <X className="mr-1 h-4 w-4" />
                      {t('reject')}
                    </Button>
                    <Button
                      size="sm"
                      disabled={decidingId === request.id}
                      onClick={() => void decide(request, 'approve')}
                    >
                      <Check className="mr-1 h-4 w-4" />
                      {t('approve')}
                    </Button>
                  </div>
                </CardContent>
              </Card>
            )
          })}
        </div>
      )}
    </div>
  )
}
