import { expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
const element = function Element() {}

mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('next-intl', () => ({ useTranslations: () => (key: string, values?: Record<string, unknown>) => values ? `${key}:${values.n}` : key }))
mock.module('@xyflow/react', () => ({ Handle: element, Position: { Left: 'left', Right: 'right' } }))
mock.module('lucide-react', () => ({ Braces: element, Bot: element, Code: element, FileJson: element, Type: element, Hash: element, ToggleLeft: element, List: element }))
mock.module('@/lib/utils', () => ({ cn: (...values: string[]) => values.filter(Boolean).join(' ') }))

const { ParameterExtractorNode, generateJsonSchema, getExtractionMethodConfig } = await import('./parameter-extractor-node')

type TreeNode = { props: Record<string, unknown> }

function findAll(node: unknown, predicate: (node: TreeNode) => boolean): TreeNode[] {
  if (Array.isArray(node)) return node.flatMap((child) => findAll(child, predicate))
  if (!node || typeof node !== 'object' || !('props' in node)) return []
  const current = node as TreeNode
  return [...(predicate(current) ? [current] : []), ...findAll(current.props.children, predicate)]
}

test('generates JSON Schema for supported parameter types and required fields', () => {
  expect(generateJsonSchema([
    { id: 'name', name: 'name', type: 'string', description: 'Name', required: true, enum: ['A', 'B'] },
    { id: 'score', name: 'score', type: 'number', description: '', required: false },
    { id: 'active', name: 'active', type: 'boolean', description: '', required: false },
    { id: 'tags', name: 'tags', type: 'array', description: '', required: true, arrayItemType: 'string' },
    { id: 'metadata', name: 'metadata', type: 'object', description: '', required: false },
  ])).toEqual({
    name: 'extracted_parameters', strict: true,
    schema: {
      type: 'object', additionalProperties: false, required: ['name', 'tags'],
      properties: {
        name: { type: 'string', description: 'Name', enum: ['A', 'B'] },
        score: { type: 'number', description: undefined },
        active: { type: 'boolean', description: undefined },
        tags: { type: 'array', description: undefined, items: { type: 'string' } },
        metadata: { type: 'object', description: undefined },
      },
    },
  })
})

test('renders selected extraction parameters with limit, count, and handles', () => {
  const tree = ParameterExtractorNode({
    id: 'extract', selected: true,
    data: {
      type: 'parameter_extractor', label: 'Extract fields', config: {},
      parameterExtractorConfig: {
        extractionMethod: 'regex', sourceVariable: '{{input.text}}',
        parameters: [
          { id: 'one', name: 'title', type: 'string', description: '', required: true },
          { id: 'two', name: 'count', type: 'number', description: '', required: false },
          { id: 'three', name: 'enabled', type: 'boolean', description: '', required: false },
          { id: 'four', name: 'hidden', type: 'object', description: '', required: false },
        ],
      },
    },
  }) as TreeNode

  expect(findAll(tree, (node) => node.props.className?.includes('border-primary')).length).toBeGreaterThan(0)
  expect(findAll(tree, (node) => node.props.children === 'nodesParameterExtractor.methodRegexShort')).toHaveLength(1)
  expect(findAll(tree, (node) => node.props.children === 'title')).toHaveLength(1)
  expect(findAll(tree, (node) => node.props.children === 'nodesCommon.required')).toHaveLength(1)
  expect(findAll(tree, (node) => node.props.children === 'hidden')).toHaveLength(0)
  expect(findAll(tree, (node) => node.props.children === 'nodesParameterExtractor.moreParams:1')).toHaveLength(1)
  expect(findAll(tree, (node) => node.props.type === 'target')[0].props.position).toBe('left')
  expect(findAll(tree, (node) => node.props.type === 'source')[0].props.position).toBe('right')
})

test('uses translated extraction metadata and the default configuration prompt', () => {
  const methods = getExtractionMethodConfig((key) => `translated:${key}`)
  const tree = ParameterExtractorNode({ id: 'extract', data: { type: 'parameter_extractor', label: '', config: {} } }) as TreeNode

  expect(methods.llm.label).toBe('translated:nodesParameterExtractor.methodLlmLabel')
  expect(methods.regex.sourceVariableTypes).toEqual(['String'])
  expect(methods.json_path.defaultType).toBe('object')
  expect(findAll(tree, (node) => node.props.children === 'nodesParameterExtractor.label')).toHaveLength(2)
  expect(findAll(tree, (node) => node.props.children === 'nodesParameterExtractor.clickToConfigure')).toHaveLength(1)
})
