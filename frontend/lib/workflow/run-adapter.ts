import { workflowsApi, type Workflow, type WorkflowRunListItem, type WorkflowRun, type WorkflowPauseRequest, type NodeExecution, type VariableDefinition } from '@/lib/api/workflows'
import type { EmbedWorkflowInfo } from '@/lib/api/embed'
import type { WorkflowRunApi } from '@/hooks/use-workflow-run'

export interface RunSnapshotNode {
  nodeType: string
  outputs?: Record<string, unknown> | null
  order: number
  status: string
}
export interface RunSnapshot {
  runId: string
  status: string
  outputs: Record<string, unknown> | null
  nodes: RunSnapshotNode[]
  error?: string | null
  inputs?: Record<string, unknown> | null
  createdAt: string
}

export interface RunDetail {
  run: WorkflowRun
  nodes: NodeExecution[]
}

/**
 * Pluggable data layer for the workflow run page. The default (`jwtWorkflowRunAdapter`)
 * talks to the authenticated `workflowsApi`; embeds pass an adapter backed by the
 * API-key `embedApi` plus browser-local history so the same page component can be
 * reused without a logged-in user.
 */
export interface WorkflowRunAdapter {
  getWorkflow: (id: string) => Promise<Workflow>
  createRunApi: () => WorkflowRunApi
  loadHistory: (id: string) => Promise<WorkflowRunListItem[]>
  /**
   * Paginated history for scroll-loading. When absent the run page falls back
   * to the single `loadHistory` call and shows no load-more.
   */
  loadHistoryPage?: (
    id: string,
    params: { page: number; pageSize: number }
  ) => Promise<{ items: WorkflowRunListItem[]; total: number }>
  loadRunDetail: (id: string, runId: string) => Promise<RunDetail>
  getPendingPauseRequest?: (workflowId: string, runId: string) => Promise<WorkflowPauseRequest | null>
  submitPauseRequest?: (
    workflowId: string,
    runId: string,
    pauseRequestId: string,
    values: Record<string, unknown>,
    comment?: string,
  ) => Promise<{ pause_request_id: string; status: string }>
  saveRun: (id: string, snapshot: RunSnapshot) => void
}

/** Map the minimal embed workflow info onto the full Workflow shape the run page expects. */
export function mapEmbedWorkflow(info: EmbedWorkflowInfo): Workflow {
  return {
    id: info.id,
    team_id: '',
    name: info.name,
    description: info.description,
    icon: info.icon,
    definition: { nodes: [], edges: [], viewport: { x: 0, y: 0, zoom: 1 } },
    variables: info.variables as unknown as VariableDefinition[],
    status: 'published',
    visibility: 'public',
    version: 1,
    trigger_type: 'manual',
    trigger_config: {},
    run_count: 0,
    success_count: 0,
    fail_count: 0,
    created_by_id: '',
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    embed_config: info.embed_config,
    run_page_config: { presentation_mode: 'simple' },
  }
}

export const jwtWorkflowRunAdapter: WorkflowRunAdapter = {
  getWorkflow: (id) => workflowsApi.getWorkflow(id),
  createRunApi: () => ({
    runWorkflow: (id, body) => workflowsApi.runWorkflow(id, body),
    streamWorkflowRun: (runId, handlers) => workflowsApi.streamWorkflowRun(runId, handlers),
    cancelWorkflowRun: async (runId) => { await workflowsApi.cancelWorkflowRun(runId) },
  }),
  loadHistory: (id) => workflowsApi.getMyWorkflowRuns(id, { pageSize: 20 }).then((d) => d.items),
  loadHistoryPage: (id, params) => workflowsApi
    .getMyWorkflowRuns(id, { page: params.page, pageSize: params.pageSize })
    .then((d) => ({ items: d.items, total: d.total })),
  loadRunDetail: async (id, runId) => {
    const [run, nodes] = await Promise.all([
      workflowsApi.getMyWorkflowRun(id, runId),
      workflowsApi.getMyRunNodeExecutions(id, runId),
    ])
    return { run, nodes }
  },
  getPendingPauseRequest: (workflowId, runId) => workflowsApi.getPendingPauseRequest(workflowId, runId),
  submitPauseRequest: async (workflowId, runId, pauseRequestId, values, comment) =>
    workflowsApi.submitPauseRequest(workflowId, runId, pauseRequestId, values, comment),
  saveRun: () => {
    // The authenticated run page relies on server-side history; nothing to persist locally.
  },
}
