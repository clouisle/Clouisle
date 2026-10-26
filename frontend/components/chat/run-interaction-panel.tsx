'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { Loader2, RefreshCw, ServerCog } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { InteractionRequestCard } from '@/components/tool-interactions'
import type { RunInteractionResponseInput } from '@/lib/api'
import { cn } from '@/lib/utils'
import { useRunInteractions } from '@/hooks/use-run-interactions'

export interface RunInteractionPanelProps {
  runId?: string | null
  /** Poll only while the run is active or waiting. */
  enabled?: boolean
  /** Re-read the owning run after a response so resumed events are applied. */
  onRefreshRun?: () => void | Promise<void>
  className?: string
}

/**
 * In-chat surface for MCP sampling/elicitation requests that arrive while the
 * original tool call is still running. There is no interaction SSE event, so
 * the durable pending list is polled while the run is open.
 */
export function RunInteractionPanel({
  runId,
  enabled = true,
  onRefreshRun,
  className,
}: RunInteractionPanelProps) {
  const t = useTranslations('approvals.chat')
  const tInteraction = useTranslations('approvals.interaction')
  const { interactions, isLoading, error, refresh, respond } = useRunInteractions({
    runId,
    enabled,
  })

  const handleRespond = async (
    interactionId: string,
    input: RunInteractionResponseInput
  ) => {
    const result = await respond(interactionId, input)
    if (result.outcome === 'accept') {
      toast.success(tInteraction('acceptedToast'))
    } else if (result.outcome === 'decline') {
      toast.success(tInteraction('declinedToast'))
    } else if (result.outcome === 'cancel') {
      toast.success(tInteraction('cancelledToast'))
    }
    try {
      await onRefreshRun?.()
    } catch {
      // The response is already durable; run replay can happen on reconnect.
    }
    return result
  }

  if (!runId || (!isLoading && !error && interactions.length === 0)) return null

  return (
    <div
      className={cn('mx-auto w-[70%] space-y-2 px-4', className)}
      data-testid="run-interaction-panel"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex min-w-0 items-start gap-2">
          <ServerCog className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
          <div>
            <p className="text-sm font-medium">{t('interactionTitle')}</p>
            <p className="text-xs text-muted-foreground">{t('interactionDescription')}</p>
          </div>
        </div>
        <Button
          size="sm"
          variant="ghost"
          onClick={() => void refresh()}
          disabled={isLoading}
          title={t('interactionRefresh')}
        >
          <RefreshCw className={cn('h-3.5 w-3.5', isLoading && 'animate-spin')} />
        </Button>
      </div>

      {error && (
        <div className="flex items-center gap-2 text-xs text-destructive">
          <span>{t('interactionRefreshFailed')}</span>
          <Button size="xs" variant="ghost" onClick={() => void refresh()}>
            {tInteraction('retry')}
          </Button>
        </div>
      )}

      {isLoading && interactions.length === 0 && (
        <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
          {tInteraction('loading')}
        </p>
      )}

      {interactions.map((interaction) => (
        <InteractionRequestCard
          key={interaction.id}
          interaction={interaction}
          onRespond={handleRespond}
          compact
        />
      ))}
    </div>
  )
}
