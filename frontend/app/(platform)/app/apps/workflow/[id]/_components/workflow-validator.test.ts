import { describe, expect, test } from 'bun:test'
import type { Edge } from '@xyflow/react'
import { getNodeTypeColor, getNodeTypeLabelKey, validateWorkflow } from './workflow-validator'

type WorkflowNode = Parameters<typeof validateWorkflow>[0][number]
type NodeData = WorkflowNode['data']

function node(type: string, data: Partial<NodeData> = {}, parentId?: string): WorkflowNode {
  return {
    id: data.label?.toLowerCase().replaceAll(' ', '-') || type,
    type,
    position: { x: 0, y: 0 },
    parentId,
    data: { type, label: type, config: {}, ...data },
  }
}

function edge(source: string, target: string): Edge {
  return { id: `${source}-${target}`, source, target }
}

function messages(nodes: WorkflowNode[], edges: Edge[] = []) {
  return validateWorkflow(nodes, edges).map(issue => ({
    nodeId: issue.nodeId,
    severity: issue.severity,
    message: issue.message,
    field: issue.field,
    params: issue.messageParams,
  }))
}

describe('validateWorkflow', () => {
  test('accepts a connected graph whose nodes reference transitive upstream outputs', () => {
    const nodes = [
      node('user_input', { label: 'Input', parameters: [{ name: 'question', type: 'string' }] }),
      node('llm', {
        label: 'Writer',
        llmConfig: { modelId: 'model-1', prompt: 'Answer the question' },
      }),
      node('code', {
        label: 'Formatter',
        codeConfig: {
          code: 'return input',
          inputs: [
            { name: 'response', value: '{{writer.response}}' },
            { name: 'requestId', value: 'sys_workflow_run_id' },
            { name: 'history', value: 'conversation.history' },
          ],
          outputs: [{ name: 'formatted' }],
        },
      }),
      node('answer', {
        label: 'Answer',
        answerConfig: { outputs: [{ id: 'result', sourceVariable: 'formatter.formatted' }] },
      }),
    ]
    const edges = [edge('input', 'writer'), edge('writer', 'formatter'), edge('formatter', 'answer')]

    expect(validateWorkflow(nodes, edges)).toEqual([])
  })

  test('reports concrete classifier, answer, LLM, media, and condition failures', () => {
    const nodes = [
      node('user_input', { label: 'Input', parameters: [{ name: 'question', type: 'string' }] }),
      node('question_classifier', {
        label: 'Classifier',
        questionClassifierConfig: {
          sourceVariable: 'missing.question',
          categories: [{ id: '1', name: '' }, { id: '2', name: 'Billing' }],
        },
      }),
      node('answer', { label: 'Answer', answerConfig: { outputs: [{ id: 'a' }, { id: 'b', sourceVariable: 'missing.value' }] } }),
      node('llm', { label: 'LLM', llmConfig: {} }),
      node('media_generation', {
        label: 'Media',
        mediaGenerationConfig: {
          mode: 'audio' as 'image',
          referenceImageVariable: 'missing.image',
          startImageVariable: 'missing.start',
          outputVariable: 'not valid',
        },
      }),
      node('condition', {
        label: 'Condition',
        branches: [
          { id: 'if', type: 'if', conditions: [] },
          { id: 'else-if', type: 'else_if', conditions: [{ variable: 'missing.flag', operator: '' }] },
          { id: 'else', type: 'else', conditions: [] },
        ],
      }),
    ]
    const edges = nodes.slice(1).map(current => edge('input', current.id))
    const issues = messages(nodes, edges)

    expect(issues.filter(issue => issue.nodeId === 'classifier')).toEqual([
      { nodeId: 'classifier', severity: 'error', message: 'variableNotAvailable', field: 'sourceVariable', params: { name: 'question' } },
      { nodeId: 'classifier', severity: 'error', message: 'modelNotSelected', field: 'modelId', params: undefined },
      { nodeId: 'classifier', severity: 'warning', message: 'unnamedCategories', field: 'categories', params: { count: 1 } },
    ])
    expect(issues.filter(issue => issue.nodeId === 'answer')).toHaveLength(2)
    expect(issues.filter(issue => issue.nodeId === 'llm').map(issue => issue.message)).toEqual(['modelNotSelected', 'suggestPrompt'])
    expect(issues.filter(issue => issue.nodeId === 'media').map(issue => issue.message)).toEqual([
      'modelNotSelected', 'promptEmpty', 'invalidMediaMode', 'variableNotAvailable', 'variableNotAvailable', 'invalidVariableName',
    ])
    expect(issues.filter(issue => issue.nodeId === 'condition')).toEqual([
      { nodeId: 'condition', severity: 'error', message: 'branchNoCondition', field: 'branches', params: { name: 'IF' } },
      { nodeId: 'condition', severity: 'error', message: 'branchIncompleteCondition', field: 'branches', params: { name: 'ELSE_IF' } },
      { nodeId: 'condition', severity: 'error', message: 'conditionVariableNotAvailable', field: 'branches', params: { name: 'flag' } },
    ])
  })

  test('validates code, template, tool, extractor, and variable operations', () => {
    const nodes = [
      node('user_input', { label: 'Input', parameters: [{ name: 'value', type: 'string' }] }),
      node('code', {
        label: 'Code',
        codeConfig: { inputs: [{ name: 'x' }, { name: 'same', value: 'missing.one' }, { name: 'same', value: 'missing.one' }] },
      }),
      node('template', { label: 'Template', templateConfig: { variables: [{ name: 'x' }, { name: 'y', variable: 'missing.two' }] } }),
      node('tool', { label: 'Tool', toolConfig: { inputs: [{ name: 'required', required: true }, { name: 'ref', value: 'missing.three' }] } }),
      node('parameter_extractor', { label: 'Extractor', parameterExtractorConfig: {} }),
      node('variable_aggregator', {
        label: 'Aggregator',
        variableAggregatorConfig: { variables: [{ id: '1' }, { id: '2', sourceVariable: 'missing.four' }] },
      }),
      node('variable_assignment', {
        label: 'Assignment',
        variableAssignmentConfig: { assignments: [{ targetVariable: '' }, { targetVariable: 'x', sourceVariable: 'missing.five' }] },
      }),
      node('answer', { label: 'Answer', answerConfig: { outputs: [{ id: 'result', sourceVariable: 'input.value' }] } }),
    ]
    const edges = nodes.slice(1).map(current => edge('input', current.id))
    const issues = messages(nodes, edges)

    expect(issues.filter(issue => issue.nodeId === 'code').map(issue => issue.message)).toEqual([
      'codeEmpty', 'inputsMissingSource', 'duplicateInputNames', 'inputVariableRefNotExist',
    ])
    expect(issues.filter(issue => issue.nodeId === 'template').map(issue => issue.message)).toEqual([
      'templateEmpty', 'templateVarsMissingSource', 'templateVarRefNotExist',
    ])
    expect(issues.filter(issue => issue.nodeId === 'tool').map(issue => issue.message)).toEqual([
      'toolNotSelected', 'requiredParamsMissing', 'paramRefNotExist',
    ])
    expect(issues.filter(issue => issue.nodeId === 'extractor').map(issue => issue.message)).toEqual([
      'inputVariableEmpty', 'modelNotSelected', 'atLeastOneExtractParam',
    ])
    expect(issues.filter(issue => issue.nodeId === 'aggregator').map(issue => issue.message)).toEqual([
      'aggregateVarsMissingSource', 'aggregateVarRefNotExist',
    ])
    expect(issues.filter(issue => issue.nodeId === 'assignment').map(issue => issue.message)).toEqual([
      'incompleteAssignments', 'assignmentRefNotExist',
    ])
  })

  test('validates container structure and exposes parent iteration and loop variables to children', () => {
    const validIteration = node('iteration', {
      label: 'Iteration',
      iterationConfig: { iteratorVariable: '{{input.items}}', itemVariable: 'entry' },
    })
    const validLoop = node('loop', {
      label: 'Loop',
      loopConfig: { maxIterations: 3, loopVariables: [{ name: 'current', type: 'string' }] },
    })
    const nodes = [
      node('user_input', { label: 'Input', parameters: [{ name: 'items', type: 'array' }] }),
      validIteration,
      node('iteration_start', { label: 'Iteration Start' }, validIteration.id),
      node('template', {
        label: 'Iteration Body',
        templateConfig: { template: '{{entry}}', variables: [{ name: 'entry', variable: 'iteration.entry' }] },
      }, validIteration.id),
      validLoop,
      node('loop_start', { label: 'Loop Start' }, validLoop.id),
      node('code', {
        label: 'Loop Body',
        codeConfig: { code: 'return current', inputs: [{ name: 'current', value: 'loop.current' }] },
      }, validLoop.id),
      node('answer', { label: 'Answer', answerConfig: { outputs: [{ id: 'result', sourceVariable: 'input.items' }] } }),
    ]
    const edges = [
      edge('input', 'iteration'), edge('iteration-start', 'iteration-body'), edge('iteration', 'loop'),
      edge('loop-start', 'loop-body'), edge('loop', 'answer'),
    ]

    expect(validateWorkflow(nodes, edges)).toEqual([])

    const invalid = [
      node('user_input', { label: 'Input', parameters: [{ name: 'items', type: 'array' }] }),
      node('iteration', { label: 'Bad Iteration', iterationConfig: { iteratorVariable: '{{missing.items}}' } }),
      node('loop', { label: 'Bad Loop', loopConfig: { conditionVariable: 'missing.done' } }),
    ]
    expect(messages(invalid).map(issue => issue.message)).toEqual([
      'iterateVariableNotAvailable', 'iterationMissingStart', 'iterationNoProcessNodes',
      'conditionVariableNotAvailable', 'loopMissingStart', 'loopNoProcessNodes',
      'nodeNoInput', 'nodeNoInput', 'noOutputNode',
    ])
  })

  test('accepts bare iteration item references inside the iteration body', () => {
    const iteration = node('iteration', {
      label: 'Iteration',
      iterationConfig: {
        iteratorVariable: '{{input.files}}',
        iteratorType: 'array',
        itemVariable: 'doc',
        indexVariable: 'index',
        outputVariable: 'results',
      },
    })
    const nodes = [
      node('user_input', { label: 'Input', parameters: [{ name: 'files', type: 'files' }] }),
      iteration,
      node('iteration_start', { label: 'Iteration Start' }, iteration.id),
      node('file_to_url', {
        label: 'File URL',
        fileToUrlConfig: {
          inputs: [{ name: 'doc_url', sourceVariable: '{{doc}}', sourceType: 'file' }],
          ensureAbsolute: true,
        },
      }, iteration.id),
      node('answer', { label: 'Answer', answerConfig: { outputs: [{ id: 'result', sourceVariable: '{{iteration.results}}' }] } }),
    ]
    const edges = [
      edge('input', 'iteration'),
      edge('iteration-start', 'file-url'),
      edge('iteration', 'answer'),
    ]

    // 裸名 {{doc}}（等价于 {{iteration.doc}}）与节点作用域形式都应通过
    expect(validateWorkflow(nodes, edges)).toEqual([])

    const bad = [
      ...nodes.filter(n => n.id !== 'file-url'),
      node('file_to_url', {
        label: 'File URL',
        fileToUrlConfig: {
          inputs: [{ name: 'doc_url', sourceVariable: '{{missing}}', sourceType: 'file' }],
          ensureAbsolute: true,
        },
      }, iteration.id),
    ]
    const badIssues = messages(bad, edges).filter(issue => issue.nodeId === 'file-url')
    expect(badIssues.map(issue => issue.message)).toEqual(['inputVariableRefNotExist'])
  })

  test('validates integration nodes, connection warnings, and ignores comments', () => {
    const nodes = [
      node('trigger', { label: 'Trigger', triggerConfig: {} }),
      node('sub_workflow', {
        label: 'Sub Flow',
        subWorkflowConfig: { inputMappings: [{ name: 'input', sourceVariable: 'missing.input' }] },
      }),
      node('agent', { label: 'Agent', agentConfig: { inputVariable: 'missing.agentInput' } }),
      node('file_to_url', { label: 'File URL', fileToUrlConfig: { inputs: [{ name: 'file', sourceVariable: 'missing.file' }] } }),
      node('knowledge_retrieval', {
        label: 'Knowledge',
        knowledgeRetrievalConfig: { querySource: 'variable', queryVariableRef: 'missing.query', outputVariable: 'bad name' },
      }),
      node('answer', { label: 'Answer', answerConfig: { outputs: [] } }),
      node('comment', { label: 'Ignored' }),
    ]
    const edges = [edge('trigger', 'sub-flow'), edge('sub-flow', 'agent'), edge('agent', 'file-url'), edge('file-url', 'knowledge')]
    const issues = messages(nodes, edges)

    expect(issues.filter(issue => issue.nodeId === 'trigger').map(issue => issue.message)).toEqual(['triggerTypeNotSelected'])
    expect(issues.filter(issue => issue.nodeId === 'sub-flow').map(issue => issue.message)).toEqual(['subWorkflowNotSelected', 'inputMappingRefNotExist'])
    expect(issues.filter(issue => issue.nodeId === 'agent').map(issue => issue.message)).toEqual(['agentNotSelected', 'variableNotAvailable'])
    expect(issues.filter(issue => issue.nodeId === 'file-url').map(issue => issue.message)).toEqual(['inputVariableRefNotExist'])
    expect(issues.filter(issue => issue.nodeId === 'knowledge').map(issue => issue.message)).toEqual([
      'knowledgeBaseNotSelected', 'variableNotAvailable', 'invalidVariableName',
    ])
    expect(issues.filter(issue => issue.nodeId === 'answer').map(issue => issue.message)).toEqual(['outputVariableEmpty', 'nodeNoInput'])
    expect(issues.some(issue => issue.nodeId === 'ignored')).toBe(false)
  })
})

describe('workflow validator display metadata', () => {
  test('maps known and unknown node types to stable labels and colors', () => {
    expect(getNodeTypeColor('llm')).toBe('bg-blue-500')
    expect(getNodeTypeColor('unknown')).toBe('bg-gray-500')
    expect(getNodeTypeLabelKey('answer')).toBe('nodeLabels.answer')
    expect(getNodeTypeLabelKey('custom')).toBe('custom')
  })
})
