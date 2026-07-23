import { expect, test, mock } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
const element = function Element() {}

mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('@xyflow/react', () => ({ Handle: element, Position: { Right: 'right' } }))
mock.module('lucide-react', () => ({ Zap: element, Type: element, AlignLeft: element, ListChecks: element, Hash: element, CheckSquare: element, File: element, Image: element, Files: element, Images: element }))
mock.module('@/lib/utils', () => ({ cn: (...values: string[]) => values.filter(Boolean).join(' ') }))

const { TriggerNode } = await import('./trigger-node')

function findAll(node: unknown, predicate: (node: { props: Record<string, unknown> }) => boolean): Array<{ props: Record<string, unknown> }> {
  if (!node || typeof node !== 'object' || !('props' in node)) return []
  const current = node as { props: Record<string, unknown> }
  return [...(predicate(current) ? [current] : []), ...[current.props.children].flat().flatMap((child) => findAll(child, predicate))]
}

test('renders selected trigger with required parameter metadata', () => {
  const tree = TriggerNode({ selected: true, data: { type: 'trigger', label: 'Start', parameters: [{ id: 'input', name: 'Prompt', type: 'paragraph', required: true }, { id: 'optional', name: 'Skip', type: 'text', required: false }], config: {} } }) as { props: Record<string, unknown> }

  expect(findAll(tree, (node) => node.props.className?.includes('border-primary')).length).toBeGreaterThan(0)
  expect(findAll(tree, (node) => node.props.children === 'Prompt')).toHaveLength(1)
  expect(findAll(tree, (node) => node.props.children === 'Skip')).toHaveLength(0)
  expect(findAll(tree, (node) => node.props.type === 'source')[0].props.position).toBe('right')
})

test('omits parameter section without required inputs', () => {
  const tree = TriggerNode({ data: { type: 'trigger', label: 'Start', parameters: [{ id: 'optional', name: 'Skip', type: 'text', required: false }], config: {} } }) as { props: Record<string, unknown> }

  expect(findAll(tree, (node) => node.props.children === 'Skip')).toHaveLength(0)
})
