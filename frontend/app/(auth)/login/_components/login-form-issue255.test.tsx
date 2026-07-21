import { beforeEach, expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown> | null) => ({ type, props: props ?? {} })
const component = (name: string) => Object.assign(function Component(props: Record<string, unknown>) { return jsx(name, props) }, { displayName: name })

let state: unknown[] = []
let stateIndex = 0
let refs: Array<{ current: unknown }> = []
let refIndex = 0
const effects: Array<() => void | (() => void)> = []
const pushes: string[] = []
const storage = new Map<string, string>()

const login = mock(async () => ({ access_token: 'test-token' }))
const getCurrentUser = mock(async () => ({ locale: 'en' }))
const getCaptcha = mock(async () => ({
  captcha_id: 'captcha-1',
  challenge: JSON.stringify({ type: 'click-choice', options: ['A'], created_at: 1 }),
  prompt: 'Choose',
  expires_in: 60,
}))
const completeCaptchaClick = mock(async () => ({ captcha_id: 'captcha-1', captcha_token: 'proof' }))
const getPublic = mock(async () => ({ enable_captcha: false, sso_enabled: false, sso_allow_password_login: true }))
const initiateLogin = mock(() => {})
const toastSuccess = mock(() => {})

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
  useSearchParams: () => ({ get: (key: string) => key === 'redirect' ? '/app/target' : null }),
}))
mock.module('next-intl', () => ({ useLocale: () => 'en', useTranslations: () => (key: string) => key }))
mock.module('next/link', () => ({ default: component('link') }))
mock.module('sonner', () => ({ toast: { success: toastSuccess, info: mock(() => {}) } }))
mock.module('lucide-react', () => ({ Loader2: component('loader'), Mail: component('mail'), ArrowLeft: component('back'), ChevronDown: component('down') }))
mock.module('@/lib/api', () => ({
  authApi: { login, getCurrentUser, getCaptcha, completeCaptchaClick, sendVerification: mock(async () => {}), verifyEmail: mock(async () => {}), verifyTOTP: mock(async () => ({ access_token: 'totp-token' })) },
  usersApi: { updateProfile: mock(async () => {}) },
  siteSettingsApi: { getPublic },
  ssoApi: { getPublicProviders: mock(async () => []), initiateLogin },
  ApiError: class ApiError extends Error {},
}))
mock.module('@/lib/validation', () => ({
  clearValidationError: (errors: Record<string, string>, field: string) => Object.fromEntries(Object.entries(errors).filter(([key]) => key !== field)),
  formatValidationSummaryMessage: (_field: string, message: string) => message,
  getValidationSummaryEntries: (errors: Record<string, string>) => Object.entries(errors),
}))
for (const [path, names] of Object.entries({
  '@/components/ui/input': ['Input'], '@/components/ui/button': ['Button'], '@/components/ui/field': ['FieldError'],
  '@/components/ui/label': ['Label'], '@/components/ui/input-otp': ['InputOTP', 'InputOTPGroup', 'InputOTPSlot'],
  '@/components/ui/separator': ['Separator'],
})) mock.module(path, () => Object.fromEntries(names.map((name) => [name, component(name)])))

const { LoginForm } = await import('./login-form')
type Node = { type: unknown; props: Record<string, unknown> }

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
async function runEffects() { for (const effect of effects) await effect() }

beforeEach(() => {
  state = []
  refs = []
  pushes.length = 0
  storage.clear()
  login.mockClear()
  getCurrentUser.mockClear()
  getCaptcha.mockClear()
  completeCaptchaClick.mockClear()
  getPublic.mockReset()
  getPublic.mockImplementation(async () => ({ enable_captcha: false, sso_enabled: false, sso_allow_password_login: true }))
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: { setItem: (key: string, value: string) => storage.set(key, value), getItem: (key: string) => storage.get(key) ?? null } })
})

test('runs login field callbacks, pointer tracing, submit, and redirect', async () => {
  let tree = render()
  await runEffects()
  tree = render()

  const inputs = byType(tree, 'Input')
  inputs[0].props.onChange({ target: { value: 'test-user' } })
  inputs[1].props.onChange({ target: { value: 'not-a-real-password' } })
  tree = render()
  const form = findAll(tree, (node) => node.type === 'form')[0]
  const target = { getBoundingClientRect: () => ({ left: 10, top: 20, width: 200, height: 50 }) }
  form.props.onPointerEnter({ currentTarget: target, clientX: 30, clientY: 45 })
  form.props.onPointerMove({ currentTarget: target, clientX: 50, clientY: 48 })
  form.props.onPointerDown({ currentTarget: target, clientX: 50, clientY: 48 })
  form.props.onPointerUp({ currentTarget: target, clientX: 50, clientY: 48 })
  await form.props.onSubmit({ preventDefault: () => {} })

  expect(login).toHaveBeenCalledWith({ username: 'test-user', password: 'not-a-real-password', captcha_id: undefined, captcha_token: undefined })
  expect(storage.get('access_token')).toBe('test-token')
  expect(toastSuccess).toHaveBeenCalledWith('loginSuccess')
  expect(pushes).toEqual(['/app/target'])
})

test('loads and completes captcha including keyboard trace callback', async () => {
  getPublic.mockImplementation(async () => ({ enable_captcha: true, sso_enabled: false, sso_allow_password_login: true }))
  let tree = render()
  await runEffects()
  tree = render()
  const inputs = byType(tree, 'Input')
  inputs[0].props.onChange({ target: { value: 'captcha-user' } })
  inputs[1].props.onChange({ target: { value: 'password' } })
  render()
  await runEffects()
  tree = render()

  const captchaButton = byType(tree, 'Button').find((node) => node.props.type === 'button')!
  const target = { getBoundingClientRect: () => ({ left: 0, top: 0, width: 200, height: 60 }) }
  captchaButton.props.onKeyDown({ key: 'Enter', currentTarget: target })
  await captchaButton.props.onClick()
  tree = render()

  expect(getCaptcha).toHaveBeenCalled()
  expect(completeCaptchaClick).toHaveBeenCalledWith(expect.objectContaining({ captcha_id: 'captcha-1', clicked_option: 'A' }))
  expect((completeCaptchaClick.mock.calls[0][0] as { pointer: unknown[] }).pointer).toHaveLength(7)
  expect(byType(tree, 'Button').some((node) => node.props.variant === 'secondary')).toBe(true)
})
