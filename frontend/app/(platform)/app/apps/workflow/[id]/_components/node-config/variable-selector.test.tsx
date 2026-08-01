import { expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
const component = function Component() {}
const setSearch = mock(() => {})
let search = ''

mock.module('react', () => ({
  useState: () => [search, setSearch],
  useMemo: (factory: () => unknown) => factory(),
}))
mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('lucide-react', () => ({ Search: component }))
mock.module('next-intl', () => ({ useTranslations: () => (key: string, values?: Record<string, string>) => values ? `${key}:${values.expected}:${values.actual}` : key }))
mock.module('@/components/ui/input', () => ({ Input: component }))
mock.module('@/components/ui/popover', () => ({ Popover: component, PopoverContent: component, PopoverTrigger: component }))
mock.module('@/components/ui/scroll-area', () => ({ ScrollArea: component }))
mock.module('@/components/ui/tooltip', () => ({
  Tooltip: (props: Record<string, unknown>) => ({ type: 'tooltip', props }),
  TooltipTrigger: ({ render, children, ...props }: Record<string, unknown>) => {
    const element = render as { type?: unknown; props?: Record<string, unknown> } | undefined
    return element
      ? { type: element.type, props: { ...element.props, ...props, ...(children !== undefined ? { children } : {}) } }
      : { type: 'span', props: { ...props, children } }
  },
  TooltipContent: (props: Record<string, unknown>) => ({ type: 'tooltip-content', props }),
}))
mock.module('@/lib/utils', () => ({ cn: (...values: unknown[]) => values.filter(Boolean).join(' ') }))

const { VariableSelector } = await import('./variable-selector')

type TreeNode = { type?: unknown, props: Record<string, unknown> }

function findAll(node: unknown, predicate: (node: TreeNode) => boolean): TreeNode[] {
  if (Array.isArray(node)) return node.flatMap((child) => findAll(child, predicate))
  if (!node || typeof node !== 'object' || !('props' in node)) return []
  const current = node as TreeNode
  return [
    ...(predicate(current) ? [current] : []),
    ...findAll(current.props.children, predicate),
    ...findAll(current.props.render, predicate),
  ]
}

const variables = [
  { id: 'input.name', name: 'Name', type: 'string', typeSpec: { kind: 'string' as const }, group: 'input', groupLabel: 'Input', isSystem: false },
  { id: 'system.files', name: 'Files', type: 'files', typeSpec: { kind: 'files' as const }, group: 'system', groupLabel: 'System', isSystem: true },
]

function render(overrides: Record<string, unknown> = {}) {
  const onOpenChange = mock(() => {})
  const onSelect = mock(() => {})
  const tree = VariableSelector({ open: true, onOpenChange, onSelect, variables, ...overrides }) as TreeNode
  return { tree, onOpenChange, onSelect }
}

test('groups variables, renders selection, and forwards selection and close actions', () => {
  search = ''
  const { tree, onOpenChange, onSelect } = render({ selectedValue: '{{input.name}}', acceptType: { kind: 'string' }, triggerClassName: 'custom' })

  expect(findAll(tree, (node) => node.props.children === 'input.name')).toHaveLength(1)
  expect(findAll(tree, (node) => node.props.children === 'Input')).toHaveLength(1)
  expect(findAll(tree, (node) => node.props.children === 'System')).toHaveLength(1)
  const mismatch = findAll(tree, (node) => node.type === 'button' && String(node.props.className).includes('opacity-50'))[0]
  expect(mismatch.props.className).toContain('opacity-50')
  expect(findAll(tree, (node) => node.props.children === 'configCommon.typeMismatch:string:files')).toHaveLength(1)

  const selected = findAll(tree, (node) => node.type === 'button' && !String(node.props.className).includes('opacity-50'))[0]
  ;(selected.props.onClick as () => void)()
  expect(onSelect).toHaveBeenCalledWith(variables[0])
  expect(onOpenChange).toHaveBeenCalledWith(false)
  expect(setSearch).toHaveBeenCalledWith('')

  const popover = findAll(tree, (node) => node.type === component && node.props.open === true)[0]
  ;(popover.props.onOpenChange as (open: boolean) => void)(false)
  expect(onOpenChange).toHaveBeenLastCalledWith(false)
})

test('filters by search and reports an empty result', () => {
  search = 'missing'
  const { tree } = render({ placeholder: 'Choose one' })
  expect(findAll(tree, (node) => node.props.children === 'Choose one')).toHaveLength(1)
  expect(findAll(tree, (node) => node.props.children === 'configCommon.noMatchingVariables')).toHaveLength(1)

  const input = findAll(tree, (node) => node.type === component && node.props.placeholder === 'configCommon.searchVariable')[0]
  ;(input.props.onChange as (event: { target: { value: string } }) => void)({ target: { value: 'name' } })
  expect(setSearch).toHaveBeenCalledWith('name')
})
