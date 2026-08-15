import type { VariableDefinition } from '@/lib/api/agents'
import type { VariableDefinition as WorkflowVariableDefinition } from '@/lib/api/workflows'

export type RunVariableDefinition = Omit<VariableDefinition, 'type' | 'default'> & {
  type: VariableDefinition['type'] | 'boolean'
  default?: unknown
}

type WorkflowStartParameter = {
  name: string
  type?: string
  required?: boolean
  default?: unknown
  description?: string
  label?: string
  options?: string[]
  fileConfig?: { maxSize?: number; accept?: string[]; maxFiles?: number }
}

function normalizeVariableType(type?: string): RunVariableDefinition['type'] {
  if (type === 'string') return 'text'
  if (type === 'boolean') return 'boolean'
  return (type as RunVariableDefinition['type']) || 'text'
}

/**
 * Extract variable definitions from Agent or Workflow metadata
 */
export function extractVariables(
  metadata: unknown,
  type: 'agent' | 'workflow'
): RunVariableDefinition[] {
  if (!metadata || typeof metadata !== 'object') return []

  if (type === 'agent') {
    const agent = metadata as { variables?: VariableDefinition[] }
    return agent.variables || []
  } else {
    // Extract from workflow's start node (user_input or trigger)
    const workflow = metadata as {
      variables?: WorkflowVariableDefinition[]
      definition?: {
        nodes?: Array<{
          data?: {
            type?: string
            parameters?: Array<WorkflowStartParameter>
            config?: {
              parameters?: Array<WorkflowStartParameter>
            }
          }
        }>
      }
    }

    // First try to get from workflow.variables
    if (workflow.variables && workflow.variables.length > 0) {
      return workflow.variables.map((v) => ({
        ...v,
        type: normalizeVariableType(v.type),
        required: v.required ?? true,
        default: v.default ?? null,
        label: v.label || v.name,
      }))
    }

    // Otherwise extract from start node (user_input stores parameters on data)
    const nodes = workflow.definition?.nodes || []
    const startNode = nodes.find(
      (n) => n.data?.type === 'user_input' || n.data?.type === 'trigger'
    )

    const params = startNode?.data?.config?.parameters || startNode?.data?.parameters || []

    return params.map((p) => ({
      name: p.name,
      type: normalizeVariableType(p.type),
      required: p.required ?? true,
      default: p.default ?? null,
      description: p.description || null,
      label: p.label || p.name,
      options: p.options,
      fileConfig: p.fileConfig,
    }))
  }
}
