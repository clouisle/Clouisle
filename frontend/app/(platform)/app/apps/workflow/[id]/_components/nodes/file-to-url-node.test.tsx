import { expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
const element = function Element() {}

mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('next-intl', () => ({ useTranslations: () => (key: string, values?: Record<string, unknown>) => values ? `${key}:${values.count}` : key }))
mock.module('@xyflow/react', () => ({ Handle: element, Position: { Left: 'left', Right: 'right' } }))
mock.module('lucide-react', () => ({ Link: element }))
mock.module('@/lib/utils', () => ({ cn: (...values: string[]) => values.filter(Boolean).join(' ') }))

const { FileToUrlNode } = await import('./file-to-url-node')

type TreeNode = { props: Record<string, unknown> }

function findAll(node: unknown, predicate: (node: TreeNode) => boolean): TreeNode[] {
  if (Array.isArray(node)) return node.flatMap((child) => findAll(child, predicate))
  if (!node || typeof node !== 'object' || !('props' in node)) return []
  const current = node as TreeNode
  return [...(predicate(current) ? [current] : []), ...findAll(current.props.children, predicate)]
}

test('renders selected file conversion with its input count and handles', () => {
  const tree = FileToUrlNode({
    id: 'file-to-url', selected: true,
    data: {
      type: 'file_to_url', label: 'Asset URLs', config: {},
      fileToUrlConfig: {
        ensureAbsolute: true,
        inputs: [
          { id: 'image', name: 'imageUrl', sourceVariable: '{{input.image}}', sourceType: 'image' },
          { id: 'file', name: 'fileUrl', sourceVariable: '{{input.file}}', sourceType: 'file' },
        ],
      },
    },
  }) as TreeNode

  expect(findAll(tree, (node) => node.props.className?.includes('border-primary')).length).toBeGreaterThan(0)
  expect(findAll(tree, (node) => node.props.children === 'Asset URLs')).toHaveLength(1)
  expect(findAll(tree, (node) => node.props.children === 'nodesFileToUrl.inputCount:2')).toHaveLength(1)
  expect(findAll(tree, (node) => node.props.type === 'target')[0].props.position).toBe('left')
  expect(findAll(tree, (node) => node.props.type === 'source')[0].props.position).toBe('right')
})

test('uses the localized default label without an input count', () => {
  const tree = FileToUrlNode({ id: 'file-to-url', data: { type: 'file_to_url', label: '', config: {} } }) as TreeNode

  expect(findAll(tree, (node) => node.props.children === 'nodesFileToUrl.label')).toHaveLength(2)
  expect(findAll(tree, (node) => node.props.children === 'nodesFileToUrl.inputCount:0')).toHaveLength(0)
})
