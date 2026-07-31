import { expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
let stateValues: unknown[] = []
let searchParams = new URLSearchParams()

function Loader2() {}
function AgentRunPage() {}
function WorkflowRunPage() {}

mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({
  jsxDEV: jsx,
  Fragment: Symbol.for('react.fragment'),
}))
mock.module('react', () => ({
  useState: () => [stateValues.shift(), mock(() => {})],
  useEffect: () => {},
}))
mock.module('next/navigation', () => ({
  useSearchParams: () => searchParams,
}))
mock.module('lucide-react', () => ({ Loader2 }))
mock.module('./_components/agent-run-page', () => ({ AgentRunPage }))
mock.module('./_components/workflow-run-page', () => ({ WorkflowRunPage }))

const { default: UnifiedRunPage } = await import('./page')

test('shows a loading indicator until route parameters resolve', () => {
  stateValues = [null]
  const tree = UnifiedRunPage({ params: Promise.resolve({ id: 'run-1' }) }) as {
    props: Record<string, unknown>
  }

  expect(tree.props.className).toContain('h-screen')
  expect((tree.props.children as { type: { name?: string } }).type.name).toBe('Loader2')
})

test('defaults to the Agent runner for missing or invalid types', () => {
  stateValues = [{ id: 'agent-1' }]
  searchParams = new URLSearchParams('type=invalid')
  const tree = UnifiedRunPage({ params: Promise.resolve({ id: 'agent-1' }) }) as {
    type: unknown
    props: Record<string, unknown>
  }

  expect(tree.type).toBe(AgentRunPage)
  expect(tree.props.id).toBe('agent-1')
})

test('dispatches workflow routes without interpreting debug parameters', () => {
  stateValues = [{ id: 'workflow-1' }]
  searchParams = new URLSearchParams('type=workflow&debug=true')
  const tree = UnifiedRunPage({ params: Promise.resolve({ id: 'workflow-1' }) }) as {
    type: unknown
    props: Record<string, unknown>
  }

  expect(tree.type).toBe(WorkflowRunPage)
  expect(tree.props).toEqual({ id: 'workflow-1' })
})
