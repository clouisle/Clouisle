import { beforeEach, expect, mock, test } from 'bun:test'

type Props = Record<string, unknown>
type TestNode = { type: unknown; props: Props }
type StateRecord = { value: unknown; set: (value: unknown) => void }

const jsx = (type: unknown, props: Props = {}): TestNode => ({ type, props })
const element = (props: Props) => jsx('element', props)
globalThis.window = {
  addEventListener: () => {}, removeEventListener: () => {}, innerWidth: 1200, innerHeight: 800,
} as never
const push = mock(() => {})
const router = { push }
const toastError = mock(() => {})
const toastSuccess = mock(() => {})
const getCurrentUser = mock(async () => ({ id: 'user-1', username: 'owner', is_superuser: false }))
const validateWorkflow = mock(() => [])
const screenToFlowPosition = mock(({ x, y }: { x: number; y: number }) => ({ x, y }))
const fitView = mock(() => {})
const setCenter = mock(() => {})

let states: StateRecord[] = []
let dependencies: (unknown[] | undefined)[] = []
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
      dependencies[index] = deps
      effect()
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
mock.module('@/components/permission-guard', () => ({ useCanPerform: () => ({ canPerform: () => false }) }))
mock.module('@/contexts/team-context', () => ({ useTeam: () => ({ currentTeam: { id: 'team-1', role: 'member' } }) }))

mock.module('@/components/ui/button', () => ({ Button: element }))
mock.module('@/components/ui/skeleton', () => ({ Skeleton: element }))
mock.module('@/components/ui/dropdown-menu', () => ({
  DropdownMenu: element, DropdownMenuContent: element, DropdownMenuItem: element, DropdownMenuTrigger: element,
}))
mock.module('@/components/ui/alert-dialog', () => ({
  AlertDialog: element, AlertDialogAction: element, AlertDialogCancel: element, AlertDialogContent: element,
  AlertDialogDescription: element, AlertDialogFooter: element, AlertDialogHeader: element, AlertDialogTitle: element,
}))
mock.module('@/components/ui/tooltip', () => ({ Tooltip: element, TooltipTrigger: element, TooltipContent: element }))

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

function render(editorApi: ReturnType<typeof api>) {
  cursor = 0
  return WorkflowEditorContent({ workflowId: 'workflow-1', api: editorApi as never }) as TestNode
}

async function settle(editorApi: ReturnType<typeof api>) {
  render(editorApi)
  await new Promise((resolve) => setTimeout(resolve, 0))
  return render(editorApi)
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
  states = []
  dependencies = []
  cursor = 0
  nodes = []
  edges = []
  push.mockClear()
  toastError.mockClear()
  toastSuccess.mockClear()
  getCurrentUser.mockClear()
  validateWorkflow.mockClear()
  onNodesChangeBase.mockClear()
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
