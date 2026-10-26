'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { Loader2, RefreshCw, ServerCog } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { InteractionRequestCard } from '@/components/tool-interactions'
import {
  runInteractionsApi,
  type RunInteraction,
  type RunInteractionResponseInput,
} from '@/lib/api'

export interface InteractionsInboxProps {
  refreshKey?: number
}

const PAGE_SIZE = 20

/**
 * Durable list of MCP sampling/elicitation requests addressed to the current
 * user. Responding authorizes only that request; the enclosing tool execution
 * keeps its own approval decision.
 */
export function InteractionsInbox({ refreshKey = 0 }: InteractionsInboxProps) {
  const t = useTranslations('approvals.interaction')
  const tRef = React.useRef(t)
  tRef.current = t
  const [page, setPage] = React.useState(1)
  const [interactions, setInteractions] = React.useState<RunInteraction[]>([])
  const [total, setTotal] = React.useState(0)
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)

  const load = React.useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await runInteractionsApi.list({
        page,
        page_size: PAGE_SIZE,
        status: 'pending',
      })
      setInteractions(response.items)
      setTotal(response.total)
    } catch (reason) {
      setError(reason instanceof Error && reason.message ? reason.message : tRef.current('loadFailed'))
      setInteractions([])
      setTotal(0)
    } finally {
      setLoading(false)
    }
  }, [page])

  React.useEffect(() => {
    void load()
  }, [load, refreshKey])

  const handleRespond = async (
    interactionId: string,
    input: RunInteractionResponseInput
  ) => {
    const result = await runInteractionsApi.respond(interactionId, input)
    if (result.outcome === 'accept') toast.success(t('acceptedToast'))
    else if (result.outcome === 'decline') toast.success(t('declinedToast'))
    else if (result.outcome === 'cancel') toast.success(t('cancelledToast'))
    await load()
    return result
  }

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  if (loading && interactions.length === 0) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-7 w-7 animate-spin text-muted-foreground" />
        <span className="ml-2 text-sm text-muted-foreground">{t('loading')}</span>
      </div>
    )
  }

  if (error) {
    return (
      <Card>
        <CardContent className="flex flex-col items-center gap-3 py-10">
          <p className="text-sm text-destructive">{error}</p>
          <Button variant="outline" onClick={() => void load()}>
            <RefreshCw className="mr-2 h-4 w-4" />
            {t('retry')}
          </Button>
        </CardContent>
      </Card>
    )
  }

  if (interactions.length === 0) {
    return (
      <Card>
        <CardContent className="flex flex-col items-center justify-center gap-2 py-12">
          <ServerCog className="h-10 w-10 text-muted-foreground" />
          <p className="font-medium">{t('empty')}</p>
          <p className="text-sm text-muted-foreground">{t('emptyHint')}</p>
        </CardContent>
      </Card>
    )
  }

  return (
    <div className="space-y-3" data-testid="interactions-inbox">
      <div>
        <h2 className="text-lg font-semibold">{t('listTitle')}</h2>
        <p className="text-sm text-muted-foreground">{t('listDescription')}</p>
      </div>

      {interactions.map((interaction) => (
        <InteractionRequestCard
          key={interaction.id}
          interaction={interaction}
          onRespond={handleRespond}
        />
      ))}

      {totalPages > 1 && (
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span>{t('pageInfo', { page, totalPages })}</span>
          <div className="flex gap-2">
            <Button
              size="sm"
              variant="outline"
              disabled={page <= 1 || loading}
              onClick={() => setPage((current) => Math.max(1, current - 1))}
            >
              {t('previous')}
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={page >= totalPages || loading}
              onClick={() => setPage((current) => current + 1)}
            >
              {t('next')}
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}
