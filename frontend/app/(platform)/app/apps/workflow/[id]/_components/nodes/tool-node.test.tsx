import { expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
const element = function Element() {}

mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('next-intl', () => ({ useTranslations: () => (key: string, values?: Record<string, unknown>) => values ? `${key}:${Object.values(values).join('/')}` : key }))
mock.module('@xyflow/react', () => ({ Handle: element, Position: { Left: 'left', Right: 'right' } }))
mock.module('lucide-react', () => ({ Wrench: element, AlertCircle: element, Clock3: element, Calculator: element, Search: element, Globe: element, FolderOpen: element, Code2: element, Link: element, ChartColumn: element }))
mock.module('@/lib/api', () => ({ isPresetToolCategory: (category: string) => ['time', 'math', 'search', 'web', 'file', 'code', 'sandbox', 'api', 'data', 'other'].includes(category) }))
mock.module('@/lib/utils', () => ({ cn: (...values: unknown[]) => values.filter(Boolean).join(' ') }))

const { ToolNode, defaultToolNodeConfig } = await import('./tool-node')

type TreeNode = { type?: unknown, props: Record<string, unknown> }

function findAll(node: unknown, predicate: (node: TreeNode) => boolean): TreeNode[] {
  if (Array.isArray(node)) return node.flatMap((child) => findAll(child, predicate))
  if (!node || typeof node !== 'object' || !('props' in node)) return []
  const current = node as TreeNode
  return [...(predicate(current) ? [current] : []), ...findAll(current.props.children, predicate)]
}

function text(node: unknown): string {
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (Array.isArray(node)) return node.map(text).join('')
  if (node && typeof node === 'object' && 'props' in node) return text((node as TreeNode).props.children)
  return ''
}

test('renders selected builtin tool with category and required parameter status', () => {
  const tree = ToolNode({
    id: 'tool', selected: true,
    data: {
      type: 'tool', label: 'Search docs', config: {},
      toolConfig: {
        toolId: 'search', toolType: 'builtin', toolDisplayName: 'Document search',
        toolDescription: 'Find documents', toolCategory: 'search', outputVariable: 'result',
        parameterMappings: [
          { name: 'query', type: 'string', required: true, source: 'variable', variableRef: '' },
          { name: 'limit', type: 'number', required: true, source: 'constant', constantValue: '10' },
          { name: 'scope', type: 'string', required: false, source: 'constant' },
        ],
      },
    },
  }) as TreeNode

  expect(findAll(tree, (node) => node.props.className?.toString().includes('border-primary')).length).toBeGreaterThan(0)
  expect(findAll(tree, (node) => node.props.children === 'Search docs')).toHaveLength(1)
  expect(findAll(tree, (node) => node.props.children === 'Document search')).toHaveLength(1)
  expect(findAll(tree, (node) => node.props.children === 'Find documents')).toHaveLength(1)
  expect(findAll(tree, (node) => node.props.children === 'nodesTool.typeBuiltin')).toHaveLength(1)
  expect(findAll(tree, (node) => node.props.children === 'nodesTool.configured:2/3')).toHaveLength(1)
  expect(findAll(tree, (node) => node.props.type === 'target')[0].props.style).toEqual({ top: 24 })
  expect(findAll(tree, (node) => node.props.type === 'source')[0].props.position).toBe('right')
})

test('renders configured MCP tool details and complete parameters', () => {
  const tree = ToolNode({
    id: 'tool',
    data: {
      type: 'tool', label: '', config: {},
      toolConfig: {
        toolName: 'server', toolType: 'mcp', toolDisplayName: 'GitHub Server',
        mcpToolName: 'search_code', mcpToolDescription: 'Search repositories', toolIcon: '🔎',
        outputVariable: 'result', parameterMappings: [
          { name: 'query', type: 'string', required: true, source: 'variable', variableRef: '{{input.query}}' },
        ],
      },
    },
  }) as TreeNode

  expect(findAll(tree, (node) => node.props.children === 'nodesTool.label')).toHaveLength(2)
  expect(findAll(tree, (node) => node.props.children === '🔎')).toHaveLength(1)
  expect(findAll(tree, (node) => node.props.children === 'search_code')).toHaveLength(1)
  expect(findAll(tree, (node) => text(node) === 'via GitHub Server').length).toBeGreaterThan(0)
  expect(findAll(tree, (node) => node.props.children === 'Search repositories')).toHaveLength(1)
  expect(findAll(tree, (node) => node.props.children === 'MCP')).toHaveLength(1)
  expect(findAll(tree, (node) => node.props.children === 'nodesTool.configured:1/1')).toHaveLength(1)
})

test('shows custom type, MCP selection warning, and the default empty state', () => {
  const custom = ToolNode({
    id: 'tool', data: { type: 'tool', label: '', config: {}, toolConfig: {
      toolId: 'custom', toolType: 'custom', toolDisplayName: 'Formatter', toolCategory: 'special', parameterMappings: [], outputVariable: 'result',
    } },
  }) as TreeNode
  const pending = ToolNode({
    id: 'tool', data: { type: 'tool', label: '', config: {}, toolConfig: {
      toolName: 'server', toolType: 'mcp', toolDisplayName: 'MCP Server', parameterMappings: [], outputVariable: 'result',
    } },
  }) as TreeNode
  const empty = ToolNode({ id: 'tool', data: { type: 'tool', label: '', config: {} } }) as TreeNode

  expect(findAll(custom, (node) => node.props.children === 'nodesTool.typeCustom')).toHaveLength(1)
  expect(findAll(pending, (node) => node.props.children === 'nodesTool.selectToolFrom:MCP Server')).toHaveLength(1)
  expect(findAll(pending, (node) => node.type === element && node.props.className === 'h-4 w-4 text-amber-500')).toHaveLength(1)
  expect(defaultToolNodeConfig).toEqual({ toolType: 'builtin', parameterMappings: [], outputVariable: 'result' })
  expect(findAll(empty, (node) => node.props.children === 'nodesTool.clickToConfigure')).toHaveLength(1)
})
