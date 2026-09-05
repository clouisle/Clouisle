/* eslint-disable @typescript-eslint/no-explicit-any -- JSX module mocks use lightweight element shapes. */
import { describe, expect, mock, test } from 'bun:test'
import path from 'node:path'

const authRoot = path.join(import.meta.dir)
const navigation = {
  push: mock(() => {}),
  replace: mock(() => {}),
  searchParams: new URLSearchParams(),
}
const t = (key: string) => key
const getTranslations = mock(async () => t)
const fetchMock = mock()

mock.module('next/navigation', () => ({
  useRouter: () => navigation,
  useSearchParams: () => navigation.searchParams,
}))
mock.module('next-intl', () => ({ useTranslations: () => t, useLocale: () => 'en' }))
mock.module('next-intl/server', () => ({ getTranslations }))
mock.module('next/link', () => ({ default: ({ children, ...props }: any) => ({ type: 'a', props: { ...props, children } }) }))
mock.module('react', () => ({
  useEffect: (effect: () => void) => effect(),
  useMemo: (value: () => unknown) => value(),
  useState: (value: unknown) => [value, mock(() => {})],
}))
const jsxDEV = (type: any, props: any) => typeof type === 'function' ? type(props) : ({ type, props })
mock.module('react/jsx-dev-runtime', () => ({ Fragment: Symbol.for('react.fragment'), jsxDEV }))
mock.module('react/jsx-runtime', () => ({ Fragment: Symbol.for('react.fragment'), jsx: jsxDEV, jsxs: jsxDEV }))
mock.module('sonner', () => ({ toast: { success: mock(() => {}), error: mock(() => {}) } }))
mock.module('lucide-react', () => ({
  AlertCircle: () => null,
  CheckCircle2: () => null,
  Loader2: () => null,
  XCircle: () => null,
}))
mock.module('@/components/ui/card', () => ({
  Card: ({ children, ...props }: any) => ({ type: 'card', props: { ...props, children } }),
  CardContent: ({ children, ...props }: any) => ({ type: 'content', props: { ...props, children } }),
  CardDescription: ({ children, ...props }: any) => ({ type: 'description', props: { ...props, children } }),
  CardFooter: ({ children, ...props }: any) => ({ type: 'footer', props: { ...props, children } }),
  CardHeader: ({ children, ...props }: any) => ({ type: 'header', props: { ...props, children } }),
  CardTitle: ({ children, ...props }: any) => ({ type: 'title', props: { ...props, children } }),
}))
mock.module('@/components/ui/button', () => ({ Button: ({ children, ...props }: any) => ({ type: 'button', props: { ...props, children } }) }))
mock.module('@/components/totp-setup-wizard-forced', () => ({
  TOTPSetupWizardForced: (props: any) => ({ type: 'totp-wizard', props }),
}))
mock.module('@/lib/api', () => ({
  ApiError: class ApiError extends Error {},
  authApi: { getCurrentUser: mock(async () => ({ locale: 'en' })), verifyEmailByToken: mock(async () => {}) },
  usersApi: { updateProfile: mock(async () => {}) },
}))
mock.module('@/lib/api/server-url', () => ({ getServerApiBaseUrl: () => 'http://api.test' }))
mock.module(path.join(authRoot, '_components/auth-layout-shell.tsx'), () => ({
  AuthLayoutShell: (props: any) => ({ type: 'auth-layout-shell', props }),
}))
for (const component of [
  'forgot-password/_components/forgot-password-form.tsx',
  'login/_components/login-form.tsx',
  'login/_components/login-redirect.tsx',
  'register/_components/register-form.tsx',
  'reset-password/_components/reset-password-by-token-form.tsx',
]) {
  const name = component.includes('login-redirect') ? 'LoginRedirect' :
    component.includes('forgot') ? 'ForgotPasswordForm' :
    component.includes('register') ? 'RegisterForm' :
    component.includes('reset') ? 'ResetPasswordByTokenForm' : 'LoginForm'
  mock.module(path.join(authRoot, component), () => ({ [name]: (props: any) => ({ type: name, props }) }))
}

globalThis.fetch = fetchMock as typeof fetch

function collectText(node: any): string[] {
  if (typeof node === 'string') return [node]
  if (Array.isArray(node)) return node.flatMap(collectText)
  return node?.props?.children ? collectText(node.props.children) : []
}

function findElement(node: any, type: string): any {
  if (!node || typeof node !== 'object') return
  if (node.type === type || node.type?.name === type) return node
  for (const child of Array.isArray(node.props?.children) ? node.props.children : [node.props?.children]) {
    const found = findElement(child, type)
    if (found) return found
  }
}

function resetRouteState(params = '') {
  navigation.push.mockClear()
  navigation.replace.mockClear()
  navigation.searchParams = new URLSearchParams(params)
}

describe('auth route wrappers', () => {
  test('loads public branding into the split auth layout', async () => {
    fetchMock.mockResolvedValueOnce({ ok: true, json: async () => ({ data: { site_name: 'Acme', auth_page_layout: 'split', terms_enabled: true } }) })
    const { default: AuthLayout } = await import('./layout')

    const result = await AuthLayout({ children: 'route content' }) as any

    expect(fetchMock).toHaveBeenCalledWith('http://api.test/site-settings/public', expect.objectContaining({ cache: 'no-store' }))
    expect(result.type).toBe('auth-layout-shell')
    expect(result.props).toMatchObject({
      layout: 'split', previewImageAlt: 'previewImageAlt', brandingSettings: { site_name: 'Acme' }, children: 'route content',
    })
  })

  test('falls back to centered branding when public settings fail', async () => {
    fetchMock.mockResolvedValueOnce({ ok: false, status: 503 })
    const { default: AuthLayout } = await import('./layout')

    const result = await AuthLayout({ children: null }) as any

    expect(result.props).toMatchObject({ layout: 'centered', brandingSettings: { site_name: 'Clouisle' } })
  })

  test('renders server auth pages with their scoped form and navigation contracts', async () => {
    const [{ default: LoginPage }, { default: RegisterPage }, { default: ForgotPasswordPage }] = await Promise.all([
      import('./login/page'), import('./register/page'), import('./forgot-password/page'),
    ])

    expect(collectText(await LoginPage())).toEqual(expect.arrayContaining(['loginTitle', 'loginDescription', 'noAccount', 'register']))
    expect(findElement(await LoginPage(), 'a').props.href).toBe('/register')
    expect(collectText(await RegisterPage())).toEqual(expect.arrayContaining(['registerTitle', 'registerDescription', 'hasAccount', 'login']))
    expect(findElement(await RegisterPage(), 'a').props.href).toBe('/login')
    expect(collectText(await ForgotPasswordPage())).toEqual(expect.arrayContaining(['forgotPasswordTitle', 'forgotPasswordDescription']))
  })

  test('redirects reset-password requests without a token and forwards valid tokens to its form boundary', async () => {
    const { default: ResetPasswordPage } = await import('./reset-password/page')
    resetRouteState()
    expect(ResetPasswordPage()).toBeNull()
    expect(navigation.replace).toHaveBeenCalledWith('/forgot-password')

    resetRouteState('token=valid-token')
    expect(findElement(ResetPasswordPage(), 'ResetPasswordByTokenForm').props.token).toBe('valid-token')
  })

  test('handles SSO errors without processing a token and lets users return to login', async () => {
    const { default: SSOCallbackPage } = await import('./sso-callback/page')
    resetRouteState('error=inactive&token=ignored')

    const result = SSOCallbackPage()

    expect(collectText(result)).toEqual(expect.arrayContaining(['ssoCallbackInactiveTitle', 'ssoCallbackInactiveDescription', 'ssoCallbackBackToLogin']))
    expect(navigation.push).not.toHaveBeenCalled()
    findElement(result, 'button').props.onClick()
    expect(navigation.push).toHaveBeenCalledWith('/login')
  })

  test('redirects TOTP setup without the temporary session token', async () => {
    const { default: TOTPSetupPage } = await import('./totp-setup/page')
    const getItem = mock(() => null)
    Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: { getItem, removeItem: mock(), setItem: mock() } })
    resetRouteState()

    expect(TOTPSetupPage()).toBeNull()
    expect(navigation.push).toHaveBeenCalledWith('/login')
  })

  test('shows a verification error when the link has no token', async () => {
    const { default: VerifyPage } = await import('./verify/page')
    resetRouteState()

    const result = VerifyPage()

    expect(collectText(result)).toEqual(expect.arrayContaining(['verifyYourEmail', 'verifyingEmail']))
  })
})
