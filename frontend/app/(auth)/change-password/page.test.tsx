import { beforeEach, describe, expect, mock, test } from 'bun:test'
import type { ReactNode } from 'react'

const changePassword = mock(() => Promise.resolve())
const push = mock()
const success = mock()
let search = new URLSearchParams()
let normalizedErrors: Record<string, string> = {}
let state: unknown[] = []
let stateIndex = 0

mock.module('react/jsx-dev-runtime', () => ({
  jsxDEV: (type: unknown, props: Record<string, unknown>) => ({ type, props }),
}))
mock.module('react/jsx-runtime', () => ({
  jsx: (type: unknown, props: Record<string, unknown>) => ({ type, props }),
  jsxs: (type: unknown, props: Record<string, unknown>) => ({ type, props }),
  Fragment: 'fragment',
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
mock.module('sonner', () => ({ toast: { success } }))
mock.module('@/lib/api', () => ({ usersApi: { changePassword } }))
mock.module('@/lib/validation', () => ({
  clearValidationError: (errors: Record<string, string>, field: string) => {
    const { [field]: removed, ...remaining } = errors
    void removed
    return remaining
  },
  formatValidationSummaryMessage: (_field: string, message: string) => message,
  getValidationSummaryEntries: (errors: Record<string, string>) => Object.entries(errors),
  normalizeValidationErrors: () => normalizedErrors,
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

async function submit() {
  const form = find(render(), (tree) => tree.type === 'form')
  await (form.props.onSubmit as (event: { preventDefault(): void }) => Promise<void>)({ preventDefault() {} })
}

beforeEach(() => {
  changePassword.mockReset()
  changePassword.mockResolvedValue(undefined)
  push.mockReset()
  success.mockReset()
  search = new URLSearchParams()
  normalizedErrors = {}
  state = []
})

describe('ChangePasswordPage', () => {
  test('rejects mismatched passwords before requesting a password change', async () => {
    change('currentPassword', 'current-password')
    change('newPassword', 'new-password')
    change('confirmPassword', 'different-password')

    await submit()

    expect(changePassword).not.toHaveBeenCalled()
    expect(find(render(), (tree) => tree.props.children === 'passwordMismatch')).toBeDefined()
  })

  test('changes the password and returns to the requested destination', async () => {
    search = new URLSearchParams('redirect=/app/settings')
    change('currentPassword', 'current-password')
    change('newPassword', 'new-password')
    change('confirmPassword', 'new-password')

    await submit()

    expect(changePassword).toHaveBeenCalledWith({
      current_password: 'current-password',
      new_password: 'new-password',
    })
    expect(success).toHaveBeenCalledWith('password_changed')
    expect(push).toHaveBeenCalledWith('/app/settings')
  })

  test('shows expired-password copy and falls back to the app redirect', async () => {
    search = new URLSearchParams('reason=expired')
    change('currentPassword', 'current-password')
    change('newPassword', 'new-password')
    change('confirmPassword', 'new-password')

    expect(find(render(), (tree) => tree.props.children === 'passwordExpired')).toBeDefined()

    await submit()

    expect(push).toHaveBeenCalledWith('/app')
  })

  test('shows forced-change defaults and password input boundaries', () => {
    const tree = render()

    expect(find(tree, (node) => node.props.children === 'forcePasswordChange')).toBeDefined()
    for (const id of ['currentPassword', 'newPassword', 'confirmPassword']) {
      const input = find(tree, (node) => node.props.id === id)
      expect(input.props.type).toBe('password')
      expect(input.props.required).toBe(true)
      expect(input.props.autoComplete).toBe(id === 'currentPassword' ? 'current-password' : 'new-password')
    }
  })

  test('shows the force-change alert for a non-expiration reason', () => {
    search = new URLSearchParams('reason=force')

    const alert = find(render(), (tree) => tree.type === 'aside')
    expect(find(alert, (tree) => tree.props.children === 'forcePasswordChangeDescription')).toBeDefined()
  })

  test('shows normalized API errors and clears each error when its field changes', async () => {
    normalizedErrors = {
      current_password: 'current password is wrong',
      new_password: 'new password is weak',
      confirmPassword: 'confirmation is invalid',
    }
    changePassword.mockRejectedValue(new Error('invalid password'))
    change('currentPassword', 'bad-password')
    change('newPassword', 'new-password')
    change('confirmPassword', 'new-password')

    await submit()

    expect(push).not.toHaveBeenCalled()
    for (const [id, message] of [
      ['currentPassword', 'current password is wrong'],
      ['newPassword', 'new password is weak'],
      ['confirmPassword', 'confirmation is invalid'],
    ]) {
      expect(find(render(), (tree) => tree.props.children === message)).toBeDefined()
      expect(find(render(), (tree) => tree.props.id === id).props['aria-invalid']).toBe(true)
      change(id, 'corrected-password')
      expect(find(render(), (tree) => tree.props.id === id).props['aria-invalid']).toBe(false)
    }
  })

  test('disables submission and shows progress while the API request is pending', async () => {
    let resolveRequest: (() => void) | undefined
    changePassword.mockImplementation(() => new Promise<void>((resolve) => { resolveRequest = resolve }))
    change('currentPassword', 'current-password')
    change('newPassword', 'new-password')
    change('confirmPassword', 'new-password')

    const pending = submit()
    await Promise.resolve()

    const button = find(render(), (tree) => tree.type === 'button')
    expect(button.props.disabled).toBe(true)
    expect(find(button, (tree) => tree.type === 'svg').props.className).toContain('animate-spin')

    resolveRequest!()
    await pending
    expect(find(render(), (tree) => tree.type === 'button').props.disabled).toBe(false)
  })
})
