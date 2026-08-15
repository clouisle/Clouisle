import { beforeEach, describe, expect, mock, test } from 'bun:test'

type TreeNode = { type: unknown; props: Record<string, unknown> }
const jsx = (type: unknown, props: Record<string, unknown> = {}): TreeNode => ({ type, props })
const component = (name: string) => (props: Record<string, unknown>) => jsx(name, props)

let state: unknown[] = []
let stateIndex = 0
const useState = (initial: unknown) => {
  const index = stateIndex++
  if (!(index in state)) state[index] = typeof initial === 'function' ? initial() : initial
  return [state[index], (value: unknown) => {
    state[index] = typeof value === 'function' ? (value as (previous: unknown) => unknown)(state[index]) : value
  }]
}

mock.module('react', () => ({
  useState,
  useEffect: (effect: () => void | (() => void)) => effect(),
  useCallback: (callback: unknown) => callback,
}))
mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('lucide-react', () => ({ X: component('X'), Check: component('Check'), Copy: component('Copy'), Loader2: component('Loader2') }))
mock.module('@/lib/utils', () => ({ cn: (...values: unknown[]) => values.filter(Boolean).join(' ') }))

for (const [path, names] of [
  ['@/components/ui/button', ['Button']],
  ['@/components/ui/input', ['Input']],
  ['@/components/ui/label', ['Label']],
  ['@/components/ui/textarea', ['Textarea']],
  ['@/components/ui/scroll-area', ['ScrollArea']],
  ['@/components/ui/tabs', ['Tabs', 'TabsContent', 'TabsList', 'TabsTrigger']],
] as const) {
  mock.module(path, () => Object.fromEntries(names.map(name => [name, component(name)])))
}

const defaults = {
  iteration: { iteratorType: 'array', itemVariable: 'item', indexVariable: 'index', outputVariable: 'results' },
  loop: { indexVariable: 'index', outputVariable: 'results', loopVariables: [] },
  code: { inputs: [], outputs: [] },
  template: { outputVariable: 'output' },
  fileToUrl: { inputs: [] },
  aggregator: { mode: 'array', outputVariable: 'result' },
  assignment: { assignments: [] },
  extractor: { parameters: [] },
  classifier: { classes: [] },
  answer: {},
  tool: { outputVariable: 'result' },
  media: { mode: 'image', outputVariable: 'result' },
}

for (const [path, exports] of [
  ['./nodes/condition-node', {}],
  ['./nodes/iteration-node', { defaultIterationConfig: defaults.iteration }],
  ['./nodes/loop-node', { defaultLoopConfig: defaults.loop }],
  ['./nodes/code-node', { defaultCodeConfig: defaults.code }],
  ['./nodes/template-node', { defaultTemplateConfig: defaults.template }],
  ['./nodes/file-to-url-node', { defaultFileToUrlConfig: defaults.fileToUrl }],
  ['./nodes/variable-aggregator-node', { defaultVariableAggregatorConfig: defaults.aggregator, aggregationModeOutputTypes: { array: 'Array', string: 'String' } }],
  ['./nodes/variable-assignment-node', { defaultVariableAssignmentConfig: defaults.assignment }],
  ['./nodes/parameter-extractor-node', { defaultParameterExtractorConfig: defaults.extractor }],
  ['./nodes/question-classifier-node', { defaultQuestionClassifierConfig: defaults.classifier }],
  ['./nodes/answer-node', { defaultAnswerNodeConfig: defaults.answer }],
  ['./nodes/tool-node', { defaultToolNodeConfig: defaults.tool }],
  ['./nodes/media-generation-node', { defaultMediaGenerationConfig: defaults.media }],
] as const) mock.module(path, () => exports)

mock.module('./nodes/comment-node', () => ({
  COMMENT_COLORS: {
    amber: { bg: 'amber', borderSelected: 'amber-selected' },
    blue: { bg: 'blue', borderSelected: 'blue-selected' },
  },
}))

const configNames = [
  'StartNodeConfig', 'LLMNodeConfig', 'MediaGenerationNodeConfig', 'CodeNodeConfig',
  'ConditionNodeConfig', 'IterationNodeConfig', 'LoopNodeConfig', 'TemplateNodeConfig',
  'FileToUrlNodeConfig', 'VariableAggregatorNodeConfig', 'VariableAssignmentNodeConfig',
  'ParameterExtractorNodeConfig', 'QuestionClassifierNodeConfig', 'AnswerNodeConfig',
  'ToolNodeConfig', 'ParameterEditDialog', 'CodeInputDialog', 'SubWorkflowNodeConfig',
  'AgentNodeConfig', 'KnowledgeRetrievalNodeConfig',
]
mock.module('./node-config', () => ({
  ...Object.fromEntries(configNames.map(name => [name, component(name)])),
  nodeTypeInfo: new Proxy({}, { get: (_, key) => ({ titleKey: String(key), color: 'node-color', icon: component('NodeIcon') }) }),
  systemParameters: [{ name: 'sys.query', valueType: 'String' }],
  defaultStartParameters: [{ id: 'default', name: 'query', type: 'text', required: true }],
  getTypeName: (type: string) => ({ array: 'Array', object: 'Object', files: 'Array' }[type] || 'String'),
  getLoopVarTypeName: (type: string) => ({ array: 'Array', object: 'Object', number: 'Number', file: 'File', image: 'Image', files: 'Files', images: 'Images' }[type] || 'String'),
  defaultLLMNodeConfig: { outputVariables: { response: 'response', reasoning: 'reasoning', usage: 'usage' } },
  defaultSubWorkflowNodeConfig: { outputVariable: 'result' },
  defaultAgentNodeConfig: { outputVariable: 'response' },
  defaultKnowledgeRetrievalNodeConfig: { outputVariable: 'results' },
}))

const renderNodeOutput = mock((nodeType: string, outputs: unknown) => jsx('RenderedOutput', { nodeType, outputs }))
mock.module('./node-output-renderer', () => ({
  nodeStatusConfig: { failed: { icon: component('FailedIcon'), className: 'failed-class' }, running: { icon: component('RunningIcon'), className: 'running-class' } },
  renderNodeOutput,
}))

const { NodeConfigDrawer } = await import('./node-config-drawer')

function descendants(value: unknown): TreeNode[] {
  if (Array.isArray(value)) return value.flatMap(descendants)
  if (!value || typeof value !== 'object' || !('type' in value)) return []
  const node = value as TreeNode
  if (typeof node.type === 'function') {
    const rendered = (node.type as (props: Record<string, unknown>) => unknown)(node.props)
    return descendants(rendered)
  }
  return [node, ...descendants(node.props.children)]
}

function text(value: unknown): string {
  if (typeof value === 'string' || typeof value === 'number') return String(value)
  if (Array.isArray(value)) return value.map(text).join('')
  if (value && typeof value === 'object' && 'props' in value) return text((value as TreeNode).props.children)
  return ''
}

const baseNode = (type: string, data: Record<string, unknown> = {}, extra: Record<string, unknown> = {}) => ({
  id: `${type}-current`, type, data: { label: 'Current', ...data }, position: { x: 0, y: 0 }, ...extra,
})

function render(node: ReturnType<typeof baseNode> | null, overrides: Record<string, unknown> = {}) {
  stateIndex = 0
  return NodeConfigDrawer({
    node: node as never,
    allNodes: node ? [node] as never : [],
    allEdges: [],
    open: true,
    onClose: mock(() => undefined),
    onUpdate: mock(() => undefined),
    readOnly: true,
    ...overrides,
  }) as TreeNode | null
}

beforeEach(() => {
  state = []
  stateIndex = 0
  renderNodeOutput.mockClear()
})

describe('NodeConfigDrawer', () => {
  test('honors closed and missing-node boundaries', () => {
    expect(render(null)).toBeNull()
    expect(render(baseNode('llm'), { open: false })).toBeNull()
  })

  test('shows duplicate-name and read-only states while exposing only reachable variables', () => {
    const current = baseNode('condition', { label: 'Duplicate', parentIterationId: 'parent' })
    const parent = baseNode('iteration', {
      label: 'Iterator',
      iterationConfig: { iteratorType: 'object', keyVariable: 'key', valueVariable: 'value', outputVariable: 'collected' },
    }, { id: 'parent' })
    const input = baseNode('start', { label: 'Input', parameters: [
      { id: 'items', name: 'items', type: 'array', required: true },
      { id: 'title', name: 'title', type: 'text', required: false },
    ] }, { id: 'input' })
    const sibling = baseNode('llm', { label: 'Duplicate' }, { id: 'sibling' })
    const downstream = baseNode('tool', { label: 'Downstream' }, { id: 'downstream' })
    const overrides = {
      allNodes: [current, parent, input, sibling, downstream],
      allEdges: [{ id: 'a', source: 'input', target: 'parent' }, { id: 'b', source: 'sibling', target: current.id }, { id: 'c', source: current.id, target: 'downstream' }],
    }

    render(current, overrides)
    const nodes = descendants(render(current, overrides))
    const inputNode = nodes.find(node => node.type === 'Input' && node.props.id === 'node-label')
    const config = nodes.find(node => node.type === 'ConditionNodeConfig')
    const variableIds = (config?.props.variables as Array<{ id: string }>).map(variable => variable.id)

    expect(inputNode?.props).toMatchObject({ value: 'Duplicate', disabled: true })
    expect(String(inputNode?.props.className)).toContain('!border-destructive')
    expect(nodes.some(node => node.props.children === 'nodeConfig.nodeNameDuplicate')).toBe(true)
    expect(nodes.some(node => node.props.children === 'nodeConfig.readOnlyNotice')).toBe(true)
    expect(variableIds).toEqual(expect.arrayContaining(['parent.key', 'parent.value', 'parent.collected', 'input.items', 'input.title', 'sibling.response', 'sys.query']))
    expect(variableIds.some(id => id.startsWith('downstream.'))).toBe(false)
  })

  test('routes every supported node type to its focused editor', () => {
    const routes = {
      user_input: 'StartNodeConfig', llm: 'LLMNodeConfig', media_generation: 'MediaGenerationNodeConfig',
      condition: 'ConditionNodeConfig', iteration: 'IterationNodeConfig', loop: 'LoopNodeConfig', code: 'CodeNodeConfig',
      template: 'TemplateNodeConfig', file_to_url: 'FileToUrlNodeConfig', variable_aggregator: 'VariableAggregatorNodeConfig',
      variable_assignment: 'VariableAssignmentNodeConfig', parameter_extractor: 'ParameterExtractorNodeConfig',
      question_classifier: 'QuestionClassifierNodeConfig', sub_workflow: 'SubWorkflowNodeConfig', agent: 'AgentNodeConfig',
      tool: 'ToolNodeConfig', knowledge_retrieval: 'KnowledgeRetrievalNodeConfig', answer: 'AnswerNodeConfig',
    }

    for (const [type, editor] of Object.entries(routes)) {
      state = []
      render(baseNode(type))
      expect(descendants(render(baseNode(type))).some(node => node.type === editor), type).toBe(true)
    }
    state = []
    expect(descendants(render(baseNode('unknown'))).find(node => node.type === 'TabsContent' && node.props.value === 'settings')?.props.children).toBeNull()
  })

  test('exposes typed outputs from every supported upstream producer', () => {
    const current = baseNode('llm', {}, { id: 'current' })
    const upstream = [
      baseNode('iteration', { iterationConfig: { outputVariable: 'items' } }, { id: 'iteration' }),
      baseNode('loop', { loopConfig: { outputVariable: 'rows', indexVariable: 'step', loopVariables: [{ name: 'record', type: 'object' }, { name: 'note', type: 'string' }] } }, { id: 'loop' }),
      baseNode('media_generation', { mediaGenerationConfig: { mode: 'image', outputVariable: 'images' } }, { id: 'media' }),
      baseNode('code', { codeConfig: { inputs: [], outputs: [{ name: 'payload', type: 'object' }, { name: '', type: 'string' }] } }, { id: 'code' }),
      baseNode('template', { templateConfig: { outputVariable: 'text' } }, { id: 'template' }),
      baseNode('file_to_url', { fileToUrlConfig: { inputs: [{ name: 'urls', sourceType: 'files' }] } }, { id: 'files' }),
      baseNode('variable_aggregator', { variableAggregatorConfig: { mode: 'array', outputVariable: 'merged' } }, { id: 'aggregator' }),
      baseNode('parameter_extractor', { parameterExtractorConfig: { parameters: [{ name: 'entities', type: 'array' }] } }, { id: 'extractor' }),
      baseNode('tool', { toolConfig: { outputVariable: 'toolResult' } }, { id: 'tool' }),
      baseNode('sub_workflow', { subWorkflowConfig: { outputVariable: 'workflowResult' } }, { id: 'sub-workflow' }),
      baseNode('agent', { agentConfig: { outputVariable: 'reply' } }, { id: 'agent' }),
      baseNode('knowledge_retrieval', { knowledgeRetrievalConfig: { outputVariable: 'documents' } }, { id: 'retrieval' }),
    ]
    const allNodes = [current, ...upstream]
    const allEdges = upstream.map((node, index) => ({ id: String(index), source: node.id, target: current.id }))
    const editor = descendants(render(current, { allNodes, allEdges })).find(node => node.type === 'LLMNodeConfig')!
    const getAvailableVariables = editor.props.getAvailableVariables as (filter?: 'iterable' | 'all') => Array<{ id: string }>

    const ids = getAvailableVariables().map(variable => variable.id)
    expect(ids).toEqual(expect.arrayContaining([
      'iteration.items', 'loop.rows', 'loop.step', 'loop.record', 'loop.note',
      'media.result', 'media.images', 'code.payload', 'template.text', 'files.urls',
      'aggregator.merged', 'extractor.entities', 'tool.toolResult',
      'sub-workflow.workflowResult', 'agent.reply', 'retrieval.documents',
      'retrieval.context', 'retrieval.totalFound', 'sys.query',
    ]))
    const iterableIds = getAvailableVariables('iterable').map(variable => variable.id)
    expect(iterableIds).toEqual(expect.arrayContaining([
      'iteration.items', 'loop.rows', 'loop.record', 'media.images', 'code.payload',
      'files.urls', 'aggregator.merged', 'extractor.entities', 'tool.toolResult',
      'sub-workflow.workflowResult', 'retrieval.documents',
    ]))
    expect(iterableIds).not.toEqual(expect.arrayContaining(['loop.step', 'loop.note', 'agent.reply', 'retrieval.context', 'sys.query']))
  })

  test('exposes loop-local and writable conversation variables inside a subgraph', () => {
    const current = baseNode('variable_assignment', { parentLoopId: 'loop-parent' }, { id: 'current' })
    const parent = baseNode('loop', {
      loopConfig: {
        indexVariable: 'position',
        outputVariable: 'results',
        loopVariables: [
          { name: 'records', type: 'array' },
          { name: 'metadata', type: 'object' },
          { name: 'label', type: 'string' },
          { name: 'attachment', type: 'file' },
          { name: 'photos', type: 'images' },
        ],
      },
    }, { id: 'loop-parent' })
    const start = baseNode('start', {
      parameters: [{ id: 'topic', name: 'topic', type: 'text', required: true }],
    }, { id: 'start' })
    const sibling = baseNode('code', {
      parentLoopId: 'loop-parent',
      codeConfig: { inputs: [], outputs: [{ name: 'rows', type: 'array' }] },
    }, { id: 'sibling' })
    const editor = descendants(render(current, {
      allNodes: [current, parent, start, sibling],
      allEdges: [
        { id: 'a', source: 'start', target: 'loop-parent' },
        { id: 'b', source: 'sibling', target: 'current' },
      ],
    })).find(node => node.type === 'VariableAssignmentNodeConfig')!

    const variableIds = (editor.props.variables as Array<{ id: string }>).map(variable => variable.id)
    expect(variableIds).toEqual(expect.arrayContaining([
      'loop-parent.position', 'loop-parent.records', 'loop-parent.metadata',
      'loop-parent.label', 'loop-parent.attachment', 'loop-parent.photos',
      'start.topic', 'sibling.rows',
    ]))
    // 文件类型的循环变量必须对 file_to_url 等文件变量选择器可见
    const fileVars = (editor.props.variables as Array<{ id: string; isFile?: boolean; type: string }>)
      .filter(v => v.isFile)
    expect(fileVars.map(v => v.id)).toEqual(expect.arrayContaining([
      'loop-parent.attachment', 'loop-parent.photos',
    ]))
    expect(fileVars.find(v => v.id === 'loop-parent.attachment')!.type).toBe('File')
    expect(fileVars.find(v => v.id === 'loop-parent.photos')!.type).toBe('Images')
    expect(fileVars.some(v => v.id === 'loop-parent.records')).toBe(false)
    const writableIds = (editor.props.conversationVariables as Array<{ id: string }>).map(variable => variable.id)
    expect(writableIds).toEqual(['conversation.topic', 'loop-parent.results'])
  })

  test('marks iteration items as file variables when iterating a file-typed source', () => {
    const current = baseNode('file_to_url', {
      parentIterationId: 'iteration',
      fileToUrlConfig: { inputs: [], ensureAbsolute: true },
    }, { id: 'current' })
    const iteration = baseNode('iteration', {
      iterationConfig: {
        iteratorVariable: '{{start.files}}',
        iteratorType: 'array',
        itemVariable: 'item',
        indexVariable: 'index',
        outputVariable: 'results',
        parallel: false,
      },
    }, { id: 'iteration' })
    const start = baseNode('start', {
      parameters: [{ id: 'files', name: 'files', type: 'files', required: true }],
    }, { id: 'start' })
    const editor = descendants(render(current, {
      allNodes: [current, iteration, start],
      allEdges: [
        { id: 'a', source: 'start', target: 'iteration' },
        { id: 'b', source: 'iteration', target: 'current' },
      ],
    })).find(node => node.type === 'FileToUrlNodeConfig')!

    const fileVariables = (editor.props.variables as Array<{ id: string; isFile?: boolean; type: string }>).filter(v => v.isFile)
    // 迭代源是 files（文件数组），item 是单个文件，必须对 file_to_url 的文件选择器可见
    const item = fileVariables.find(v => v.id === 'iteration.item')
    expect(item).toBeDefined()
    expect(item!.type).toBe('File')
    expect(fileVariables.some(v => v.id === 'iteration.index')).toBe(false)
    expect(fileVariables.some(v => v.id === 'start.files')).toBe(true)
  })

  test('adds, edits, and removes start parameters through the shared dialog', () => {
    const parameter = { id: 'topic', name: 'topic', type: 'text', required: false }
    const node = baseNode('start', { parameters: [parameter] })
    render(node)
    let nodes = descendants(render(node))
    const config = nodes.find(item => item.type === 'StartNodeConfig')!

    ;(config.props.onAddParameter as () => void)()
    nodes = descendants(render(node))
    let dialog = nodes.find(item => item.type === 'ParameterEditDialog')!
    expect(dialog.props).toMatchObject({ open: true, editingParam: null })
    ;(dialog.props.onSave as (value: Record<string, unknown>) => void)({ id: 'new', name: 'new', type: 'number' })

    nodes = descendants(render(node))
    expect((nodes.find(item => item.type === 'StartNodeConfig')!.props.parameters as unknown[])).toHaveLength(2)
    ;(nodes.find(item => item.type === 'StartNodeConfig')!.props.onEditParameter as (value: unknown) => void)(parameter)
    dialog = descendants(render(node)).find(item => item.type === 'ParameterEditDialog')!
    ;(dialog.props.onSave as (value: Record<string, unknown>) => void)({ ...parameter, name: 'subject' })

    nodes = descendants(render(node))
    const updated = nodes.find(item => item.type === 'StartNodeConfig')!
    expect(updated.props.parameters).toEqual(expect.arrayContaining([expect.objectContaining({ id: 'topic', name: 'subject' })]))
    ;(updated.props.onRemoveParameter as (id: string) => void)('topic')
    expect((descendants(render(node)).find(item => item.type === 'StartNodeConfig')!.props.parameters as Array<{ id: string }>).some(item => item.id === 'topic')).toBe(false)
  })

  test('adds and edits code inputs through the shared dialog', () => {
    const input = { id: 'source', name: 'source', type: 'string' }
    const node = baseNode('code', { codeConfig: { inputs: [input], outputs: [] } })
    render(node)
    let nodes = descendants(render(node))
    ;(nodes.find(item => item.type === 'CodeNodeConfig')!.props.onAddInput as () => void)()

    nodes = descendants(render(node))
    let dialog = nodes.find(item => item.type === 'CodeInputDialog')!
    expect(dialog.props).toMatchObject({ open: true, editingInput: null })
    ;(dialog.props.onSave as (value: Record<string, unknown>) => void)({ id: 'extra', name: 'extra', type: 'string' })
    expect((descendants(render(node)).find(item => item.type === 'CodeInputDialog')!.props.existingInputs as unknown[])).toHaveLength(2)

    state[27] = input
    dialog = descendants(render(node)).find(item => item.type === 'CodeInputDialog')!
    ;(dialog.props.onSave as (value: Record<string, unknown>) => void)({ ...input, name: 'payload' })
    expect(descendants(render(node)).find(item => item.type === 'CodeInputDialog')!.props.existingInputs).toEqual(expect.arrayContaining([expect.objectContaining({ id: 'source', name: 'payload' })]))
  })

  test('renders comment editing without tabs and updates color and content', () => {
    const node = baseNode('comment', { content: 'Old note', color: 'blue' })
    render(node)
    let nodes = descendants(render(node))
    expect(nodes.some(item => item.type === 'Tabs')).toBe(false)
    const textarea = nodes.find(item => item.type === 'Textarea')
    expect(textarea?.props.value).toBe('Old note')
    ;(textarea?.props.onChange as (event: { target: { value: string } }) => void)({ target: { value: 'New note' } })
    const amber = nodes.find(item => item.type === 'button' && String(item.props.className).includes('amber'))
    ;(amber?.props.onClick as () => void)()
    nodes = descendants(render(node))
    expect(nodes.find(item => item.type === 'Textarea')?.props.value).toBe('New note')
    expect(nodes.find(item => item.type === 'button' && String(item.props.className).includes('amber-selected'))).toBeDefined()
  })

  test('shows run output, token and safe error details and copies serialized output', () => {
    const writes: string[] = []
    globalThis.navigator = { clipboard: { writeText: (text: string) => { writes.push(text); return Promise.resolve() } } } as never
    const trace = {
      status: 'failed', nodeType: 'llm', durationMs: 12.34567,
      tokens: { prompt: 3, completion: 4, total: 7 }, outputs: { answer: 'ok' }, error: 'Quota exceeded',
    }
    const nodes = descendants(render(baseNode('llm'), { lastRunTrace: trace }))
    const copy = nodes.find(node => node.type === 'Button' && node.props.size === 'sm')

    expect(nodes.some(node => text(node) === '12.346 ms')).toBe(true)
    expect(nodes.some(node => node.props.children === 'Quota exceeded')).toBe(true)
    expect(renderNodeOutput).toHaveBeenCalledWith('llm', { answer: 'ok' }, expect.any(Function))
    ;(copy?.props.onClick as () => void)()
    expect(writes).toEqual(['{\n  "answer": "ok"\n}'])
  })

  test('redacts unsafe errors and shows streaming and empty-history boundaries', () => {
    const unsafe = descendants(render(baseNode('llm'), { lastRunTrace: {
      status: 'running', nodeType: 'llm', streamingContent: 'partial', error: 'HTTP 500\nTraceback', tokens: { total: 0 },
    } }))
    expect(unsafe.some(node => node.props.children === 'runDrawer.unknownError')).toBe(true)
    expect(unsafe.some(node => node.props.children === 'runDrawer.generating')).toBe(true)
    expect(unsafe.some(node => text(node).includes('partial'))).toBe(true)

    state = []
    const empty = descendants(render(baseNode('llm')))
    expect(empty.some(node => node.props.children === 'nodeConfig.noRunHistory')).toBe(true)
  })

  test('debounces observable updates and suppresses them in read-only mode', async () => {
    const node = baseNode('llm', { description: 'Saved description' })
    const onUpdate = mock(() => undefined)
    render(node, { readOnly: false, onUpdate })
    render(node, { readOnly: false, onUpdate })
    await new Promise(resolve => setTimeout(resolve, 320))
    expect(onUpdate).toHaveBeenCalledWith(node.id, expect.objectContaining({ label: 'Current', description: 'Saved description' }))

    onUpdate.mockClear()
    state = []
    render(node, { readOnly: true, onUpdate })
    await new Promise(resolve => setTimeout(resolve, 320))
    expect(onUpdate).not.toHaveBeenCalled()
  })
})
