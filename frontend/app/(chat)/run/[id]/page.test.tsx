import { expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
let stateValues: unknown[] = []
const push = mock(() => {})

function Loader2() {}
function AlertCircle() {}
function Sparkles() {}
function GitBranch() {}
function ChevronDown() {}
function ChevronUp() {}
function Button() {}
function Alert() {}
function AlertDescription() {}
function AlertTitle() {}
function Collapsible() {}
function CollapsibleContent() {}
function CollapsibleTrigger() {}
function ChatContainer() {}
function ChatInput() {}
function VariableForm() {}
function Image() {}

mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({
  jsxDEV: jsx,
  Fragment: Symbol.for('react.fragment'),
}))
mock.module('react', () => ({
  useState: () => [stateValues.shift(), mock(() => {})],
  useEffect: () => {},
  useMemo: (factory: () => unknown) => factory(),
}))
mock.module('next/navigation', () => ({
  useRouter: () => ({ push }),
  useSearchParams: () => new URLSearchParams(),
}))
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('next/image', () => ({ default: Image }))
mock.module('lucide-react', () => ({
  Loader2,
  AlertCircle,
  Sparkles,
  GitBranch,
  ChevronDown,
  ChevronUp,
}))
mock.module('@/lib/api', () => ({
  ApiError: class ApiError extends Error {},
  publicAgentsApi: {},
  workflowsApi: {},
}))
mock.module('@/components/ui/button', () => ({ Button }))
mock.module('@/components/ui/alert', () => ({ Alert, AlertDescription, AlertTitle }))
mock.module('@/components/ui/collapsible', () => ({
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
}))
mock.module('@/components/chat', () => ({
  ChatContainer,
  ChatInput,
  VariableForm,
  useVariableForm: () => ({
    values: {},
    setValues: mock(() => {}),
    needsInput: false,
    isValid: true,
    fieldErrors: {},
    validate: () => true,
  }),
}))
mock.module('@/hooks/use-run', () => ({
  useRun: () => ({
    messages: [],
    isStreaming: false,
    isLoading: false,
    sendMessage: mock(() => {}),
    stop: mock(() => {}),
  }),
}))
mock.module('@/lib/utils/extract-variables', () => ({ extractVariables: () => [] }))
mock.module('@/lib/utils', () => ({
  cn: (...values: unknown[]) => values.filter(Boolean).join(' '),
}))

const { default: UnifiedRunPage } = await import('./page')

test('shows a loading indicator until run metadata and route parameters resolve', () => {
  stateValues = [null, null, true, null, '', true]
  const tree = UnifiedRunPage({ params: Promise.resolve({ id: 'run-1' }) }) as {
    props: Record<string, unknown>
  }

  expect(tree.props.className).toContain('h-screen')
  expect((tree.props.children as { type: Function }).type.name).toBe('Loader2')
})

test('shows a failure state and returns to the home page', () => {
  stateValues = [{ id: 'run-1' }, null, false, new Error('loadError'), '', true]
  const tree = UnifiedRunPage({ params: Promise.resolve({ id: 'run-1' }) }) as {
    props: Record<string, unknown>
  }
  const [alert, backButton] = tree.props.children as Array<{ props: Record<string, unknown> }>

  backButton.props.onClick()

  expect((alert.type as Function).name).toBe('Alert')
  expect(JSON.stringify(alert.props.children)).toContain('loadError')
  expect(push).toHaveBeenCalledWith('/')
})

test('renders an agent run with its emoji icon and no visible variables', () => {
  const agent = {
    id: 'agent-1',
    name: 'Weather',
    description: 'Forecast helper',
    icon: '☀️',
    avatar_url: null,
    hide_tool_calls: true,
  }
  stateValues = [{ id: 'agent-1' }, agent, false, null, '', false]
  const tree = UnifiedRunPage({ params: Promise.resolve({ id: 'agent-1' }) }) as {
    props: Record<string, unknown>
  }
  const content = JSON.stringify(tree)

  expect(tree.props.className).toContain('overflow-hidden')
  expect(content).toContain('Weather')
  expect(content).toContain('Forecast helper')
  expect(content).toContain('☀️')
})
