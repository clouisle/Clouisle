import { beforeEach, describe, expect, mock, test } from 'bun:test'
import type { ReactNode } from 'react'

interface TestNode {
  type: unknown
  props: Record<string, unknown>
}

const jsx = (type: unknown, props: Record<string, unknown> = {}): TestNode => ({ type, props })
const noop = () => {}
globalThis.window = { addEventListener: noop, removeEventListener: noop } as never
let routeParams = { id: 'workflow-1' }
let pathname = '/app/apps/workflow/workflow-1/logs'

function resolve(value: unknown): unknown {
  if (!value || typeof value !== 'object' || !('type' in value)) return value
  const node = value as TestNode
  return typeof node.type === 'function'
    ? resolve((node.type as (props: Record<string, unknown>) => unknown)(node.props))
    : node
}

function descendants(value: unknown): TestNode[] {
  if (Array.isArray(value)) return value.flatMap(descendants)
  const resolved = resolve(value)
  if (!resolved || typeof resolved !== 'object' || !('props' in resolved)) return []
  const node = resolved as TestNode
  return [node, ...descendants(node.props.children)]
}

function createIcon(name: string) {
  return (props: Record<string, unknown>) => jsx(name, props)
}

mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react-dom', () => ({ createPortal: (children: ReactNode) => children }))
mock.module('react', () => ({
  default: {
    useCallback: (fn: unknown) => fn,
    useEffect: (effect: () => void) => effect(),
    useMemo: (factory: () => unknown) => factory(),
    useRef: (value: unknown) => ({ current: value }),
    useState: (value: unknown) => [value, noop],
  },
  useCallback: (fn: unknown) => fn,
  useEffect: (effect: () => void) => effect(),
  useMemo: (factory: () => unknown) => factory(),
  useRef: (value: unknown) => ({ current: value }),
  useState: (value: unknown) => [value, noop],
  useLayoutEffect: (effect: () => void) => effect(),
  useId: () => 'react-id',
  useReducer: (_reducer: unknown, initial: unknown) => [initial, noop],
  useSyncExternalStore: (_subscribe: unknown, getSnapshot: () => unknown) => getSnapshot(),
  useImperativeHandle: () => {},
  useTransition: () => [false, (cb: () => void) => cb()],
  createContext: () => ({ Provider: ({ children }: { children: unknown }) => children }),
  createElement: (type: unknown, props: Record<string, unknown> | null, ...children: unknown[]) =>
    jsx(type, { ...(props ?? {}), ...(children.length ? { children: children.length === 1 ? children[0] : children } : {}) }),
}))
mock.module('next/navigation', () => ({
  useParams: () => routeParams,
  usePathname: () => pathname,
  useRouter: () => ({ push: noop, replace: noop, back: noop, refresh: noop }),
}))
mock.module('next-intl', () => ({
  useLocale: () => 'en',
  useTranslations: (namespace?: string) => (key: string) => (namespace ? `${namespace}.${key}` : key),
}))
mock.module('next/link', () => ({ default: ({ children, ...props }: { children?: ReactNode }) => jsx('next-link', { ...props, children }) }))
mock.module('next/image', () => ({ default: (props: Record<string, unknown>) => jsx('next-image', props) }))
mock.module('streamdown', () => ({ Streamdown: ({ children, ...props }: { children?: ReactNode }) => jsx('streamdown', { ...props, children }) }))
mock.module('sonner', () => ({ toast: { success: noop, error: noop } }))
mock.module('@xyflow/react', () => ({
  Background: (props: Record<string, unknown>) => jsx('flow-background', props),
  BackgroundVariant: { Dots: 'dots' },
  Controls: (props: Record<string, unknown>) => jsx('flow-controls', props),
  Handle: (props: Record<string, unknown>) => jsx('flow-handle', props),
  MarkerType: { ArrowClosed: 'arrowclosed' },
  MiniMap: (props: Record<string, unknown>) => jsx('flow-minimap', props),
  Panel: ({ children, ...props }: { children?: ReactNode }) => jsx('flow-panel', { ...props, children }),
  Position: { Left: 'left', Right: 'right', Top: 'top', Bottom: 'bottom' },
  SelectionMode: { Partial: 'partial', Full: 'full' },
  ReactFlow: ({ children, ...props }: { children?: ReactNode }) => jsx('react-flow', { ...props, children }),
  ReactFlowProvider: ({ children, ...props }: { children?: ReactNode }) => jsx('react-flow-provider', { ...props, children }),
  addEdge: (edge: unknown) => edge,
  applyEdgeChanges: (_changes: unknown, edges: unknown[]) => edges,
  applyNodeChanges: (_changes: unknown, nodes: unknown[]) => nodes,
  useEdgesState: (initial: unknown[]) => [initial, noop, noop],
  useNodesState: (initial: unknown[]) => [initial, noop, noop],
  useReactFlow: () => ({ fitView: noop, getNodes: () => [], getEdges: () => [], setNodes: noop, setEdges: noop }),
  useViewport: () => ({ x: 0, y: 0, zoom: 1 }),
}))
mock.module('@xyflow/react/dist/style.css', () => ({}))
mock.module('lucide-react', () => ({
  Activity: createIcon('Activity'),
  AlertCircle: createIcon('AlertCircle'),
  AlertTriangle: createIcon('AlertTriangle'),
  AlignLeft: createIcon('AlignLeft'),
  ArrowLeft: createIcon('ArrowLeft'),
  ArrowRight: createIcon('ArrowRight'),
  Ban: createIcon('Ban'),
  Bot: createIcon('Bot'),
  Braces: createIcon('Braces'),
  Brackets: createIcon('Brackets'),
  Bug: createIcon('Bug'),
  Calculator: createIcon('Calculator'),
  Calendar: createIcon('Calendar'),
  ChartColumn: createIcon('ChartColumn'),
  Check: createIcon('Check'),
  CheckCircle: createIcon('CheckCircle'),
  CheckCircle2: createIcon('CheckCircle2'),
  CheckSquare: createIcon('CheckSquare'),
  ChevronDown: createIcon('ChevronDown'),
  ChevronLeft: createIcon('ChevronLeft'),
  ChevronRight: createIcon('ChevronRight'),
  ChevronUp: createIcon('ChevronUp'),
  ClipboardCheck: createIcon('ClipboardCheck'),
  Clock: createIcon('Clock'),
  Clock3: createIcon('Clock3'),
  Code: createIcon('Code'),
  Code2: createIcon('Code2'),
  Combine: createIcon('Combine'),
  Copy: createIcon('Copy'),
  Database: createIcon('Database'),
  Download: createIcon('Download'),
  Edit3: createIcon('Edit3'),
  ExternalLink: createIcon('ExternalLink'),
  File: createIcon('File'),
  FileJson: createIcon('FileJson'),
  FileText: createIcon('FileText'),
  Files: createIcon('Files'),
  FolderOpen: createIcon('FolderOpen'),
  GitBranch: createIcon('GitBranch'),
  Globe: createIcon('Globe'),
  GlobeLock: createIcon('GlobeLock'),
  GripVertical: createIcon('GripVertical'),
  Hand: createIcon('Hand'),
  Hash: createIcon('Hash'),
  HelpCircle: createIcon('HelpCircle'),
  History: createIcon('History'),
  Home: createIcon('Home'),
  Image: createIcon('Image'),
  Images: createIcon('Images'),
  Infinity: createIcon('Infinity'),
  Info: createIcon('Info'),
  LayoutGrid: createIcon('LayoutGrid'),
  Link: createIcon('Link'),
  List: createIcon('List'),
  ListChecks: createIcon('ListChecks'),
  Loader2: createIcon('Loader2'),
  LogOut: createIcon('LogOut'),
  Maximize: createIcon('Maximize'),
  Maximize2: createIcon('Maximize2'),
  Merge: createIcon('Merge'),
  MessageSquareText: createIcon('MessageSquareText'),
  Minus: createIcon('Minus'),
  MousePointer2: createIcon('MousePointer2'),
  Pencil: createIcon('Pencil'),
  Play: createIcon('Play'),
  Plus: createIcon('Plus'),
  PlusCircle: createIcon('PlusCircle'),
  RefreshCw: createIcon('RefreshCw'),
  Save: createIcon('Save'),
  Search: createIcon('Search'),
  Settings: createIcon('Settings'),
  Settings2: createIcon('Settings2'),
  Sparkles: createIcon('Sparkles'),
  StickyNote: createIcon('StickyNote'),
  StopCircle: createIcon('StopCircle'),
  Tags: createIcon('Tags'),
  ToggleLeft: createIcon('ToggleLeft'),
  Trash2: createIcon('Trash2'),
  Type: createIcon('Type'),
  Variable: createIcon('Variable'),
  Video: createIcon('Video'),
  Workflow: createIcon('Workflow'),
  Wrench: createIcon('Wrench'),
  X: createIcon('X'),
  XCircle: createIcon('XCircle'),
  Zap: createIcon('Zap'),
  ZoomIn: createIcon('ZoomIn'),
  ZoomOut: createIcon('ZoomOut'),
}))
mock.module('@/lib/utils', () => ({ cn: (...values: unknown[]) => values.filter(Boolean).join(' ') }))
mock.module('@/lib/api/client', () => ({
  api: { get: async () => ({}), post: async () => ({}), put: async () => ({}), delete: async () => ({}) },
  axiosInstance: { get: async () => ({}), post: async () => ({}), put: async () => ({}), delete: async () => ({}) },
  ApiError: class ApiError extends Error {},
  getErrorMessage: () => 'api-error',
}))
mock.module('@/lib/api/auth', () => ({ authApi: { getUsers: async () => [] } }))
mock.module('@/lib/api/workflows', () => ({
  workflowsApi: {
    getWorkflow: async () => workflow,
    getWorkflowRuns: async () => ({ items: [], total: 0 }),
    getWorkflowRun: async () => run,
    getNodeExecutions: async () => [],
    debugWorkflow: async () => run,
    updateWorkflow: async () => workflow,
    publishWorkflow: async () => workflow,
    unpublishWorkflow: async () => workflow,
  },
}))
mock.module('@/components/permission-guard', () => ({ useCanPerform: () => true }))
mock.module('@/contexts/team-context', () => ({ useTeam: () => ({ currentTeam: { id: 'team-1' } }) }))

mock.module('@/components/ui/button', () => ({ Button: ({ children, ...props }: { children?: ReactNode }) => jsx('button', { ...props, children }), buttonVariants: () => 'button-variants' }))
mock.module('@/components/ui/input', () => ({ Input: (props: Record<string, unknown>) => jsx('input', props) }))
mock.module('@/components/ui/label', () => ({ Label: ({ children, ...props }: { children?: ReactNode }) => jsx('label', { ...props, children }) }))
mock.module('@/components/ui/textarea', () => ({ Textarea: (props: Record<string, unknown>) => jsx('textarea', props) }))
mock.module('@/components/ui/scroll-area', () => ({ ScrollArea: ({ children, ...props }: { children?: ReactNode }) => jsx('scroll-area', { ...props, children }) }))
mock.module('@/components/ui/skeleton', () => ({ Skeleton: (props: Record<string, unknown>) => jsx('skeleton', props) }))
mock.module('@/components/ui/switch', () => ({ Switch: (props: Record<string, unknown>) => jsx('switch', props) }))
mock.module('@/components/ui/badge', () => ({ Badge: ({ children, ...props }: { children?: ReactNode }) => jsx('badge', { ...props, children }) }))
mock.module('@/components/ui/tooltip', () => ({
  Tooltip: ({ children, ...props }: { children?: ReactNode }) => jsx('tooltip', { ...props, children }),
  TooltipContent: ({ children, ...props }: { children?: ReactNode }) => jsx('tooltip-content', { ...props, children }),
  TooltipTrigger: ({ children, ...props }: { children?: ReactNode }) => jsx('tooltip-trigger', { ...props, children }),
}))
mock.module('@/components/ui/tabs', () => ({
  Tabs: ({ children, ...props }: { children?: ReactNode }) => jsx('tabs', { ...props, children }),
  TabsList: ({ children, ...props }: { children?: ReactNode }) => jsx('tabs-list', { ...props, children }),
  TabsTrigger: ({ children, ...props }: { children?: ReactNode }) => jsx('tabs-trigger', { ...props, children }),
  TabsContent: ({ children, ...props }: { children?: ReactNode }) => jsx('tabs-content', { ...props, children }),
}))
mock.module('@/components/ui/select', () => ({
  Select: ({ children, ...props }: { children?: ReactNode }) => jsx('select', { ...props, children }),
  SelectContent: ({ children, ...props }: { children?: ReactNode }) => jsx('select-content', { ...props, children }),
  SelectItem: ({ children, ...props }: { children?: ReactNode }) => jsx('select-item', { ...props, children }),
  SelectTrigger: ({ children, ...props }: { children?: ReactNode }) => jsx('select-trigger', { ...props, children }),
  SelectValue: (props: Record<string, unknown>) => jsx('select-value', props),
}))
mock.module('@/components/ui/dialog', () => ({
  Dialog: ({ children, ...props }: { children?: ReactNode }) => jsx('dialog', { ...props, children }),
  DialogContent: ({ children, ...props }: { children?: ReactNode }) => jsx('dialog-content', { ...props, children }),
  DialogDescription: ({ children, ...props }: { children?: ReactNode }) => jsx('dialog-description', { ...props, children }),
  DialogFooter: ({ children, ...props }: { children?: ReactNode }) => jsx('dialog-footer', { ...props, children }),
  DialogHeader: ({ children, ...props }: { children?: ReactNode }) => jsx('dialog-header', { ...props, children }),
  DialogTitle: ({ children, ...props }: { children?: ReactNode }) => jsx('dialog-title', { ...props, children }),
}))
mock.module('@/components/ui/dropdown-menu', () => ({
  DropdownMenu: ({ children, ...props }: { children?: ReactNode }) => jsx('dropdown-menu', { ...props, children }),
  DropdownMenuContent: ({ children, ...props }: { children?: ReactNode }) => jsx('dropdown-menu-content', { ...props, children }),
  DropdownMenuItem: ({ children, ...props }: { children?: ReactNode }) => jsx('dropdown-menu-item', { ...props, children }),
  DropdownMenuTrigger: ({ children, ...props }: { children?: ReactNode }) => jsx('dropdown-menu-trigger', { ...props, children }),
}))
mock.module('@/components/ui/alert-dialog', () => ({
  AlertDialog: ({ children, ...props }: { children?: ReactNode }) => jsx('alert-dialog', { ...props, children }),
  AlertDialogAction: ({ children, ...props }: { children?: ReactNode }) => jsx('alert-dialog-action', { ...props, children }),
  AlertDialogCancel: ({ children, ...props }: { children?: ReactNode }) => jsx('alert-dialog-cancel', { ...props, children }),
  AlertDialogContent: ({ children, ...props }: { children?: ReactNode }) => jsx('alert-dialog-content', { ...props, children }),
  AlertDialogDescription: ({ children, ...props }: { children?: ReactNode }) => jsx('alert-dialog-description', { ...props, children }),
  AlertDialogFooter: ({ children, ...props }: { children?: ReactNode }) => jsx('alert-dialog-footer', { ...props, children }),
  AlertDialogHeader: ({ children, ...props }: { children?: ReactNode }) => jsx('alert-dialog-header', { ...props, children }),
  AlertDialogTitle: ({ children, ...props }: { children?: ReactNode }) => jsx('alert-dialog-title', { ...props, children }),
}))
mock.module('@/components/ui/field', () => ({ FieldError: (props: Record<string, unknown>) => jsx('field-error', props) }))
mock.module('@/hooks/use-debounce', () => ({ useDebounce: (value: unknown) => value }))
mock.module('@/app/(dashboard)/activities/_components/workflow-run-drawer', () => ({ WorkflowRunDrawer: (props: Record<string, unknown>) => jsx('dashboard-workflow-run-drawer', props) }))


const defaultNodeConfig = {}
mock.module('./nodes/user-input-node', () => ({ UserInputNode: (props: Record<string, unknown>) => jsx('user-input-node', props) }))
mock.module('./nodes/trigger-node', () => ({ TriggerNode: (props: Record<string, unknown>) => jsx('trigger-node', props) }))
mock.module('./nodes/llm-node', () => ({ LLMNode: (props: Record<string, unknown>) => jsx('llm-node', props) }))
mock.module('./nodes/media-generation-node', () => ({ MediaGenerationNode: (props: Record<string, unknown>) => jsx('media-generation-node', props), defaultMediaGenerationConfig: defaultNodeConfig }))
mock.module('./nodes/condition-node', () => ({ ConditionNode: (props: Record<string, unknown>) => jsx('condition-node', props), ConditionBranch: {} }))
mock.module('./nodes/sub-workflow-node', () => ({ SubWorkflowNode: (props: Record<string, unknown>) => jsx('sub-workflow-node', props) }))
mock.module('./nodes/agent-node', () => ({ AgentNode: (props: Record<string, unknown>) => jsx('agent-node', props) }))
mock.module('./nodes/tool-node', () => ({ ToolNode: (props: Record<string, unknown>) => jsx('tool-node', props), defaultToolNodeConfig: defaultNodeConfig }))
mock.module('./nodes/knowledge-retrieval-node', () => ({ KnowledgeRetrievalNode: (props: Record<string, unknown>) => jsx('knowledge-retrieval-node', props) }))
mock.module('./nodes/iteration-node', () => ({ IterationNode: (props: Record<string, unknown>) => jsx('iteration-node', props), IterationStartNode: (props: Record<string, unknown>) => jsx('iteration-start-node', props), IterationExitNode: (props: Record<string, unknown>) => jsx('iteration-exit-node', props), defaultIterationConfig: defaultNodeConfig }))
mock.module('./nodes/loop-node', () => ({ LoopNode: (props: Record<string, unknown>) => jsx('loop-node', props), LoopStartNode: (props: Record<string, unknown>) => jsx('loop-start-node', props), LoopExitNode: (props: Record<string, unknown>) => jsx('loop-exit-node', props), defaultLoopConfig: defaultNodeConfig }))
mock.module('./nodes/code-node', () => ({ CodeNode: (props: Record<string, unknown>) => jsx('code-node', props), defaultCodeConfig: defaultNodeConfig }))
mock.module('./nodes/template-node', () => ({ TemplateNode: (props: Record<string, unknown>) => jsx('template-node', props), defaultTemplateConfig: defaultNodeConfig }))
mock.module('./nodes/file-to-url-node', () => ({ FileToUrlNode: (props: Record<string, unknown>) => jsx('file-to-url-node', props), defaultFileToUrlConfig: defaultNodeConfig }))
mock.module('./nodes/variable-aggregator-node', () => ({ VariableAggregatorNode: (props: Record<string, unknown>) => jsx('variable-aggregator-node', props), defaultVariableAggregatorConfig: defaultNodeConfig, aggregationModeOutputTypes: {} }))
mock.module('./nodes/variable-assignment-node', () => ({ VariableAssignmentNode: (props: Record<string, unknown>) => jsx('variable-assignment-node', props), defaultVariableAssignmentConfig: defaultNodeConfig }))
mock.module('./nodes/parameter-extractor-node', () => ({ ParameterExtractorNode: (props: Record<string, unknown>) => jsx('parameter-extractor-node', props), defaultParameterExtractorConfig: defaultNodeConfig }))
mock.module('./nodes/question-classifier-node', () => ({ QuestionClassifierNode: (props: Record<string, unknown>) => jsx('question-classifier-node', props), defaultQuestionClassifierConfig: defaultNodeConfig }))
mock.module('./nodes/answer-node', () => ({ AnswerNode: (props: Record<string, unknown>) => jsx('answer-node', props), defaultAnswerNodeConfig: defaultNodeConfig }))
mock.module('./nodes/comment-node', () => ({ CommentNode: (props: Record<string, unknown>) => jsx('comment-node', props), COMMENT_COLORS: ['yellow'] }))
mock.module('./start-node-selector', () => ({ StartNodeSelector: (props: Record<string, unknown>) => jsx('start-node-selector', props), StartNodeType: { Trigger: 'trigger' } }))
mock.module('./workflow-settings-drawer', () => ({ WorkflowSettingsDrawer: (props: Record<string, unknown>) => jsx('workflow-settings-drawer', props) }))
mock.module('./add-node-popover', () => ({ AddNodePopover: (props: Record<string, unknown>) => jsx('add-node-popover', props) }))
mock.module('./workflow-publish-dialog', () => ({ WorkflowPublishDialog: (props: Record<string, unknown>) => jsx('workflow-publish-dialog', props) }))
mock.module('./validation-checklist', () => ({ ValidationChecklist: (props: Record<string, unknown>) => jsx('validation-checklist', props) }))
mock.module('./workflow-validator', () => ({ validateWorkflow: () => [], ValidationIssue: {} }))
mock.module('../../[id]/_components/embed-config-dialog', () => ({ EmbedConfigDialog: (props: Record<string, unknown>) => jsx('embed-config-dialog', props) }))
mock.module('./node-output-renderer', () => ({
  nodeStatusConfig: {},
  renderNodeOutput: (value: unknown) => jsx('node-output', { value }),
}))
mock.module('./node-config', () => ({
  Parameter: {},
  AvailableVariable: {},
  nodeTypeInfo: {},
  systemParameters: [],
  defaultStartParameters: [],
  getTypeName: (type: string) => type,
  getLoopVarTypeName: (type: string) => type,
  LLMNodeConfigData: {},
  defaultLLMNodeConfig: defaultNodeConfig,
  defaultSubWorkflowNodeConfig: defaultNodeConfig,
  defaultAgentNodeConfig: defaultNodeConfig,
  defaultKnowledgeRetrievalNodeConfig: defaultNodeConfig,
  NodeConfigPanel: (props: Record<string, unknown>) => jsx('node-config-panel', props),
  StartNodeConfig: (props: Record<string, unknown>) => jsx('StartNodeConfig', props),
  LLMNodeConfig: (props: Record<string, unknown>) => jsx('LLMNodeConfig', props),
  MediaGenerationNodeConfig: (props: Record<string, unknown>) => jsx('MediaGenerationNodeConfig', props),
  CodeNodeConfig: (props: Record<string, unknown>) => jsx('CodeNodeConfig', props),
  ConditionNodeConfig: (props: Record<string, unknown>) => jsx('ConditionNodeConfig', props),
  IterationNodeConfig: (props: Record<string, unknown>) => jsx('IterationNodeConfig', props),
  LoopNodeConfig: (props: Record<string, unknown>) => jsx('LoopNodeConfig', props),
  TemplateNodeConfig: (props: Record<string, unknown>) => jsx('TemplateNodeConfig', props),
  FileToUrlNodeConfig: (props: Record<string, unknown>) => jsx('FileToUrlNodeConfig', props),
  VariableAggregatorNodeConfig: (props: Record<string, unknown>) => jsx('VariableAggregatorNodeConfig', props),
  VariableAssignmentNodeConfig: (props: Record<string, unknown>) => jsx('VariableAssignmentNodeConfig', props),
  ParameterExtractorNodeConfig: (props: Record<string, unknown>) => jsx('ParameterExtractorNodeConfig', props),
  QuestionClassifierNodeConfig: (props: Record<string, unknown>) => jsx('QuestionClassifierNodeConfig', props),
  AnswerNodeConfig: (props: Record<string, unknown>) => jsx('AnswerNodeConfig', props),
  ToolNodeConfig: (props: Record<string, unknown>) => jsx('ToolNodeConfig', props),
  ParameterEditDialog: (props: Record<string, unknown>) => jsx('ParameterEditDialog', props),
  CodeInputDialog: (props: Record<string, unknown>) => jsx('CodeInputDialog', props),
  SubWorkflowNodeConfig: (props: Record<string, unknown>) => jsx('SubWorkflowNodeConfig', props),
  AgentNodeConfig: (props: Record<string, unknown>) => jsx('AgentNodeConfig', props),
  KnowledgeRetrievalNodeConfig: (props: Record<string, unknown>) => jsx('KnowledgeRetrievalNodeConfig', props),
}))
mock.module('./node-config/configs', () => ({ NODE_CONFIGS: {} }))

const workflow = {
  id: 'workflow-1', team_id: 'team-1', name: 'Coverage Flow', description: 'test', icon: null,
  definition: { nodes: [], edges: [] }, variables: [], status: 'draft', visibility: 'private', version: 1,
  trigger_type: 'manual', trigger_config: {}, run_count: 0, success_count: 0, fail_count: 0,
  created_by_id: 'user-1', created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z',
}
const run = {
  id: 'run-1', workflow_id: 'workflow-1', trigger_type: 'manual', is_debug: true, status: 'success',
  inputs: {}, outputs: {}, depth: 0, created_at: '2026-01-01T00:00:00Z', total_nodes: 0,
  executed_nodes: 0, failed_nodes: 0, skipped_nodes: 0, total_token_usage: {},
}

const [{ default: WorkflowEditorPage, WorkflowEditorContent }, { default: WorkflowLogsPage }, { WorkflowRunDrawer }, { NodeConfigDrawer }] = await Promise.all([
  import('../page'),
  import('../logs/page'),
  import('./workflow-run-drawer'),
  import('./node-config-drawer'),
])

beforeEach(() => {
  routeParams = { id: 'workflow-1' }
  pathname = '/app/apps/workflow/workflow-1/logs'
})

describe('workflow route coverage imports', () => {
  test('imports workflow editor and logs pages into LCOV', () => {
    expect(typeof WorkflowEditorPage).toBe('function')
    expect(typeof WorkflowLogsPage).toBe('function')
    expect(WorkflowEditorPage()).toBeDefined()
    expect(WorkflowLogsPage()).toBeDefined()
  })

  test('renders the editor content shell with the route workflow', () => {
    const tree = WorkflowEditorContent({ workflow: workflow as never, users: [] }) as TestNode
    const nodes = descendants(tree)

    expect(nodes.length).toBeGreaterThan(0)
    expect(nodes.some((node) => String(node.props.className).includes('h-full'))).toBe(true)
  })

  test('keeps drawer closed branches cheap but covered', () => {
    const runDrawer = WorkflowRunDrawer({ workflow: workflow as never, variables: [], open: false, onClose: noop }) as TestNode
    expect(runDrawer.props.className).toContain('pointer-events-none')
    expect(NodeConfigDrawer({ node: null, allNodes: [], allEdges: [], open: false, onClose: noop, onUpdate: noop })).toBeNull()
  })
})
