import { beforeEach, describe, expect, mock, test } from 'bun:test'
import type { ReactNode } from 'react'

const resetPasswordByToken = mock(() => Promise.resolve())
const push = mock()
const toastSuccess = mock()
let state: unknown[] = []
let stateIndex = 0

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx }))
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
mock.module('next/navigation', () => ({ useRouter: () => ({ push }) }))
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('sonner', () => ({ toast: { success: toastSuccess } }))

class ApiError extends Error {
  constructor(public code: number, message: string, public data?: unknown) {
    super(message)
  }

  isValidationError() {
    return this.code === 1001
  }
}

mock.module('@/lib/api', () => ({ authApi: { resetPasswordByToken }, ApiError }))
mock.module('@/lib/validation', () => ({
  clearValidationError: (errors: Record<string, string>, field: string) => {
    const { [field]: removed, ...remaining } = errors
    void removed
    return remaining
  },
  formatValidationSummaryMessage: (_field: string, message: string) => message,
  getValidationSummaryEntries: (errors: Record<string, string>, inline: string[]) =>
    Object.entries(errors).filter(([field]) => !inline.includes(field)),
  normalizeValidationErrorsRaw: (error: ApiError) => {
    const data = error.data as { errors?: Record<string, string | string[]> } | undefined
    return Object.fromEntries(Object.entries(data?.errors ?? {}).map(([field, messages]) => [
      field,
      Array.isArray(messages) ? messages : [messages],
    ]))
  },
}))

const element = (tag: string) => ({ children, ...props }: { children?: ReactNode }) => ({
  type: tag,
  props: { ...props, children },
})
mock.module('@/components/ui/input', () => ({ Input: element('input') }))
mock.module('@/components/ui/button', () => ({ Button: element('button') }))
mock.module('@/components/ui/label', () => ({ Label: element('label') }))
mock.module('@/components/ui/field', () => ({ FieldError: element('span') }))
mock.module('lucide-react', () => ({
  CheckCircle2: element('svg'),
  KeyRound: element('svg'),
  Loader2: element('svg'),
}))

const { ResetPasswordByTokenForm } = await import('./reset-password-by-token-form')

type Tree = { type: unknown; props: Record<string, unknown> }

function resolve(node: ReactNode): Tree | ReactNode {
  if (!node || typeof node !== 'object' || !('type' in node)) return node
  const tree = node as Tree
  return typeof tree.type === 'function'
    ? resolve((tree.type as (props: Record<string, unknown>) => ReactNode)(tree.props))
    : tree
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
  return ResetPasswordByTokenForm({ token: 'reset-token' })
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
  resetPasswordByToken.mockReset()
  resetPasswordByToken.mockResolvedValue(undefined)
  push.mockReset()
  toastSuccess.mockReset()
  state = []
})

describe('ResetPasswordByTokenForm', () => {
  test('presents accessible password fields and rejects an invalid confirmation', async () => {
    const newPassword = find(render(), (tree) => tree.props.id === 'newPassword')
    const confirmation = find(render(), (tree) => tree.props.id === 'confirmPassword')

    expect(find(render(), (tree) => tree.props.htmlFor === 'newPassword').props.children).toBe('newPassword')
    expect(find(render(), (tree) => tree.props.htmlFor === 'confirmPassword').props.children).toBe('confirmNewPassword')
    expect(newPassword.props).toMatchObject({ type: 'password', required: true, placeholder: 'newPasswordPlaceholder' })
    expect(confirmation.props).toMatchObject({ type: 'password', required: true, placeholder: 'confirmPasswordPlaceholder' })

    change('newPassword', 'secure-password')
    change('confirmPassword', 'different-password')
    await submit()

    expect(resetPasswordByToken).not.toHaveBeenCalled()
    expect(find(render(), (tree) => tree.props.children === 'passwordMismatch')).toBeDefined()
    expect(find(render(), (tree) => tree.props.id === 'confirmPassword').props['aria-invalid']).toBe(true)
  })

  test('submits the token payload, shows success, and returns to login', async () => {
    change('newPassword', 'secure-password')
    change('confirmPassword', 'secure-password')
    await submit()

    expect(resetPasswordByToken).toHaveBeenCalledWith('reset-token', 'secure-password')
    expect(toastSuccess).toHaveBeenCalledWith('passwordResetSuccess')
    expect(find(render(), (tree) => tree.props.children === 'passwordResetComplete')).toBeDefined()
    expect(find(render(), (tree) => tree.props.children === 'passwordResetSuccessMessage')).toBeDefined()

    const login = find(render(), (tree) => tree.props.children?.[1] === 'goToLogin')
    ;(login.props.onClick as () => void)()
    expect(push).toHaveBeenCalledWith('/login')
  })

  test('shows invalid-token and backend password validation errors', async () => {
    change('newPassword', 'secure-password')
    change('confirmPassword', 'secure-password')
    resetPasswordByToken.mockRejectedValueOnce(new ApiError(5005, 'invalid token'))
    await submit()
    expect(find(render(), (tree) => tree.props.children === 'verificationTokenInvalid')).toBeDefined()

    resetPasswordByToken.mockRejectedValueOnce(new ApiError(1001, 'validation', {
      errors: { password: ['Password is compromised'] },
    }))
    await submit()
    expect(find(render(), (tree) => tree.props.children === 'Password is compromised')).toBeDefined()
    expect(find(render(), (tree) => tree.props.id === 'newPassword').props['aria-invalid']).toBe(true)
  })
})
