'use client'

import * as React from 'react'
import {
  runInteractionsApi,
  type RunInteraction,
  type RunInteractionResponseInput,
} from '@/lib/api'

export interface UseRunInteractionsOptions {
  /** Durable run whose pending MCP interactions should be shown. */
  runId?: string | null
  /** Poll only while the run can still receive a response. */
  enabled?: boolean
  /** Durable pending list poll interval. */
  pollIntervalMs?: number
  pageSize?: number
}

export interface UseRunInteractionsReturn {
  interactions: RunInteraction[]
  isLoading: boolean
  error: Error | null
  refresh: () => Promise<void>
  respond: (interactionId: string, input: RunInteractionResponseInput) => Promise<RunInteraction>
}

/**
 * Load and poll MCP interactions for one run.
 *
 * The backend publishes no interaction SSE events, so the durable pending list
 * is the source of truth. Polling is disabled when the run is closed. Errors
 * are silent by design: a missing or unauthorized interaction list must not
 * break the surrounding chat surface.
 */
export function useRunInteractions({
  runId,
  enabled = true,
  pollIntervalMs = 5000,
  pageSize = 50,
}: UseRunInteractionsOptions = {}): UseRunInteractionsReturn {
  const [interactions, setInteractions] = React.useState<RunInteraction[]>([])
  const [isLoading, setIsLoading] = React.useState(false)
  const [error, setError] = React.useState<Error | null>(null)
  const generationRef = React.useRef(0)

  const refresh = React.useCallback(async () => {
    // Invalidate any in-flight request first: closing the run must also
    // discard a response that is already on the wire.
    const generation = ++generationRef.current
    // The interaction API is JWT-only. Anonymous public chat must never be
    // redirected to login just because a run is open.
    const hasAuthToken = typeof window !== 'undefined'
      && Boolean(window.localStorage.getItem('access_token'))
    if (!runId || !enabled || !hasAuthToken) {
      setInteractions([])
      setError(null)
      setIsLoading(false)
      return
    }

    setIsLoading(true)
    try {
      const data = await runInteractionsApi.list(
        { run_id: runId, status: 'pending', page: 1, page_size: pageSize },
        { silent: true }
      )
      if (generation !== generationRef.current) return
      setInteractions(data.items)
      setError(null)
    } catch (reason) {
      if (generation !== generationRef.current) return
      setInteractions([])
      setError(reason instanceof Error ? reason : new Error(String(reason)))
    } finally {
      if (generation === generationRef.current) setIsLoading(false)
    }
  }, [enabled, pageSize, runId])

  React.useEffect(() => {
    void refresh()
  }, [refresh])

  React.useEffect(() => {
    if (!runId || !enabled) return
    const timer = setInterval(() => {
      void refresh()
    }, pollIntervalMs)
    return () => clearInterval(timer)
  }, [enabled, pollIntervalMs, refresh, runId])

  const respond = React.useCallback(
    async (interactionId: string, input: RunInteractionResponseInput) => {
      const result = await runInteractionsApi.respond(interactionId, input)
      await refresh()
      return result
    },
    [refresh]
  )

  return { interactions, isLoading, error, refresh, respond }
}
