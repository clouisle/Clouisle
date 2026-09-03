import { afterEach, beforeEach, expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown> | null) => ({ type, props: props ?? {} })
const element = function Element() {}

const originalApiUrl = process.env.NEXT_PUBLIC_API_URL
const originalFetch = globalThis.fetch
let stateValues: unknown[] = []
let stateIndex = 0
const stateUpdates: unknown[][] = []
const effects: Array<() => void | (() => void)> = []

const setTheme = mock(() => {})
const changeLocale = mock(() => {})
const setSidebarVariant = mock(() => {})
const setLayoutVariant = mock(() => {})
const setDirection = mock(() => {})
const setPlatformHeaderVariant = mock(() => {})
const resetSettings = mock(() => {})
const getPasswordStatus = mock(() => Promise.resolve({}))
const setupTotp = mock(() => Promise.resolve({ secret: 'secret', qr_code: 'qr', backup_codes: ['one', 'two'] }))
const enableTotp = mock(() => Promise.resolve({}))
const toastSuccess = mock(() => {})
const toastError = mock(() => {})
const writeText = mock(() => Promise.resolve())

function Button() {}
function SheetContent() {}
function TOTPQRCode() {}
function InputOTP() {}

mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react', () => ({
  useState: <T,>(initial: T) => {
    const index = stateIndex++
    const setState = (value: T | ((previous: T) => T)) => stateUpdates[index]?.push(value)
    return [(stateValues[index] ?? initial) as T, setState] as [T, typeof setState]
  },
  useEffect: (effect: () => void | (() => void)) => effects.push(effect),
}))
mock.module('next-themes', () => ({ useTheme: () => ({ theme: 'system', setTheme }) }))
mock.module('next-intl', () => ({
  useLocale: () => 'en',
  useTranslations: () => (key: string, values?: Record<string, unknown>) => values?.days ? `${key}:${values.days}` : key,
}))
mock.module('next/link', () => ({ default: element }))
mock.module('lucide-react', () => ({
  AlertCircle: element,
  Check: element,
  CheckCircle2: element,
  Copy: element,
  Download: element,
  Info: element,
  Key: element,
  Loader2: element,
  Shield: element,
  ShieldCheck: element,
  X: element,
}))
mock.module('@/components/ui/alert', () => ({ Alert: element, AlertDescription: element }))
mock.module('@/components/ui/button', () => ({ Button }))
mock.module('@/components/ui/card', () => ({ Card: element, CardContent: element, CardDescription: element, CardHeader: element, CardTitle: element }))
mock.module('@/components/ui/dialog', () => ({ Dialog: element, DialogContent: element, DialogDescription: element, DialogHeader: element, DialogTitle: element }))
mock.module('@/components/ui/input-otp', () => ({ InputOTP, InputOTPGroup: element, InputOTPSlot: element }))
mock.module('@/components/ui/label', () => ({ Label: element }))
mock.module('@/components/ui/sheet', () => ({ Sheet: element, SheetContent, SheetDescription: element, SheetFooter: element, SheetHeader: element, SheetTitle: element }))
mock.module('@/components/totp-qr-code', () => ({ TOTPQRCode }))
mock.module('./totp-qr-code', () => ({ TOTPQRCode }))
mock.module('@/lib/utils', () => ({ cn: (...values: unknown[]) => values.filter(Boolean).join(' ') }))
mock.module('@/i18n/config', () => ({ locales: ['en', 'zh'], localeNames: { en: 'English', zh: '中文' } }))
mock.module('@/hooks/use-locale-change', () => ({ useLocaleChange: () => ({ changeLocale }) }))
mock.module('@/hooks/use-settings', () => ({
  useSettings: () => ({
    sidebarVariant: 'floating',
    layoutVariant: 'compact',
    direction: 'rtl',
    platformHeaderVariant: 'centered',
    mounted: true,
    setSidebarVariant,
    setLayoutVariant,
    setDirection,
    setPlatformHeaderVariant,
    resetSettings,
  }),
}))
mock.module('@/lib/api', () => ({ usersApi: { getPasswordStatus } }))
mock.module('@/lib/api/users', () => ({ totpApi: { setup: setupTotp, enable: enableTotp } }))
mock.module('sonner', () => ({ toast: { error: toastError, success: toastSuccess } }))

const { SettingsDrawer } = await import('./settings-drawer')
const { PasswordExpirationBanner } = await import('./password-expiration-banner')
const { TOTPSetupWizard } = await import('./totp-setup-wizard')
const { TOTPSetupWizardForced } = await import('./totp-setup-wizard-forced')

function resetHooks(values: unknown[] = []) {
  stateValues = values
  stateIndex = 0
  stateUpdates.length = 20
  for (let index = 0; index < 20; index++) stateUpdates[index] = []
  effects.length = 0
}

function textContent(node: unknown): string {
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (!node || typeof node !== 'object' || !('props' in node)) return ''
  return [((node as { props: Record<string, unknown> }).props.children)].flat().map(textContent).join('')
}

function find(node: unknown, predicate: (node: { type: unknown; props: Record<string, unknown> }) => boolean): { type: unknown; props: Record<string, unknown> } | undefined {
  if (!node || typeof node !== 'object' || !('props' in node)) return undefined
  const elementNode = node as { type: unknown; props: Record<string, unknown> }
  if (predicate(elementNode)) return elementNode
  return [elementNode.props.children].flat().map((child) => find(child, predicate)).find(Boolean)
}

function clickButton(tree: unknown, label: string) {
  const button = find(tree, (node) => typeof node.props.onClick === 'function' && textContent(node).includes(label))
  expect(button).toBeDefined()
  return button?.props.onClick as (() => void | Promise<void>)
}

function clickLabeled(tree: unknown, label: string) {
  const node = find(tree, (item) => item.props.label === label && typeof item.props.onClick === 'function')
  expect(node).toBeDefined()
  return node?.props.onClick as () => void
}

function clickByClass(tree: unknown, className: string) {
  const node = find(tree, (item) => typeof item.props.onClick === 'function' && String(item.props.className).includes(className))
  expect(node).toBeDefined()
  return node?.props.onClick as () => void
}

beforeEach(() => {
  resetHooks()
  mock.restore()
  delete process.env.NEXT_PUBLIC_API_URL
  Object.assign(navigator, { clipboard: { writeText } })
})

afterEach(() => {
  if (originalApiUrl === undefined) delete process.env.NEXT_PUBLIC_API_URL
  else process.env.NEXT_PUBLIC_API_URL = originalApiUrl
  globalThis.fetch = originalFetch
})

test('settings drawer exposes visible choices and calls focused actions', () => {
  const tree = SettingsDrawer({ open: true, onOpenChange: mock(() => {}), showSidebarStyle: false, showPlatformHeader: true })

  expect(textContent(tree)).toContain('themeSettings')
  expect(textContent(tree)).toContain('headerLayout')
  expect(textContent(tree)).not.toContain('sidebarInset')
  expect(find(tree, (node) => node.type === SheetContent)?.props.side).toBe('left')

  clickLabeled(tree, 'dark')?.()
  clickLabeled(tree, 'headerMinimal')?.()
  clickLabeled(tree, 'directionLTR')?.()
  clickButton(tree, 'reset')?.()

  expect(setTheme).toHaveBeenCalledWith('dark')
  expect(setPlatformHeaderVariant).toHaveBeenCalledWith('minimal')
  expect(setDirection).toHaveBeenCalledWith('ltr')
  expect(resetSettings).toHaveBeenCalled()
})

test('password expiration banner loads warning and can be dismissed', async () => {
  getPasswordStatus.mockResolvedValueOnce({ is_exempt: false, days_until_expiration: 3 })
  resetHooks([null, false, true])
  PasswordExpirationBanner()
  await effects[0]?.()

  expect(getPasswordStatus).toHaveBeenCalled()
  expect(stateUpdates[0]).toContainEqual({ is_exempt: false, days_until_expiration: 3 })
  expect(stateUpdates[2]).toContain(false)

  resetHooks([{ is_exempt: false, days_until_expiration: 3 }, false, false])
  const tree = PasswordExpirationBanner()
  expect(textContent(tree)).toContain('passwordExpiringSoon:3')
  expect(find(tree, (node) => textContent(node).includes('changePasswordNow'))).toBeDefined()
  clickByClass(tree, 'h-8 w-8')?.()
  expect(stateUpdates[1]).toContain(true)
})

test('totp setup wizard starts setup and blocks short verification codes', async () => {
  resetHooks([1, false, null, '', false])
  const intro = TOTPSetupWizard({ open: true, onOpenChange: mock(() => {}), onSuccess: mock(() => {}) })
  expect(textContent(intro)).toContain('setupStep1Title')
  await clickButton(intro, 'setupStepNext')?.()

  expect(setupTotp).toHaveBeenCalled()
  expect(stateUpdates[2]).toContainEqual({ secret: 'secret', qr_code: 'qr', backup_codes: ['one', 'two'] })
  expect(stateUpdates[0]).toContain(2)

  resetHooks([3, false, { secret: 'secret', qr_code: 'qr', backup_codes: ['one', 'two'] }, '123', false])
  const verify = TOTPSetupWizard({ open: true, onOpenChange: mock(() => {}), onSuccess: mock(() => {}) })
  expect(textContent(verify)).toContain('setupStep3Title')
  await clickButton(verify, 'verifyCode')?.()
  expect(enableTotp).not.toHaveBeenCalled()
})

test('forced totp setup uses temp token and exposes backup-code actions', async () => {
  const fetchMock = mock(() => Promise.resolve({ ok: true, json: () => Promise.resolve({ data: { secret: 'forced', qr_code: 'qr', backup_codes: ['aa', 'bb'] } }) }))
  Object.assign(globalThis, { fetch: fetchMock })

  resetHooks([1, false, null, '', false])
  const intro = TOTPSetupWizardForced({ tempToken: 'temp-token', onComplete: mock(() => {}), onCancel: mock(() => {}) })
  await clickButton(intro, 'setupStepNext')?.()

  expect(fetchMock).toHaveBeenCalledWith('/api/v1/totp/setup', expect.objectContaining({ method: 'POST', headers: { Authorization: 'Bearer temp-token' } }))
  expect(stateUpdates[2]).toContainEqual({ secret: 'forced', qr_code: 'qr', backup_codes: ['aa', 'bb'] })
  expect(stateUpdates[0]).toContain(2)

  resetHooks([4, false, { secret: 'forced', qr_code: 'qr', backup_codes: ['aa', 'bb'] }, '', false])
  const backupCodes = TOTPSetupWizardForced({ tempToken: 'temp-token', onComplete: mock(() => {}), onCancel: mock(() => {}) })
  expect(textContent(backupCodes)).toContain('aa')
  clickButton(backupCodes, 'setupStep4Copy')?.()

  expect(writeText).toHaveBeenCalledWith('aa\nbb')
  expect(toastSuccess).toHaveBeenCalledWith('setupStep4CodesCopied')
  expect(stateUpdates[4]).toContain(true)
})
