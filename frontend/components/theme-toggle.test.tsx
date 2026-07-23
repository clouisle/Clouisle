import { expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
const setTheme = mock(() => {})
const DropdownMenuItem = function DropdownMenuItem() {}

mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('next-themes', () => ({ useTheme: () => ({ setTheme }) }))
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('lucide-react', () => ({
  Moon: function Moon() {},
  Sun: function Sun() {},
  Monitor: function Monitor() {},
}))
mock.module('@/components/ui/dropdown-menu', () => ({
  DropdownMenu: function DropdownMenu() {},
  DropdownMenuContent: function DropdownMenuContent() {},
  DropdownMenuItem,
  DropdownMenuTrigger: function DropdownMenuTrigger() {},
}))

const { ThemeToggle } = await import('./theme-toggle')

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

test('selects light, dark, and system themes', () => {
  setTheme.mockReset()
  const items = findAll(ThemeToggle(), DropdownMenuItem)

  expect(items).toHaveLength(3)
  for (const item of items) (item.props.onClick as () => void)()
  expect(setTheme.mock.calls.map(call => call[0])).toEqual(['light', 'dark', 'system'])
})
