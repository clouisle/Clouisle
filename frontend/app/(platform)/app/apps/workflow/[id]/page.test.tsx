import { beforeEach, expect, mock, test } from 'bun:test'

type Props = Record<string, unknown>
type TestNode = { type: unknown; props: Props }
type StateRecord = { value: unknown; set: (value: unknown) => void }

const jsx = (type: unknown, props: Props = {}): TestNode => ({ type, props })
const element = (props: Props) => jsx('element', props)
const listeners = new Map<string, Set<EventListener>>()
globalThis.window = {
  addEventListener(type: string, listener: EventListener) {
    if (!listeners.has(type)) listeners.set(type, new Set())
    listeners.get(type)!.add(listener)
  },
  removeEventListener(type: string, listener: EventListener) {
    listeners.get(type)?.delete(listener)
  },
  innerWidth: 1200,
  innerHeight: 800,
} as never
const push = mock(() => {})
const router = { push }
const toastError = mock(() => {})
const toastSuccess = mock(() => {})
let currentUser: Props = { id: 'user-1', username: 'owner', is_superuser: false }
let currentTeam: Props = { id: 'team-1', role: 'member' }
let permissionGranted = false
const getCurrentUser = mock(async () => currentUser)
const validateWorkflow = mock(() => [] as Props[])
const screenToFlowPosition = mock(({ x, y }: { x: number; y: number }) => ({ x, y }))
const fitView = mock(() => {})
const setCenter = mock(() => {})

let states: StateRecord[] = []
let dependencies: (unknown[] | undefined)[] = []
let cleanups: (((() => void) | undefined))[] = []
let cursor = 0
let nodes: Props[] = []
let edges: Props[] = []

function changed(previous: unknown[] | undefined, next: unknown[] | undefined) {
  return !previous || !next || previous.length !== next.length || next.some((value, index) => !Object.is(value, previous[index]))
}

function stateAt(index: number, initial: unknown): StateRecord {
  if (!states[index]) {
    const record: StateRecord = {
      value: typeof initial === 'function' ? (initial as () => unknown)() : initial,
      set(value) {
        record.value = typeof value === 'function' ? (value as (current: unknown) => unknown)(record.value) : value
      },
    }
    states[index] = record
  }
  return states[index]
}

const React = {
  useState(initial: unknown) {
    const record = stateAt(cursor++, initial)
    return [record.value, record.set]
  },
  useRef(initial: unknown) {
    const record = stateAt(cursor++, () => ({ current: initial }))
    return record.value
  },
  useCallback(callback: unknown, deps: unknown[]) {
    const index = cursor++
    if (!states[index]) states[index] = { value: callback, set(value) { states[index].value = value } }
    if (changed(dependencies[index], deps)) {
      dependencies[index] = deps
      states[index].value = callback
    }
    return states[index].value
  },
  useMemo(factory: () => unknown, deps: unknown[]) {
    const index = cursor++
    if (!states[index]) states[index] = { value: undefined, set(value) { states[index].value = value } }
    if (changed(dependencies[index], deps)) {
      dependencies[index] = deps
      states[index].value = factory()
    }
    return states[index].value
  },
  useEffect(effect: () => void | (() => void), deps?: unknown[]) {
    const index = cursor++
    if (changed(dependencies[index], deps)) {
      cleanups[index]?.()
      dependencies[index] = deps
      cleanups[index] = effect() || undefined
    }
  },
}

const setNodes = (value: unknown) => {
  nodes = typeof value === 'function' ? (value as (current: Props[]) => Props[])(nodes) : value as Props[]
}
const setEdges = (value: unknown) => {
  edges = typeof value === 'function' ? (value as (current: Props[]) => Props[])(edges) : value as Props[]
}
const onNodesChangeBase = mock(() => {})
const onEdgesChangeBase = mock(() => {})

mock.module('react', () => ({ ...React, default: React }))
mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('next/navigation', () => ({ useParams: () => ({ id: 'workflow-1' }), useRouter: () => router }))
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('next/image', () => ({ default: element }))
mock.module('sonner', () => ({ toast: { error: toastError, success: toastSuccess } }))
mock.module('@/lib/api/workflows', () => ({ workflowsApi: {} }))
mock.module('@xyflow/react', () => ({
  ReactFlow: (props: Props) => jsx('react-flow', props), Background: element, MiniMap: element, Panel: element,
  ReactFlowProvider: element, BackgroundVariant: { Dots: 'dots' }, SelectionMode: { Partial: 'partial', Full: 'full' },
  useNodesState: () => [nodes, setNodes, onNodesChangeBase], useEdgesState: () => [edges, setEdges, onEdgesChangeBase],
  addEdge: (connection: Props, current: Props[]) => [...current, connection],
  useReactFlow: () => ({ screenToFlowPosition, getViewport: () => ({ x: 0, y: 0, zoom: 1 }), fitView, setCenter }),
  useViewport: () => ({ zoom: 1 }),
}))
mock.module('@xyflow/react/dist/style.css', () => ({}))
mock.module('lucide-react', () => ({
  ArrowLeft: element, Save: element, Play: element, Settings: element, Loader2: element, Minus: element,
  Plus: element, PlusCircle: element, MousePointer2: element, Hand: element, Sparkles: element, Maximize: element,
  StickyNote: element, ClipboardCheck: element, Globe: element, GlobeLock: element, LayoutGrid: element,
  ExternalLink: element, FileText: element, Activity: element, GitBranch: element, Code: element,
}))
mock.module('@/lib/api/auth', () => ({ authApi: { getCurrentUser } }))
mock.module('@/components/permission-guard', () => ({ useCanPerform: () => ({ canPerform: () => permissionGranted }) }))
mock.module('@/contexts/team-context', () => ({ useTeam: () => ({ currentTeam }) }))

mock.module('@/components/ui/button', () => ({ Button: element }))
mock.module('@/components/ui/skeleton', () => ({ Skeleton: element }))
mock.module('@/components/ui/dropdown-menu', () => ({
  DropdownMenu: element, DropdownMenuContent: element, DropdownMenuItem: element, DropdownMenuTrigger: element,
}))
mock.module('@/components/ui/alert-dialog', () => ({
  AlertDialog: element, AlertDialogAction: element, AlertDialogCancel: element, AlertDialogContent: element,
  AlertDialogDescription: element, AlertDialogFooter: element, AlertDialogHeader: element, AlertDialogTitle: element,
}))
mock.module('@/components/ui/tooltip', () => ({
  Tooltip: element,
  TooltipTrigger: (props: Props) => props.render || element(props),
  TooltipContent: element,
}))

mock.module('./_components/nodes/user-input-node', () => ({ UserInputNode: element }))
mock.module('./_components/nodes/trigger-node', () => ({ TriggerNode: element }))
mock.module('./_components/nodes/llm-node', () => ({ LLMNode: element }))
mock.module('./_components/nodes/media-generation-node', () => ({ MediaGenerationNode: element }))
mock.module('./_components/nodes/condition-node', () => ({ ConditionNode: element }))
mock.module('./_components/nodes/sub-workflow-node', () => ({ SubWorkflowNode: element }))
mock.module('./_components/nodes/agent-node', () => ({ AgentNode: element }))
mock.module('./_components/nodes/tool-node', () => ({ ToolNode: element }))
mock.module('./_components/nodes/knowledge-retrieval-node', () => ({ KnowledgeRetrievalNode: element }))
mock.module('./_components/nodes/iteration-node', () => ({ IterationNode: element, IterationStartNode: element, IterationExitNode: element }))
mock.module('./_components/nodes/loop-node', () => ({ LoopNode: element, LoopStartNode: element, LoopExitNode: element }))
mock.module('./_components/nodes/code-node', () => ({ CodeNode: element }))
mock.module('./_components/nodes/template-node', () => ({ TemplateNode: element }))
mock.module('./_components/nodes/file-to-url-node', () => ({ FileToUrlNode: element }))
mock.module('./_components/nodes/variable-aggregator-node', () => ({ VariableAggregatorNode: element }))
mock.module('./_components/nodes/variable-assignment-node', () => ({ VariableAssignmentNode: element }))
mock.module('./_components/nodes/parameter-extractor-node', () => ({ ParameterExtractorNode: element }))
mock.module('./_components/nodes/question-classifier-node', () => ({ QuestionClassifierNode: element }))
mock.module('./_components/nodes/answer-node', () => ({ AnswerNode: element }))
mock.module('./_components/nodes/comment-node', () => ({ CommentNode: element }))

mock.module('./_components/start-node-selector', () => ({ StartNodeSelector: (props: Props) => jsx('start-node-selector', props) }))
mock.module('./_components/node-config-drawer', () => ({ NodeConfigDrawer: (props: Props) => jsx('node-config-drawer', props) }))
mock.module('./_components/workflow-settings-drawer', () => ({ WorkflowSettingsDrawer: (props: Props) => jsx('workflow-settings-drawer', props) }))
mock.module('./_components/workflow-run-drawer', () => ({ WorkflowRunDrawer: (props: Props) => jsx('workflow-run-drawer', props) }))
mock.module('./_components/add-node-popover', () => ({ AddNodePopover: (props: Props) => jsx('add-node-popover', props) }))
mock.module('./_components/validation-checklist', () => ({ ValidationChecklist: (props: Props) => jsx('validation-checklist', props) }))
mock.module('../../[id]/_components/embed-config-dialog', () => ({ EmbedConfigDialog: (props: Props) => jsx('embed-config-dialog', props) }))
mock.module('./_components/workflow-validator', () => ({ validateWorkflow }))

const { WorkflowEditorContent } = await import('./page')

const workflow = {
  id: 'workflow-1', team_id: 'team-1', name: 'Coverage Flow', icon: null, status: 'draft',
  definition: { nodes: [{ id: 'start-1', type: 'user_input', position: { x: 0, y: 0 }, data: {
    type: 'user_input', label: 'Start', config: {}, parameters: [
      { name: 'query', type: 'string', required: true, defaultValue: 'hello', description: 'Prompt' },
    ],
  } }], edges: [] }, variables: [], created_by_id: 'user-1',
}

function api(overrides: Props = {}) {
  return {
    getWorkflow: mock(async () => workflow), updateWorkflow: mock(async () => workflow),
    publishWorkflow: mock(async () => ({ ...workflow, status: 'published' })),
    unpublishWorkflow: mock(async () => ({ ...workflow, status: 'draft' })), ...overrides,
  }
}

function descendants(value: unknown): TestNode[] {
  if (Array.isArray(value)) return value.flatMap(descendants)
  if (!value || typeof value !== 'object' || !('props' in value)) return []
  const node = value as TestNode
  if (typeof node.type === 'function') return descendants((node.type as (props: Props) => unknown)(node.props))
  return [node, ...descendants(node.props.children)]
}

function render(editorApi: ReturnType<typeof api>, props: Props = {}) {
  cursor = 0
  return WorkflowEditorContent({ workflowId: 'workflow-1', api: editorApi as never, ...props }) as TestNode
}

async function settle(editorApi: ReturnType<typeof api>, props: Props = {}) {
  render(editorApi, props)
  await new Promise((resolve) => setTimeout(resolve, 0))
  return render(editorApi, props)
}

function flow(tree: TestNode) {
  return descendants(tree).find((node) => node.type === 'react-flow')!
}

function findAction(tree: TestNode, label: string) {
  return descendants(tree).find((node) => node.props.onClick && text(node.props.children).includes(label))!
}

function text(value: unknown): string {
  if (typeof value === 'string' || typeof value === 'number') return String(value)
  if (Array.isArray(value)) return value.map(text).join('')
  if (!value || typeof value !== 'object' || !('props' in value)) return ''
  const node = value as TestNode
  if (typeof node.type === 'function') return text((node.type as (props: Props) => unknown)(node.props))
  return text(node.props.children)
}

beforeEach(() => {
  cleanups.forEach((cleanup) => cleanup?.())
  states = []
  dependencies = []
  cleanups = []
  cursor = 0
  nodes = []
  edges = []
  listeners.clear()
  currentUser = { id: 'user-1', username: 'owner', is_superuser: false }
  currentTeam = { id: 'team-1', role: 'member' }
  permissionGranted = false
  push.mockClear()
  toastError.mockClear()
  toastSuccess.mockClear()
  getCurrentUser.mockClear()
  validateWorkflow.mockClear()
  onNodesChangeBase.mockClear()
  onEdgesChangeBase.mockClear()
  fitView.mockClear()
  setCenter.mockClear()
})

test('loads an existing workflow and redirects when loading fails', async () => {
  const editorApi = api()
  const tree = await settle(editorApi)

  expect(editorApi.getWorkflow).toHaveBeenCalledWith('workflow-1')
  expect(getCurrentUser).toHaveBeenCalledWith({ skipAuthRedirect: true })
  expect(flow(tree).props.nodes).toHaveLength(1)

  states = []
  dependencies = []
  const failingApi = api({ getWorkflow: mock(async () => { throw new Error('missing') }) })
  await settle(failingApi)
  expect(push).toHaveBeenCalledWith('/app/apps')
})

test('creates the selected start node for an empty workflow', async () => {
  const emptyApi = api({ getWorkflow: mock(async () => ({ ...workflow, definition: { nodes: [], edges: [] } })) })
  let tree = await settle(emptyApi)
  const selector = descendants(tree).find((node) => node.type === 'start-node-selector')!

  ;(selector.props.onSelect as (type: string) => void)('trigger')
  tree = render(emptyApi)

  expect(flow(tree).props.nodes).toEqual([expect.objectContaining({ id: 'trigger-1', type: 'trigger' })])
})

test('protects the start node from removal and saves its input variables', async () => {
  const editorApi = api()
  let tree = await settle(editorApi)

  ;(flow(tree).props.onNodesChange as (changes: Props[]) => void)([{ type: 'remove', id: 'start-1' }])
  expect(toastError).toHaveBeenCalledWith('editor.cannotDeleteStart')
  expect(onNodesChangeBase).toHaveBeenCalledWith([])

  tree = render(editorApi)
  const save = findAction(tree, 'save')
  await (save.props.onClick as () => Promise<void>)()

  expect(editorApi.updateWorkflow).toHaveBeenCalledWith('workflow-1', expect.objectContaining({
    variables: [{ name: 'query', type: 'string', required: true, default: 'hello', description: 'Prompt' }],
  }))
  expect(toastSuccess).toHaveBeenCalledWith('saved')
})

test('saves pending edits before publishing and supports unpublishing', async () => {
  const editorApi = api()
  let tree = await settle(editorApi)
  ;(flow(tree).props.onConnect as (connection: Props) => void)({ source: 'start-1', target: 'next-1' })
  tree = render(editorApi)

  const publish = findAction(tree, 'publish')
  await (publish.props.onClick as () => Promise<void>)()

  expect(editorApi.updateWorkflow).toHaveBeenCalledTimes(1)
  expect(editorApi.publishWorkflow).toHaveBeenCalledWith('workflow-1')
  expect(toastSuccess).toHaveBeenCalledWith('published')

  tree = render(editorApi)
  const unpublish = findAction(tree, 'published')
  await (unpublish.props.onClick as () => Promise<void>)()
  expect(editorApi.unpublishWorkflow).toHaveBeenCalledWith('workflow-1')
})

test('passes edge changes through and updates container child extents', async () => {
  const nestedWorkflow = {
    ...workflow,
    definition: {
      nodes: [
        workflow.definition.nodes[0],
        { id: 'loop-1', type: 'loop', position: { x: 100, y: 100 }, data: { type: 'loop', label: 'Loop', config: {} } },
        { id: 'child-1', type: 'llm', parentId: 'loop-1', position: { x: 20, y: 80 }, data: { type: 'llm', label: 'LLM', config: {} } },
      ],
      edges: [{ id: 'edge-1', source: 'start-1', target: 'loop-1' }],
    },
  }
  const editorApi = api({ getWorkflow: mock(async () => nestedWorkflow) })
  let tree = await settle(editorApi)

  ;(flow(tree).props.onEdgesChange as (changes: Props[]) => void)([{ type: 'remove', id: 'edge-1' }])
  expect(onEdgesChangeBase).toHaveBeenCalledWith([{ type: 'remove', id: 'edge-1' }])

  ;(flow(tree).props.onNodesChange as (changes: Props[]) => void)([
    { type: 'dimensions', id: 'loop-1', resizing: true, dimensions: { width: 600, height: 350 } },
  ])
  tree = render(editorApi)

  expect((flow(tree).props.nodes as Props[]).find((node) => node.id === 'child-1')?.extent).toEqual([
    [12, 14],
    [588, 338],
  ])
  expect(onNodesChangeBase).toHaveBeenLastCalledWith([
    { type: 'dimensions', id: 'loop-1', resizing: true, dimensions: { width: 600, height: 350 } },
  ])
})

test('opens node configuration, updates related children, and clears stale selection', async () => {
  const configuredWorkflow = {
    ...workflow,
    definition: {
      nodes: [
        workflow.definition.nodes[0],
        { id: 'iteration-1', type: 'iteration', position: { x: 100, y: 100 }, data: { type: 'iteration', label: 'Iteration', config: {} } },
        { id: 'child-1', type: 'llm', parentId: 'iteration-1', position: { x: 20, y: 80 }, data: { type: 'llm', label: 'Child', config: {}, parentIterationId: 'iteration-1' } },
      ],
      edges: [],
    },
  }
  const editorApi = api({ getWorkflow: mock(async () => configuredWorkflow) })
  let tree = await settle(editorApi)
  const iteration = (flow(tree).props.nodes as Props[]).find((node) => node.id === 'iteration-1')!

  ;(flow(tree).props.onNodeClick as (event: unknown, node: Props) => void)({}, iteration)
  tree = render(editorApi)
  let drawer = descendants(tree).find((node) => node.type === 'node-config-drawer')!
  expect(drawer.props.open).toBe(true)
  expect((drawer.props.node as Props).id).toBe('iteration-1')

  ;(drawer.props.onUpdate as (id: string, data: Props) => void)('iteration-1', {
    type: 'iteration', label: 'Updated', config: {}, iterationConfig: { parallel: true },
  })
  tree = render(editorApi)
  const rendered = flow(tree).props.nodes as Props[]
  expect((rendered.find((node) => node.id === 'iteration-1')?.data as Props).label).toBe('Updated')
  expect((rendered.find((node) => node.id === 'child-1')?.data as Props).iterationConfig).toEqual({ parallel: true })

  setNodes((current: Props[]) => current.filter((node) => node.id !== 'iteration-1'))
  render(editorApi)
  tree = render(editorApi)
  drawer = descendants(tree).find((node) => node.type === 'node-config-drawer')!
  expect(drawer.props.open).toBe(false)
  expect(drawer.props.node).toBeNull()
})

test('adds connected container nodes and validates selection on the canvas', async () => {
  validateWorkflow.mockReturnValue([{ nodeId: 'start-1', message: 'invalid' }])
  const editorApi = api()
  let tree = await settle(editorApi)
  const canvas = flow(tree)

  ;(canvas.props.onConnectStart as (event: unknown, params: Props) => void)({}, {
    nodeId: 'start-1', handleId: 'source-a', handleType: 'source',
  })
  ;(canvas.props.onConnectEnd as (event: Props, state: Props) => void)(
    { clientX: 500, clientY: 300 },
    { isValid: false },
  )
  tree = render(editorApi)
  const popover = descendants(tree).find((node) => node.type === 'add-node-popover')!
  expect(popover.props.position).toEqual({ x: 500, y: 300 })

  ;(popover.props.onSelect as (type: string, source: string, handle?: string) => void)('loop', 'start-1', 'source-a')
  tree = render(editorApi)
  expect((flow(tree).props.nodes as Props[]).map((node) => node.type)).toEqual(['user_input', 'loop', 'loop_start'])
  expect(flow(tree).props.edges).toEqual([expect.objectContaining({ source: 'start-1', sourceHandle: 'source-a' })])

  const checklistButton = descendants(tree).find((node) =>
    typeof node.props.onClick === 'function' && String(node.props.className).includes('relative h-8 w-8'))!
  ;(checklistButton.props.onClick as () => void)()
  tree = render(editorApi)
  const checklist = descendants(tree).find((node) => node.type === 'validation-checklist')!
  expect(checklist.props.issues).toEqual([{ nodeId: 'start-1', message: 'invalid' }])
  ;(checklist.props.onSelectNode as (id: string) => void)('start-1')
  expect(setCenter).toHaveBeenCalledWith(100, 50, { zoom: 1, duration: 300 })
})

test('supports run refetch, settings, save failure recovery, and custom navigation', async () => {
  const failedUpdate = mock(async () => { throw new Error('save failed') })
  const editorApi = api({ updateWorkflow: failedUpdate })
  let tree = await settle(editorApi, { backHref: '/custom/workflows', baseUrl: '/custom/workflows/workflow-1' })

  await (findAction(tree, 'save').props.onClick as () => Promise<void>)()
  tree = render(editorApi, { backHref: '/custom/workflows', baseUrl: '/custom/workflows/workflow-1' })
  expect(findAction(tree, 'save').props.disabled).toBe(false)
  expect(toastSuccess).not.toHaveBeenCalledWith('saved')

  ;(findAction(tree, 'run').props.onClick as () => void)()
  tree = render(editorApi, { backHref: '/custom/workflows', baseUrl: '/custom/workflows/workflow-1' })
  let runDrawer = descendants(tree).find((node) => node.type === 'workflow-run-drawer')!
  expect(runDrawer.props.open).toBe(true)

  const freshWorkflow = { ...workflow, name: 'Refetched', definition: { ...workflow.definition, nodes: [] } }
  editorApi.getWorkflow.mockResolvedValueOnce(freshWorkflow)
  await (runDrawer.props.onDebugRunComplete as () => Promise<void>)()
  tree = render(editorApi, { backHref: '/custom/workflows', baseUrl: '/custom/workflows/workflow-1' })
  runDrawer = descendants(tree).find((node) => node.type === 'workflow-run-drawer')!
  expect((runDrawer.props.workflow as Props).name).toBe('Refetched')
  editorApi.getWorkflow.mockRejectedValueOnce(new Error('best effort'))
  await (runDrawer.props.onDebugRunComplete as () => Promise<void>)()

  const apiItem = descendants(tree).find((node) => node.props.onClick && text(node.props.children).includes('accessApi'))!
  ;(apiItem.props.onClick as () => void)()
  expect(push).toHaveBeenCalledWith('/custom/workflows/workflow-1/api')
})

test('enforces read-only permissions while preserving run and canvas navigation', async () => {
  currentUser = { id: 'viewer', username: 'viewer', is_superuser: false }
  currentTeam = { id: 'other-team', role: 'member' }
  const editorApi = api()
  const tree = await settle(editorApi, { allowPermissionUpdate: true, updatePermission: 'custom:update' })
  const allText = text(tree)
  const drawer = descendants(tree).find((node) => node.type === 'node-config-drawer')!

  expect(allText).toContain('run')
  expect(allText).not.toContain('save')
  expect(allText).not.toContain('publish')
  expect(drawer.props.readOnly).toBe(true)

  permissionGranted = true
  const permitted = render(editorApi, { allowPermissionUpdate: true, updatePermission: 'custom:update' })
  expect(text(permitted)).toContain('save')
  expect(descendants(permitted).find((node) => node.type === 'node-config-drawer')?.props.readOnly).toBe(false)
})

test('handles keyboard copy, paste, delete, modes, save, and listener cleanup', async () => {
  const selectedWorkflow = {
    ...workflow,
    definition: {
      nodes: [
        { ...workflow.definition.nodes[0], selected: false },
        { id: 'llm-1', type: 'llm', selected: true, position: { x: 200, y: 100 }, data: { type: 'llm', label: 'LLM', config: {} } },
      ],
      edges: [{ id: 'edge-1', source: 'start-1', target: 'llm-1' }],
    },
  }
  const editorApi = api({ getWorkflow: mock(async () => selectedWorkflow) })
  let tree = await settle(editorApi)
  const keydown = [...listeners.get('keydown')!][0] as (event: Props) => void
  const event = (key: string, extra: Props = {}) => ({
    key, ctrlKey: true, metaKey: false, shiftKey: false,
    target: { tagName: 'DIV', contentEditable: 'false' }, preventDefault: mock(() => {}), ...extra,
  })

  keydown(event('c'))
  keydown(event('v'))
  tree = render(editorApi)
  expect((flow(tree).props.nodes as Props[]).some((node) => String((node.data as Props).label).startsWith('LLM-copy'))).toBe(true)

  keydown(event('Delete', { ctrlKey: false }))
  tree = render(editorApi)
  expect((flow(tree).props.nodes as Props[]).map((node) => node.id)).toHaveLength(2)
  expect((flow(tree).props.nodes as Props[]).some((node) => node.id === 'llm-1')).toBe(false)
  expect(flow(tree).props.edges).toEqual([])

  keydown(event('3'))
  tree = render(editorApi)
  expect(flow(tree).props.selectionOnDrag).toBe(true)
  keydown(event('4'))
  tree = render(editorApi)
  expect(flow(tree).props.panOnDrag).toBe(true)

  keydown(event('s'))
  await new Promise((resolve) => setTimeout(resolve, 0))
  expect(editorApi.updateWorkflow).toHaveBeenCalled()

  const inputEvent = event('c', { target: { tagName: 'INPUT', contentEditable: 'false' } })
  keydown(inputEvent)
  expect((inputEvent.preventDefault as ReturnType<typeof mock>)).not.toHaveBeenCalled()

  cleanups.forEach((cleanup) => cleanup?.())
  expect(listeners.get('keydown')?.size ?? 0).toBe(0)
})
