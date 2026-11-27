import { embedApi } from '@/lib/api/embed'
import { mapEmbedWorkflow, type WorkflowRunAdapter } from '@/lib/workflow/run-adapter'
import { purgeLegacyEmbedHistory } from '@/lib/embed/legacy-history-cache'
import type { WorkflowRunApi } from '@/hooks/use-workflow-run'

/** Page size used by the single-shot history read the page falls back to. */
const HISTORY_PAGE_SIZE = 20

/**
 * Workflow run adapter for the embed page.
 *
 * Run history is the server's: it is read from the API-key scoped run routes,
 * which return exactly the runs that key created. Nothing is persisted in the
 * browser - `localStorage` is readable by every script on the origin - and the
 * cache left by earlier releases is purged when the adapter is created.
 */
export function createEmbedWorkflowRunAdapter(apiKey: string): WorkflowRunAdapter {
  purgeLegacyEmbedHistory()

  return {
    getWorkflow: async (id) => mapEmbedWorkflow(await embedApi.getWorkflowInfo(id, apiKey)),
    createRunApi: (): WorkflowRunApi => ({
      runWorkflow: (id, body) => embedApi.runWorkflow(id, body.inputs, apiKey),
      streamWorkflowRun: (runId, handlers) =>
        embedApi.streamWorkflowRun(runId, apiKey, {
          fromSequence: handlers.fromSequence,
          onEvent: handlers.onEvent as ((event: { type: string; data: Record<string, unknown>; sequence: number; timestamp: string }) => void) | undefined,
          onError: handlers.onError,
          onComplete: handlers.onComplete,
        }),
      cancelWorkflowRun: async () => {
        // Embed streams are closed via the SSE connection; there is no server-side cancel endpoint.
      },
    }),
    loadHistory: (id) =>
      embedApi.getWorkflowRuns(id, apiKey, { pageSize: HISTORY_PAGE_SIZE }).then((page) => page.items),
    loadHistoryPage: (id, params) => embedApi
      .getWorkflowRuns(id, apiKey, { page: params.page, pageSize: params.pageSize })
      .then((page) => ({ items: page.items, total: page.total })),
    loadRunDetail: async (id, runId) => {
      const [run, nodes] = await Promise.all([
        embedApi.getWorkflowRun(id, runId, apiKey),
        embedApi.getWorkflowRunNodes(id, runId, apiKey),
      ])
      return { run, nodes }
    },
    saveRun: () => {
      // History is stored server-side with the run itself; nothing to persist.
    },
  }
}
