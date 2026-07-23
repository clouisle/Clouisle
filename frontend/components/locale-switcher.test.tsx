import { expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
const changeLocale = mock(() => {})
const DropdownMenuItem = function DropdownMenuItem() {}
const DropdownMenuTrigger = function DropdownMenuTrigger() {}

mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('next-intl', () => ({
  useLocale: () => 'en',
  useTranslations: () => (key: string) => key,
}))
mock.module('lucide-react', () => ({ Globe: function Globe() {} }))
mock.module('@/hooks/use-locale-change', () => ({ useLocaleChange: () => ({ changeLocale }) }))
mock.module('@/components/ui/dropdown-menu', () => ({
  DropdownMenu: function DropdownMenu() {},
  DropdownMenuContent: function DropdownMenuContent() {},
  DropdownMenuItem,
  DropdownMenuTrigger,
}))

const { LocaleSwitcher } = await import('./locale-switcher')

type Tree = { type: unknown; props: Record<string, unknown> }

function findAll(node: unknown, type: unknown): Tree[] {
  if (Array.isArray(node)) return node.flatMap(child => findAll(child, type))
  if (!node || typeof node !== 'object' || !('type' in node)) return []
  const tree = node as Tree
  return [
    ...(tree.type === type ? [tree] : []),
    ...findAll(tree.props.children, type),
  ]
}

test('renders the optional current-language label and changes locale', () => {
  changeLocale.mockReset()
  const tree = LocaleSwitcher({ showLabel: true })
  const trigger = findAll(tree, DropdownMenuTrigger)[0]
  const button = (trigger.props.render as (props: Record<string, unknown>) => Tree)({ id: 'language' })
  const items = findAll(tree, DropdownMenuItem)

  expect(JSON.stringify(button)).toContain('English')
  expect(items.map(item => item.props.className)).toEqual(['bg-accent', ''])
  for (const item of items) (item.props.onClick as () => void)()
  expect(changeLocale.mock.calls.map(call => call[0])).toEqual(['en', 'zh'])
})
