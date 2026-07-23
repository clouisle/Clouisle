import { expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
const element = function Element() {}

mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('next-intl', () => ({ useTranslations: () => (key: string, values?: Record<string, unknown>) => values ? `${key}:${Object.values(values).join('/')}` : key }))
mock.module('@xyflow/react', () => ({ Handle: element, Position: { Left: 'left', Right: 'right' } }))
mock.module('lucide-react', () => ({ Database: element, AlertCircle: element }))
mock.module('@/lib/utils', () => ({ cn: (...values: unknown[]) => values.filter(Boolean).join(' ') }))

const { KnowledgeRetrievalNode } = await import('./knowledge-retrieval-node')

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

test('renders selected configured hybrid retrieval with handles', () => {
  const tree = KnowledgeRetrievalNode({
    id: 'retrieval', selected: true,
    data: {
      type: 'knowledge_retrieval', label: 'Find context', config: {},
      knowledgeRetrievalConfig: {
        knowledgeBaseId: 'kb-1', knowledgeBaseName: 'Product docs', querySource: 'variable',
        queryVariableRef: '{{input.question}}', searchMode: 'hybrid', topK: 8, threshold: 0.6,
        outputVariable: 'results',
      },
    },
  }) as TreeNode

  expect(findAll(tree, (node) => node.props.className?.toString().includes('border-primary')).length).toBeGreaterThan(0)
  expect(findAll(tree, (node) => node.props.children === 'Find context')).toHaveLength(1)
  expect(findAll(tree, (node) => node.props.children === 'Product docs')).toHaveLength(1)
  expect(findAll(tree, (node) => text(node) === 'configKnowledgeRetrieval.searchModeHybrid')).toHaveLength(1)
  expect(findAll(tree, (node) => node.props.children === 'configKnowledgeRetrieval.topKCompact:8')).toHaveLength(1)
  expect(findAll(tree, (node) => text(node) === 'configKnowledgeRetrieval.threshold: 0.6').length).toBeGreaterThan(0)
  expect(findAll(tree, (node) => node.type === element && node.props.className === 'h-4 w-4 text-amber-500')).toHaveLength(0)
  expect(findAll(tree, (node) => node.props.type === 'target')[0].props.style).toEqual({ top: 24 })
  expect(findAll(tree, (node) => node.props.type === 'source')[0].props.position).toBe('right')
})

test('renders vector and full-text modes with constant queries', () => {
  const renderMode = (searchMode: 'vector' | 'fulltext') => KnowledgeRetrievalNode({
    id: 'retrieval', data: { type: 'knowledge_retrieval', label: '', config: {}, knowledgeRetrievalConfig: {
      knowledgeBaseId: 'kb-1', knowledgeBaseName: 'Docs', querySource: 'constant', queryConstantValue: 'query',
      searchMode, topK: 5, threshold: 0, outputVariable: 'results',
    } },
  }) as TreeNode

  expect(findAll(renderMode('vector'), (node) => text(node) === 'configKnowledgeRetrieval.searchModeVector')).toHaveLength(1)
  expect(findAll(renderMode('fulltext'), (node) => text(node) === 'configKnowledgeRetrieval.searchModeFulltext')).toHaveLength(1)
})

test('uses localized empty state and warns for missing query or knowledge base', () => {
  const missingQuery = KnowledgeRetrievalNode({
    id: 'retrieval', data: { type: 'knowledge_retrieval', label: '', config: {}, knowledgeRetrievalConfig: {
      knowledgeBaseId: 'kb-1', knowledgeBaseName: 'Docs', querySource: 'variable',
      searchMode: 'hybrid', topK: 5, threshold: 0, outputVariable: 'results',
    } },
  }) as TreeNode
  const empty = KnowledgeRetrievalNode({ id: 'retrieval', data: { type: 'knowledge_retrieval', label: '', config: {} } }) as TreeNode

  expect(findAll(missingQuery, (node) => node.type === element && node.props.className === 'h-4 w-4 text-amber-500')).toHaveLength(1)
  expect(findAll(empty, (node) => node.props.children === 'nodeLabels.knowledge_retrieval')).toHaveLength(2)
  expect(findAll(empty, (node) => node.props.children === 'nodesKnowledgeRetrieval.clickToConfigure')).toHaveLength(1)
})
