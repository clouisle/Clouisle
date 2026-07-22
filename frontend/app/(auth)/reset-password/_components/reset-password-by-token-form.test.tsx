import { beforeEach, expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
const push = mock<(path: string) => void>()
const resetPasswordByToken = mock<(token: string, password: string) => Promise<void>>()
const toastSuccess = mock<(message: string) => void>()
let state: unknown[] = []
let stateIndex = 0

mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react', () => ({
  useMemo: <T,>(factory: () => T) => factory(),
  useState: <T,>(initial: T) => {
    const index = stateIndex++
    if (state[index] === undefined) state[index] = initial
    const setState = (value: T | ((current: T) => T)) => {
      state[index] = typeof value === 'function' ? (value as (current: T) => T)(state[index] as T) : value
    }
    return [state[index], setState] as const
  },
}))
mock.module('next/navigation', () => ({ useRouter: () => ({ push }) }))
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => `auth.${key}` }))
mock.module('sonner', () => ({ toast: { success: toastSuccess } }))
mock.module('@/lib/api', () => ({
  ApiError: class ApiError extends Error {
    constructor(public code: number, message: string, public data?: unknown) { super(message) }
    isValidationError() { return this.code === 1001 }
    getFieldErrorsRaw() {
      const errors = (this.data as { errors?: Record<string, string | string[]> })?.errors ?? {}
      return Object.fromEntries(Object.entries(errors).map(([key, value]) => [key, Array.isArray(value) ? value : [value]]))
    }
  },
  authApi: { resetPasswordByToken },
}))
mock.module('@/lib/validation', () => ({
  clearValidationError: (errors: Record<string, string>, key: string) => {
    const next = { ...errors }
    delete next[key]
    return next
  },
  formatValidationSummaryMessage: (_field: string, message: string) => message,
  getValidationSummaryEntries: (errors: Record<string, string>, inlineFields: string[]) =>
    Object.entries(errors).filter(([key]) => !inlineFields.includes(key)),
  normalizeValidationErrorsRaw: (error: { getFieldErrorsRaw(): Record<string, string[]> }) => error.getFieldErrorsRaw(),
}))
mock.module('@/components/ui/input', () => ({ Input: 'input' }))
mock.module('@/components/ui/button', () => ({ Button: 'button' }))
mock.module('@/components/ui/label', () => ({ Label: 'label' }))
mock.module('@/components/ui/field', () => ({ FieldError: 'field-error' }))
mock.module('lucide-react', () => ({ Loader2: 'loader', CheckCircle2: 'check', KeyRound: 'key' }))

const { ApiError } = await import('@/lib/api')
const { ResetPasswordByTokenForm } = await import('./reset-password-by-token-form')

type Node = { type?: unknown; props: Record<string, unknown> }

function render() {
  stateIndex = 0
  return ResetPasswordByTokenForm({ token: 'token-123' }) as Node
}

function findAll(node: unknown, predicate: (node: Node) => boolean): Node[] {
  if (Array.isArray(node)) return node.flatMap((child) => findAll(child, predicate))
  if (!node || typeof node !== 'object' || !('props' in node)) return []
  const current = node as Node
  return [...(predicate(current) ? [current] : []), ...findAll(current.props.children, predicate)]
}

function inputs(tree: Node) {
  return findAll(tree, (node) => node.type === 'input')
}

function text(node: unknown): string {
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (!node || typeof node !== 'object') return ''
  return text((node as Node).props?.children)
}

async function submit(tree: Node) {
  await (tree.props.onSubmit as (event: { preventDefault(): void }) => Promise<void>)({ preventDefault() {} })
}

beforeEach(() => {
  state = []
  push.mockReset()
  resetPasswordByToken.mockReset()
  resetPasswordByToken.mockImplementation(() => Promise.resolve())
  toastSuccess.mockReset()
})

test('shows password validation errors and clears them when edited', async () => {
  let tree = render()
  await submit(tree)
  tree = render()
  expect(inputs(tree)[0].props['aria-invalid']).toBe(true)
  expect(findAll(tree, (node) => node.type === 'field-error').some((node) => node.props.children === 'auth.passwordTooShort')).toBe(true)

  inputs(tree)[0].props.onChange({ target: { value: 'secret' } })
  tree = render()
  expect(inputs(tree)[0].props['aria-invalid']).toBe(false)
  inputs(tree)[1].props.onChange({ target: { value: 'different' } })
  await submit(render())
  tree = render()
  expect(inputs(tree)[1].props['aria-invalid']).toBe(true)
  expect(resetPasswordByToken).not.toHaveBeenCalled()
})

test('maps backend password errors and expired tokens to visible fields', async () => {
  state = ['secret', 'secret']
  resetPasswordByToken.mockImplementationOnce(() => Promise.reject(new ApiError(1001, 'invalid', {
    errors: { password: ['too weak', 'needs a symbol'], account: 'reset unavailable' },
  })))
  await submit(render())
  let tree = render()
  expect(findAll(tree, (node) => node.type === 'field-error').some((node) => text(node).includes('too weak; needs a symbol'))).toBe(true)

  resetPasswordByToken.mockImplementationOnce(() => Promise.reject(new ApiError(5005, 'expired')))
  await submit(tree)
  tree = render()
  expect(findAll(tree, (node) => node.type === 'field-error').some((node) => node.props.children === 'auth.verificationTokenInvalid')).toBe(true)
})

test('shows success and routes back to login after a reset', async () => {
  state = ['secret', 'secret']
  await submit(render())

  const tree = render()
  expect(resetPasswordByToken).toHaveBeenCalledWith('token-123', 'secret')
  expect(toastSuccess).toHaveBeenCalledWith('auth.passwordResetSuccess')
  expect(findAll(tree, (node) => node.type === 'button')[0].props.children).toBeDefined()
  findAll(tree, (node) => node.type === 'button')[0].props.onClick()
  expect(push).toHaveBeenCalledWith('/login')
})
