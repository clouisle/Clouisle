import { beforeEach, expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
const component = (name: string) => Object.assign(function Component() {}, { displayName: name })
type Node = { type: unknown; props: Record<string, unknown> }

let values: unknown[] = []
let index = 0
let updates: unknown[][] = []
const writeText = mock<(text: string) => Promise<void>>(() => Promise.resolve())
const createObjectURL = mock(() => 'blob:codes')
const revokeObjectURL = mock<(url: string) => void>()
const appendChild = mock<(node: unknown) => void>()
const removeChild = mock<(node: unknown) => void>()
const click = mock<() => void>()
const success = mock<(message: string) => void>()

mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('fragment') }))
mock.module('react', () => ({
  useState: <T,>(initial: T) => {
    const slot = index++
    return [values[slot] ?? initial, (value: T) => updates[slot].push(value)]
  },
  useEffect: () => {},
  useMemo: <T,>(factory: () => T) => factory(),
}))
mock.module('next-intl', () => ({ useLocale: () => 'en', useTranslations: () => (key: string) => key }))
mock.module('next/navigation', () => ({ useRouter: () => ({ push: mock(() => {}) }) }))
mock.module('sonner', () => ({ toast: { success, info: mock(() => {}), warning: mock(() => {}) } }))
mock.module('lucide-react', () => ({
  User: component('User'), Shield: component('Shield'), Loader2: component('Loader2'), Link: component('Link'),
  Unlink: component('Unlink'), KeyRound: component('KeyRound'), Download: component('Download'),
  Copy: component('Copy'), Mail: component('Mail'), AlertCircle: component('AlertCircle'), Clock: component('Clock'),
}))
mock.module('@/lib/utils', () => ({ formatDateTime: String, formatDate: String, isValidEmail: () => true }))
mock.module('@/lib/validation', () => ({
  clearValidationError: (errors: Record<string, string>) => errors,
  getValidationSummaryEntries: (errors: Record<string, string>) => Object.entries(errors),
  normalizeValidationErrors: () => ({}),
  formatValidationSummaryMessage: (_field: string, message: string) => message,
}))
class ApiError extends Error { code = 0 }
const api = new Proxy({}, { get: () => mock(() => Promise.resolve({})) })
mock.module('@/lib/api/client', () => ({ ApiError }))
mock.module('@/lib/api', () => ({ ApiError, authApi: api, usersApi: api, ssoApi: api, totpApi: api }))
mock.module('@/contexts/site-settings-context', () => ({ useSiteSettings: () => ({ settings: { allow_account_deletion: true } }) }))

mock.module('@/components/ui/dialog', () => ({ Dialog: component('Dialog'), DialogContent: component('DialogContent'), DialogDescription: component('DialogDescription'), DialogHeader: component('DialogHeader'), DialogTitle: component('DialogTitle') }))
mock.module('@/components/ui/tabs', () => ({ Tabs: component('Tabs'), TabsContent: component('TabsContent'), TabsList: component('TabsList'), TabsTrigger: component('TabsTrigger') }))
mock.module('@/components/ui/card', () => ({ Card: component('Card'), CardContent: component('CardContent'), CardDescription: component('CardDescription'), CardHeader: component('CardHeader'), CardTitle: component('CardTitle') }))
mock.module('@/components/ui/alert-dialog', () => ({
  AlertDialog: component('AlertDialog'), AlertDialogAction: component('AlertDialogAction'), AlertDialogCancel: component('AlertDialogCancel'),
  AlertDialogContent: component('AlertDialogContent'), AlertDialogDescription: component('AlertDialogDescription'), AlertDialogFooter: component('AlertDialogFooter'),
  AlertDialogHeader: component('AlertDialogHeader'), AlertDialogTitle: component('AlertDialogTitle'), AlertDialogTrigger: component('AlertDialogTrigger'),
}))
mock.module('@/components/ui/input', () => ({ Input: component('Input') }))
mock.module('@/components/ui/button', () => ({ Button: component('Button') }))
mock.module('@/components/ui/label', () => ({ Label: component('Label') }))
mock.module('@/components/ui/skeleton', () => ({ Skeleton: component('Skeleton') }))
mock.module('@/components/ui/image-upload', () => ({ ImageUpload: component('ImageUpload') }))
mock.module('@/components/ui/alert', () => ({ Alert: component('Alert'), AlertDescription: component('AlertDescription') }))
mock.module('@/components/ui/input-otp', () => ({ InputOTP: component('InputOTP'), InputOTPGroup: component('InputOTPGroup'), InputOTPSlot: component('InputOTPSlot') }))
mock.module('@/components/ui/field', () => ({ FieldError: component('FieldError') }))
mock.module('./totp-setup-wizard', () => ({ TOTPSetupWizard: component('TOTPSetupWizard') }))

const { SettingsDialog } = await import('./settings-dialog')

function walk(node: unknown, visit: (node: Node) => void) {
  if (!node || typeof node !== 'object' || !('props' in node)) return
  const current = node as Node
  visit(current)
  for (const child of [current.props.children].flat()) walk(child, visit)
}

function render(backupCodes: string[]) {
  values = []
  values[0] = false
  values[1] = { username: 'fake', email: 'fake@example.com', avatar_url: null, auth_source: 'local', sso_connections: [] }
  values[10] = { email: 'profile error' }
  values[13] = { newPassword: 'password error' }
  values[18] = { password: 'delete error' }
  values[25] = { code: 'disable error' }
  values[29] = { code: 'regenerate error' }
  values[30] = backupCodes
  index = 0
  updates = Array.from({ length: 31 }, () => [])
  return SettingsDialog({ open: true, onOpenChange: mock(() => {}) }) as Node
}

function textContent(node: unknown): string {
  if (typeof node === 'string') return node
  if (!node || typeof node !== 'object' || !('props' in node)) return ''
  return [((node as Node).props.children)].flat().map(textContent).join('')
}

function buttonHandlers(tree: Node, text: string) {
  const handlers: Array<() => unknown> = []
  walk(tree, (node) => {
    if (node.props.onClick && textContent(node) === text) handlers.push(node.props.onClick as () => unknown)
  })
  return handlers
}

beforeEach(() => {
  Object.assign(globalThis, {
    navigator: { clipboard: { writeText } },
    document: { createElement: () => ({ href: '', download: '', click }), body: { appendChild, removeChild } },
  })
  Object.assign(URL, { createObjectURL, revokeObjectURL })
  for (const fn of [writeText, createObjectURL, revokeObjectURL, appendChild, removeChild, click, success]) fn.mockClear()
})

test('downloads, copies, closes, and clears remaining dialog state', async () => {
  const tree = render(['alpha', 'beta'])
  await buttonHandlers(tree, 'setupStep4Download')[0]()
  await buttonHandlers(tree, 'setupStep4Copy')[0]()
  buttonHandlers(tree, 'close')[0]()

  expect(createObjectURL).toHaveBeenCalledTimes(1)
  expect(appendChild).toHaveBeenCalledTimes(1)
  expect(click).toHaveBeenCalledTimes(1)
  expect(removeChild).toHaveBeenCalledTimes(1)
  expect(revokeObjectURL).toHaveBeenCalledWith('blob:codes')
  expect(writeText).toHaveBeenCalledWith('alpha\nbeta')
  expect(success).toHaveBeenCalledWith('setupStep4CodesCopied')
  expect(updates[27]).toEqual([false])
  expect(updates[30]).toEqual([[]])

  const validationTree = render([])
  expect(buttonHandlers(validationTree, 'cancel').length).toBeGreaterThanOrEqual(3)
  for (const handler of buttonHandlers(validationTree, 'cancel')) handler()
  expect(updates[21]).toContain('')
  expect(updates[22]).toContain('')
  expect(updates[23]).toContain(false)
  expect(updates[28]).toContain('')
})
