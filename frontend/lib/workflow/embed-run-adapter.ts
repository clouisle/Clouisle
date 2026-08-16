import { embedApi } from '@/lib/api/embed'
import { mapEmbedWorkflow, type WorkflowRunAdapter, type RunSnapshot, type RunSnapshotNode } from '@/lib/workflow/run-adapter'
import type { WorkflowRunListItem, WorkflowRun, NodeExecution, RunStatus, NodeStatus, TriggerType } from '@/lib/api/workflows'
import type { WorkflowRunApi } from '@/hooks/use-workflow-run'

const MAX_RUNS = 20
const TRIGGER = 'manual' as TriggerType

interface StoredRun {
  runId: string
  status: string
  outputs: Record<string, unknown> | null
  nodes: RunSnapshotNode[]
  error?: string | null
  inputs?: Record<string, unknown> | null
  createdAt: string
  title: string
}

function storageKey(id: string) {
  return `clouisle:embed:runs:workflow:${id}`
}

function readRuns(id: string): StoredRun[] {
  try {
    const raw = localStorage.getItem(storageKey(id))
    return raw ? (JSON.parse(raw) as StoredRun[]) : []
  } catch {
    return []
  }
}

function writeRuns(id: string, runs: StoredRun[]) {
  try {
    localStorage.setItem(storageKey(id), JSON.stringify(runs))
  } catch {
    /* storage unavailable or full */
  }
}

function toListItem(s: StoredRun, workflowId: string): WorkflowRunListItem {
  return {
    id: s.runId,
    workflow_id: workflowId,
    trigger_type: TRIGGER,
    is_debug: false,
    status: s.status as RunStatus,
    created_at: s.createdAt,
    started_at: null,
    finished_at: null,
    total_duration_ms: null,
    executed_nodes: s.nodes.length,
    total_nodes: s.nodes.length,
    error_message: s.error ?? null,
  }
}

function toRun(s: StoredRun, workflowId: string): WorkflowRun {
  return {
    id: s.runId,
    workflow_id: workflowId,
    trigger_type: TRIGGER,
    triggered_by_id: null,
    is_debug: false,
    status: s.status as RunStatus,
    inputs: s.inputs ?? {},
    outputs: s.outputs,
    parent_run_id: null,
    root_run_id: null,
    depth: 0,
    created_at: s.createdAt,
    started_at: null,
    finished_at: null,
    total_nodes: s.nodes.length,
    executed_nodes: s.nodes.length,
    failed_nodes: 0,
    skipped_nodes: 0,
    total_duration_ms: null,
    total_token_usage: {},
    error_message: s.error ?? null,
    error_node_id: null,
  }
}

function toNodes(s: StoredRun): NodeExecution[] {
  return s.nodes.map((n, i) => ({
    id: `${s.runId}-${i}`,
    run_id: s.runId,
    node_id: '',
    node_type: n.nodeType,
    node_name: n.nodeType,
    execution_order: n.order,
    status: n.status as NodeStatus,
    outputs: n.outputs ?? null,
    retry_count: 0,
  }))
}

/**
 * Workflow run adapter backed by the API-key `embedApi` and browser-localStorage
 * history. Lets the embed page reuse `WorkflowRunPage` without a logged-in user:
 * runs go through the embed endpoints, and run history is persisted locally.
 */
export function createEmbedWorkflowRunAdapter(apiKey: string): WorkflowRunAdapter {
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
    loadHistory: async (id) => readRuns(id).map((s) => toListItem(s, id)),
    loadRunDetail: async (id, runId) => {
      const s = readRuns(id).find((r) => r.runId === runId)
      if (!s) throw new Error('run not found')
      return { run: toRun(s, id), nodes: toNodes(s) }
    },
    saveRun: (id, snapshot: RunSnapshot) => {
      const title = (snapshot.inputs?.query as string | undefined) || snapshot.runId
      const entry: StoredRun = {
        runId: snapshot.runId,
        status: snapshot.status,
        outputs: snapshot.outputs,
        nodes: snapshot.nodes,
        error: snapshot.error,
        inputs: snapshot.inputs,
        createdAt: snapshot.createdAt,
        title,
      }
      writeRuns(id, [entry, ...readRuns(id)].slice(0, MAX_RUNS))
    },
  }
}
