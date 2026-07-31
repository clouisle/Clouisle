import type { VariableDefinition } from '@/lib/api/agents'
import type { VariableDefinition as WorkflowVariableDefinition } from '@/lib/api/workflows'

export type RunVariableDefinition = Omit<VariableDefinition, 'type' | 'default'> & {
  type: VariableDefinition['type'] | 'boolean'
  default?: unknown
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
            config?: {
              parameters?: Array<{
                name: string
                type?: string
                required?: boolean
                default?: unknown
                description?: string
                label?: string
              }>
            }
          }
        }>
      }
    }

    // First try to get from workflow.variables
    if (workflow.variables && workflow.variables.length > 0) {
      return workflow.variables.map((v) => ({
        name: v.name,
        type: normalizeVariableType(v.type),
        required: v.required ?? true,
        default: v.default ?? null,
        description: v.description,
        label: v.name,
      }))
    }

    // Otherwise extract from start node
    const nodes = workflow.definition?.nodes || []
    const startNode = nodes.find(
      (n) => n.data?.type === 'user_input' || n.data?.type === 'trigger'
    )

    if (!startNode?.data?.config?.parameters) return []

    const params = startNode.data.config.parameters

    return params.map((p) => ({
      name: p.name,
      type: normalizeVariableType(p.type),
      required: p.required ?? true,
      default: p.default ?? null,
      description: p.description || null,
      label: p.label || p.name,
    }))
  }
}
