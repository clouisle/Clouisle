import { beforeEach, describe, expect, mock, test } from 'bun:test'
import type { ReactNode } from 'react'

const changePassword = mock(() => Promise.resolve())
const push = mock()
let search = new URLSearchParams()
let state: unknown[] = []
let stateIndex = 0

mock.module('react/jsx-dev-runtime', () => ({
  jsxDEV: (type: unknown, props: Record<string, unknown>) => ({ type, props }),
}))
mock.module('react', () => ({
  useMemo: <T,>(factory: () => T) => factory(),
  useState: <T,>(initial: T) => {
    const index = stateIndex++
    state[index] ??= initial
    return [state[index] as T, (value: T | ((previous: T) => T)) => {
      state[index] = typeof value === 'function'
        ? (value as (previous: T) => T)(state[index] as T)
        : value
    }] as const
  },
}))
mock.module('next/navigation', () => ({
  useRouter: () => ({ push }),
  useSearchParams: () => search,
}))
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('sonner', () => ({ toast: { success: mock() } }))
mock.module('@/lib/api', () => ({ usersApi: { changePassword } }))
mock.module('@/lib/validation', () => ({
  clearValidationError: (errors: Record<string, string>, field: string) => {
    const { [field]: _, ...remaining } = errors
    return remaining
  },
  formatValidationSummaryMessage: (_field: string, message: string) => message,
  getValidationSummaryEntries: (errors: Record<string, string>) => Object.entries(errors),
  normalizeValidationErrors: () => ({}),
}))

const element = (tag: string) => ({ children, ...props }: { children?: ReactNode }) => ({ type: tag, props: { ...props, children } })
mock.module('@/components/ui/card', () => ({ Card: element('card'), CardContent: element('div'), CardDescription: element('p'), CardHeader: element('header'), CardTitle: element('h1') }))
mock.module('@/components/ui/input', () => ({ Input: element('input') }))
mock.module('@/components/ui/button', () => ({ Button: element('button') }))
mock.module('@/components/ui/label', () => ({ Label: element('label') }))
mock.module('@/components/ui/field', () => ({ FieldError: element('span') }))
mock.module('@/components/ui/alert', () => ({ Alert: element('aside'), AlertDescription: element('p') }))
mock.module('lucide-react', () => ({ AlertCircle: element('svg'), Loader2: element('svg') }))

const { default: ChangePasswordPage } = await import('./page')

type Tree = { type: unknown; props: Record<string, unknown> }

function resolve(node: ReactNode): Tree | ReactNode {
  if (!node || typeof node !== 'object' || !('type' in node)) return node
  const tree = node as Tree
  return typeof tree.type === 'function' ? resolve((tree.type as (props: Record<string, unknown>) => ReactNode)(tree.props)) : tree
}

function find(node: ReactNode, predicate: (tree: Tree) => boolean): Tree {
  const resolved = resolve(node)
  if (!resolved || typeof resolved !== 'object' || !('type' in resolved)) throw new Error('Element not found')
  const tree = resolved as Tree
  if (predicate(tree)) return tree
  const children = tree.props.children
  for (const child of Array.isArray(children) ? children : [children]) {
    try {
      return find(child as ReactNode, predicate)
    } catch {
      // Continue searching sibling elements.
    }
  }
  throw new Error('Element not found')
}

function render() {
  stateIndex = 0
  return ChangePasswordPage()
}

function change(id: string, value: string) {
  const input = find(render(), (tree) => tree.props.id === id)
  ;(input.props.onChange as (event: { target: { value: string } }) => void)({ target: { value } })
}

beforeEach(() => {
  changePassword.mockReset()
  changePassword.mockResolvedValue(undefined)
  push.mockReset()
  search = new URLSearchParams()
  state = []
})

describe('ChangePasswordPage', () => {
  test('rejects mismatched passwords before requesting a password change', async () => {
    change('currentPassword', 'current-password')
    change('newPassword', 'new-password')
    change('confirmPassword', 'different-password')

    const form = find(render(), (tree) => tree.type === 'form')
    await (form.props.onSubmit as (event: { preventDefault(): void }) => Promise<void>)({ preventDefault() {} })

    expect(changePassword).not.toHaveBeenCalled()
    expect(find(render(), (tree) => tree.props.children === 'passwordMismatch')).toBeDefined()
  })

  test('changes the password and returns to the requested destination', async () => {
    search = new URLSearchParams('redirect=/app/settings')
    change('currentPassword', 'current-password')
    change('newPassword', 'new-password')
    change('confirmPassword', 'new-password')

    const form = find(render(), (tree) => tree.type === 'form')
    await (form.props.onSubmit as (event: { preventDefault(): void }) => Promise<void>)({ preventDefault() {} })

    expect(changePassword).toHaveBeenCalledWith({
      current_password: 'current-password',
      new_password: 'new-password',
    })
    expect(push).toHaveBeenCalledWith('/app/settings')
  })
})
