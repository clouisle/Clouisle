import { beforeEach, expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown> | null) => ({ type, props: props ?? {} })
const component = (name: string) => Object.assign(function Component(props: Record<string, unknown>) { return jsx(name, props) }, { displayName: name })

type Node = { type: unknown; props: Record<string, unknown> }
type Settings = { enable_captcha: boolean; sso_enabled: boolean; sso_allow_password_login: boolean }

let state: unknown[] = []
let stateIndex = 0
let refs: Array<{ current: unknown }> = []
let refIndex = 0
const effects: Array<() => void | (() => void)> = []
const pushes: string[] = []
const storage = new Map<string, string>()

class ApiError extends Error {
  constructor(public code: number, public data?: Record<string, unknown>, private fields: Record<string, string> = {}) { super('test error') }
  isValidationError() { return Object.keys(this.fields).length > 0 }
  getFieldErrors() { return this.fields }
}

const login = mock(async (): Promise<Record<string, unknown>> => ({ access_token: 'access-token' }))
const getCurrentUser = mock(async () => ({ locale: 'en' }))
const updateProfile = mock(async () => {})
const sendVerification = mock(async () => {})
const verifyEmail = mock(async () => {})
const verifyTOTP = mock(async (): Promise<Record<string, unknown>> => ({ access_token: 'totp-token' }))
const getPublic = mock(async (): Promise<Settings> => ({ enable_captcha: false, sso_enabled: false, sso_allow_password_login: true }))
const getPublicProviders = mock(async () => [] as Array<Record<string, unknown>>)
const initiateLogin = mock(() => {})
const toastSuccess = mock(() => {})
const toastInfo = mock(() => {})

mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react', () => ({
  useCallback: <T,>(callback: T) => callback,
  useEffect: (effect: () => void | (() => void)) => effects.push(effect),
  useMemo: <T,>(factory: () => T) => factory(),
  useRef: <T,>(initial: T) => refs[refIndex++] as { current: T } || (refs[refIndex - 1] = { current: initial }) as { current: T },
  useState: <T,>(initial: T) => {
    const index = stateIndex++
    if (state[index] === undefined) state[index] = initial
    const setState = (value: T | ((current: T) => T)) => {
      state[index] = typeof value === 'function' ? (value as (current: T) => T)(state[index] as T) : value
    }
    return [state[index], setState] as const
  },
}))
mock.module('next/navigation', () => ({
  useRouter: () => ({ push: (path: string) => pushes.push(path) }),
  useSearchParams: () => ({ get: (key: string) => key === 'redirect' ? '/safe-target' : null }),
}))
mock.module('next-intl', () => ({ useLocale: () => 'fr', useTranslations: () => (key: string, values?: { seconds?: number }) => values?.seconds === undefined ? key : `${key}:${values.seconds}` }))
mock.module('next/link', () => ({ default: component('link') }))
mock.module('sonner', () => ({ toast: { success: toastSuccess, info: toastInfo } }))
mock.module('lucide-react', () => ({ Loader2: component('loader'), Mail: component('mail'), ArrowLeft: component('back'), ChevronDown: component('down') }))
mock.module('@/lib/api', () => ({
  authApi: { login, getCurrentUser, getCaptcha: mock(async () => null), completeCaptchaClick: mock(async () => null), sendVerification, verifyEmail, verifyTOTP },
  usersApi: { updateProfile },
  siteSettingsApi: { getPublic },
  ssoApi: { getPublicProviders, initiateLogin },
  ApiError,
}))
mock.module('@/lib/validation', () => ({
  clearValidationError: (errors: Record<string, string>, field: string) => Object.fromEntries(Object.entries(errors).filter(([key]) => key !== field)),
  formatValidationSummaryMessage: (field: string, message: string) => `${field}:${message}`,
  getValidationSummaryEntries: (errors: Record<string, string>, order: string[]) => order.flatMap((key) => errors[key] ? [[key, errors[key]]] : []),
}))
for (const [path, names] of Object.entries({
  '@/components/ui/input': ['Input'], '@/components/ui/button': ['Button'], '@/components/ui/field': ['FieldError'],
  '@/components/ui/label': ['Label'], '@/components/ui/input-otp': ['InputOTP', 'InputOTPGroup', 'InputOTPSlot'],
  '@/components/ui/separator': ['Separator'],
})) mock.module(path, () => Object.fromEntries(names.map((name) => [name, component(name)])))

const { LoginForm } = await import('./login-form')

function render() {
  stateIndex = 0
  refIndex = 0
  effects.length = 0
  return LoginForm() as Node
}
function findAll(node: unknown, predicate: (node: Node) => boolean): Node[] {
  if (!node || typeof node !== 'object' || !('props' in node)) return []
  const current = node as Node
  return [...(predicate(current) ? [current] : []), ...[current.props.children].flat().flatMap((child) => findAll(child, predicate))]
}
function byType(tree: Node, type: string) { return findAll(tree, (node) => (node.type as { displayName?: string })?.displayName === type) }
function hasText(node: Node, text: string) { return [node.props.children].flat().includes(text) }
async function runEffects() {
  const cleanups: Array<() => void> = []
  for (const effect of effects) {
    const cleanup = await effect()
    if (cleanup) cleanups.push(cleanup)
  }
  return cleanups
}
function enterCredentials(tree: Node) {
  const inputs = byType(tree, 'Input')
  inputs[0].props.onChange({ target: { value: 'fake-user@example.test' } })
  inputs[1].props.onChange({ target: { value: 'fake-password' } })
}
async function submit(tree: Node) {
  await findAll(tree, (node) => node.type === 'form')[0].props.onSubmit({ preventDefault: () => {} })
}

beforeEach(() => {
  state = []
  refs = []
  pushes.length = 0
  storage.clear()
  for (const fn of [login, getCurrentUser, updateProfile, sendVerification, verifyEmail, verifyTOTP, getPublic, getPublicProviders, initiateLogin, toastSuccess, toastInfo]) fn.mockReset()
  login.mockImplementation(async () => ({ access_token: 'access-token' }))
  getCurrentUser.mockImplementation(async () => ({ locale: 'en' }))
  updateProfile.mockImplementation(async () => {})
  sendVerification.mockImplementation(async () => {})
  verifyEmail.mockImplementation(async () => {})
  verifyTOTP.mockImplementation(async () => ({ access_token: 'totp-token' }))
  getPublic.mockImplementation(async () => ({ enable_captcha: false, sso_enabled: false, sso_allow_password_login: true }))
  getPublicProviders.mockImplementation(async () => [])
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: { setItem: (key: string, value: string) => storage.set(key, value) } })
})

test('validates login errors, clears fields, and initiates configured SSO', async () => {
  getPublic.mockImplementation(async () => ({ enable_captcha: false, sso_enabled: true, sso_allow_password_login: true }))
  getPublicProviders.mockImplementation(async () => [{ id: 'sso-1', name: 'fake-sso', display_name: 'Fake SSO', button_text: 'Use Fake SSO', icon_url: '/fake.svg' }])
  login.mockImplementation(async () => { throw new ApiError(422, undefined, { username: 'unknown fake user', password: 'invalid fake password' }) })

  let tree = render()
  await runEffects()
  tree = render()
  enterCredentials(tree)
  tree = render()
  await submit(tree)
  tree = render()

  expect(findAll(tree, (node) => node.type === 'img')[0].props.alt).toBe('Fake SSO')
  expect(findAll(tree, (node) => node.type === 'form')[0]).toBeDefined()
  expect(byType(tree, 'FieldError').some((node) => node.props.children === 'username:unknown fake user')).toBe(true)
  const inputs = byType(tree, 'Input')
  inputs[0].props.onChange({ target: { value: 'corrected@example.test' } })
  inputs[1].props.onChange({ target: { value: 'corrected-password' } })
  tree = render()
  expect(byType(tree, 'FieldError').some((node) => String(node.props.children).includes('unknown fake user'))).toBe(false)

  await byType(tree, 'Button').find((node) => hasText(node, 'Use Fake SSO'))!.props.onClick()
  expect(initiateLogin).toHaveBeenCalledWith('fake-sso', '/safe-target')
})

test('handles unverified email, resend, verification failure and success, then cleans up state', async () => {
  login.mockImplementation(async () => { throw new ApiError(5004, { email: 'fake-unverified@example.test' }) })
  sendVerification.mockImplementationOnce(async () => { throw new Error('fake smtp unavailable') })

  let tree = render()
  enterCredentials(tree)
  tree = render()
  await submit(tree)
  tree = render()
  expect(findAll(tree, (node) => node.type === 'span').some((node) => node.props.children === 'fake-unverified@example.test')).toBe(true)

  const manual = findAll(tree, (node) => node.type === 'button' && node.props.children?.[0] === 'orEnterCodeManually')[0]
  manual.props.onClick()
  tree = render()
  byType(tree, 'InputOTP')[0].props.onChange('123456')
  verifyEmail.mockImplementationOnce(async () => { throw new ApiError(400) })
  tree = render()
  await byType(tree, 'Button').find((node) => hasText(node, 'verifyEmail'))!.props.onClick()
  tree = render()
  expect(byType(tree, 'FieldError').some((node) => node.props.children === 'code:verificationCodeInvalid')).toBe(true)

  byType(tree, 'InputOTP')[0].props.onChange('654321')
  tree = render()
  await byType(tree, 'Button').find((node) => hasText(node, 'verifyEmail'))!.props.onClick()
  tree = render()
  expect(verifyEmail).toHaveBeenLastCalledWith('fake-unverified@example.test', '654321', 'register')
  expect(toastSuccess).toHaveBeenCalledWith('emailVerified')
  expect(findAll(tree, (node) => node.type === 'form')[0]).toBeDefined()
})

test('covers TOTP rate errors, backup interaction, success redirect, and back cleanup', async () => {
  login.mockImplementation(async () => ({ requires_totp: true, temp_token: 'fake-temp-token' }))
  let tree = render()
  enterCredentials(tree)
  tree = render()
  await submit(tree)
  tree = render()

  byType(tree, 'InputOTP')[0].props.onChange('123456')
  verifyTOTP.mockImplementationOnce(async () => { throw new ApiError(5312, { seconds: 9 }) })
  tree = render()
  await byType(tree, 'Button').find((node) => hasText(node, 'verifyCode'))!.props.onClick()
  tree = render()
  expect(byType(tree, 'FieldError').some((node) => node.props.children === 'totp:twoFactorRateLimited:9')).toBe(true)

  findAll(tree, (node) => node.type === 'button' && node.props.children === 'useBackupCode')[0].props.onClick()
  tree = render()
  byType(tree, 'Input')[0].props.onChange({ target: { value: 'ABCD-EFGH' } })
  tree = render()
  await byType(tree, 'Button').find((node) => hasText(node, 'verifyCode'))!.props.onClick()
  expect(verifyTOTP).toHaveBeenLastCalledWith('fake-temp-token', 'ABCDEFGH', true)
  expect(storage.get('access_token')).toBe('totp-token')
  expect(updateProfile).toHaveBeenCalledWith({ locale: 'fr' }, { skipAuthRedirect: true })
  expect(pushes).toEqual(['/safe-target'])

  tree = render()
  findAll(tree, (node) => node.type === 'button')[0].props.onClick()
  tree = render()
  expect(findAll(tree, (node) => node.type === 'form')[0]).toBeDefined()
})

test('runs resend cooldown timer cleanup and TOTP setup redirect', async () => {
  const originalSetTimeout = globalThis.setTimeout
  const originalClearTimeout = globalThis.clearTimeout
  let timerCallback: (() => void) | undefined
  const clearTimer = mock(() => {})
  globalThis.setTimeout = ((callback: () => void) => { timerCallback = callback; return 77 }) as unknown as typeof setTimeout
  globalThis.clearTimeout = clearTimer as unknown as typeof clearTimeout
  try {
    login.mockImplementation(async () => { throw new ApiError(5004, { email: 'cooldown@example.test' }) })
    let tree = render()
    enterCredentials(tree)
    tree = render()
    await submit(tree)
    for (let second = 60; second > 0; second--) {
      tree = render()
      const cleanups = await runEffects()
      if (second === 60) expect(timerCallback).toBeDefined()
      timerCallback!()
      cleanups.forEach((cleanup) => cleanup())
    }
    tree = render()
    await findAll(tree, (node) => node.type === 'button' && node.props.children === 'resendEmail')[0].props.onClick()
    expect(sendVerification).toHaveBeenLastCalledWith('cooldown@example.test', 'register')
    expect(clearTimer).toHaveBeenCalledWith(77)

    state = []
    login.mockImplementation(async () => ({ requires_totp_setup: true, temp_token: 'setup-temp-token' }))
    tree = render()
    enterCredentials(tree)
    tree = render()
    await submit(tree)
    expect(storage.get('temp_token')).toBe('setup-temp-token')
    expect(toastInfo).toHaveBeenCalledWith('totpSetupRequiredByAdmin')
    expect(pushes).toContain('/totp-setup')
  } finally {
    globalThis.setTimeout = originalSetTimeout
    globalThis.clearTimeout = originalClearTimeout
  }
})
