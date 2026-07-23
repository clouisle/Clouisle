import { beforeEach, expect, mock, test } from 'bun:test'
import type { ReactNode } from 'react'

const setters = [mock(), mock()]
let stateIndex = 0

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react', () => ({
  useState: (initial: unknown) => [initial, setters[stateIndex++]],
}))

const element = (type: string) => ({ children, ...props }: { children?: ReactNode }) =>
  jsx(type, { ...props, children })

mock.module('next/image', () => ({ default: element('image') }))
mock.module('@/components/example', () => ({
  Example: element('example'),
  ExampleWrapper: element('example-wrapper'),
}))

for (const [path, names] of [
  ['@/components/ui/alert-dialog', ['AlertDialog', 'AlertDialogAction', 'AlertDialogCancel', 'AlertDialogContent', 'AlertDialogDescription', 'AlertDialogFooter', 'AlertDialogHeader', 'AlertDialogMedia', 'AlertDialogTitle', 'AlertDialogTrigger']],
  ['@/components/ui/badge', ['Badge']],
  ['@/components/ui/button', ['Button']],
  ['@/components/ui/card', ['Card', 'CardAction', 'CardContent', 'CardDescription', 'CardFooter', 'CardHeader', 'CardTitle']],
  ['@/components/ui/combobox', ['Combobox', 'ComboboxContent', 'ComboboxEmpty', 'ComboboxInput', 'ComboboxItem', 'ComboboxList']],
  ['@/components/ui/dropdown-menu', ['DropdownMenu', 'DropdownMenuCheckboxItem', 'DropdownMenuContent', 'DropdownMenuGroup', 'DropdownMenuItem', 'DropdownMenuLabel', 'DropdownMenuPortal', 'DropdownMenuRadioGroup', 'DropdownMenuRadioItem', 'DropdownMenuSeparator', 'DropdownMenuShortcut', 'DropdownMenuSub', 'DropdownMenuSubContent', 'DropdownMenuSubTrigger', 'DropdownMenuTrigger']],
  ['@/components/ui/field', ['Field', 'FieldGroup', 'FieldLabel']],
  ['@/components/ui/input', ['Input']],
  ['@/components/ui/select', ['Select', 'SelectContent', 'SelectGroup', 'SelectItem', 'SelectTrigger', 'SelectValue']],
  ['@/components/ui/textarea', ['Textarea']],
] as const) {
  mock.module(path, () => Object.fromEntries(names.map((name) => [name, element(name)])))
}
mock.module('lucide-react', () => Object.fromEntries([
  'PlusIcon', 'BluetoothIcon', 'MoreVerticalIcon', 'FileIcon', 'FolderIcon',
  'FolderOpenIcon', 'FileCodeIcon', 'MoreHorizontalIcon', 'FolderSearchIcon',
  'SaveIcon', 'DownloadIcon', 'EyeIcon', 'LayoutIcon', 'PaletteIcon', 'SunIcon',
  'MoonIcon', 'MonitorIcon', 'UserIcon', 'CreditCardIcon', 'SettingsIcon',
  'KeyboardIcon', 'LanguagesIcon', 'BellIcon', 'MailIcon', 'ShieldIcon',
  'HelpCircleIcon', 'FileTextIcon', 'LogOutIcon',
].map((name) => [name, element(name)])))

const { ComponentExample } = await import('./component-example')

type Tree = { type: unknown; props: Record<string, unknown> }

function descendants(node: ReactNode): Tree[] {
  if (Array.isArray(node)) return node.flatMap(descendants)
  if (!node || typeof node !== 'object' || !('type' in node)) return []
  const tree = node as Tree
  if (typeof tree.type === 'function') {
    return descendants((tree.type as (props: Record<string, unknown>) => ReactNode)(tree.props))
  }
  return [tree, ...descendants(tree.props.children as ReactNode)]
}

beforeEach(() => {
  stateIndex = 0
  setters.forEach((setter) => setter.mockClear())
})

test('updates notification and theme state through menu callbacks', () => {
  const nodes = descendants(ComponentExample())
  const checkedChanges = nodes
    .map((node) => node.props.onCheckedChange)
    .filter((callback): callback is (checked: unknown) => void => typeof callback === 'function')
  const themeChange = nodes.find((node) => typeof node.props.onValueChange === 'function')
    ?.props.onValueChange as (theme: string) => void

  checkedChanges[0](false)
  checkedChanges[1](true)
  checkedChanges[2]('indeterminate')
  checkedChanges[3](true)
  themeChange('dark')

  expect(setters[0].mock.calls.map(([value]) => value)).toEqual([
    { email: false, sms: false, push: true },
    { email: true, sms: true, push: true },
    { email: true, sms: false, push: false },
    { email: true, sms: false, push: true },
  ])
  expect(setters[1]).toHaveBeenCalledWith('dark')
})
