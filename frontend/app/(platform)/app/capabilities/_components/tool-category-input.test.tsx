import { expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
const component = function Component() {}
mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('next-intl', () => ({ useTranslations: (namespace: string) => (key: string) => `${namespace}.${key}` }))
mock.module('@/components/ui/combobox', () => ({
  Combobox: component,
  ComboboxContent: component,
  ComboboxEmpty: component,
  ComboboxInput: component,
  ComboboxItem: component,
  ComboboxList: component,
}))
mock.module('@/lib/api', () => ({
  PRESET_TOOL_CATEGORIES: ['search', 'other'],
  isPresetToolCategory: (category: string) => ['search', 'other'].includes(category),
}))

const { ToolCategoryInput } = await import('./tool-category-input')
type TreeNode = { type?: unknown, props: Record<string, unknown> }
function findAll(node: unknown, predicate: (node: TreeNode) => boolean): TreeNode[] {
  if (Array.isArray(node)) return node.flatMap((child) => findAll(child, predicate))
  if (!node || typeof node !== 'object' || !('props' in node)) return []
  const current = node as TreeNode
  return [...(predicate(current) ? [current] : []), ...findAll(current.props.children, predicate)]
}

test('labels preset categories and accepts selected and typed values', () => {
  const onChange = mock(() => {})
  const tree = ToolCategoryInput({ value: 'search', onChange, className: 'wrapper', inputClassName: 'input' }) as TreeNode
  expect(tree.props.className).toBe('wrapper')
  const combobox = findAll(tree, (node) => node.props.items)[0]
  expect(combobox.props.items).toEqual(['search', 'other'])
  expect(combobox.props.inputValue).toBe('tools.categories.search')
  expect((combobox.props.itemToStringLabel as (value: string) => string)('other')).toBe('tools.categories.other')
  ;(combobox.props.onValueChange as (value: unknown) => void)('other')
  ;(combobox.props.onValueChange as (value: unknown) => void)(null)
  ;(combobox.props.onInputValueChange as (value: string, details: { reason: string }) => void)('custom', { reason: 'input-change' })
  ;(combobox.props.onInputValueChange as (value: string, details: { reason: string }) => void)('ignored', { reason: 'item-press' })
  expect(onChange).toHaveBeenNthCalledWith(1, 'other')
  expect(onChange).toHaveBeenNthCalledWith(2, 'custom')
  expect(onChange).toHaveBeenCalledTimes(2)
  const input = findAll(tree, (node) => node.props.id === 'category')[0]
  expect(input.props.className).toBe('input')
  expect(findAll(tree, (node) => node.props.children === 'common.noResults')).toHaveLength(1)
})

test('keeps a custom category available and renders its label', () => {
  const tree = ToolCategoryInput({ id: 'custom-category', value: 'finance', onChange: mock(() => {}) }) as TreeNode
  const combobox = findAll(tree, (node) => node.props.items)[0]
  expect(combobox.props.items).toEqual(['finance', 'search', 'other'])
  expect(combobox.props.inputValue).toBe('finance')
  const renderItem = findAll(tree, (node) => typeof node.props.children === 'function')[0].props.children as (category: string) => TreeNode
  expect(renderItem('finance').props.children).toBe('finance')
  expect(renderItem('search').props.children).toBe('tools.categories.search')
  expect(findAll(tree, (node) => node.props.id === 'custom-category')).toHaveLength(1)
})
