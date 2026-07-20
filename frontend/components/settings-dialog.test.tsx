import { Window } from 'happy-dom'
import { afterEach, beforeEach, describe, expect, mock, test } from 'bun:test'
import * as React from 'react'
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'

const window = new Window()
globalThis.window = window as unknown as Window & typeof globalThis
globalThis.document = window.document as unknown as Document
globalThis.navigator = window.navigator as unknown as Navigator
globalThis.MouseEvent = window.MouseEvent as unknown as typeof MouseEvent
globalThis.Event = window.Event as unknown as typeof Event
globalThis.localStorage = window.localStorage as unknown as Storage
globalThis.IS_REACT_ACT_ENVIRONMENT = true

const push = mock<(path: string) => void>()
const getCurrentUser = mock<() => Promise<typeof user>>()
const getPasswordStatus = mock(() => Promise.resolve(null))
const getTotpStatus = mock(() => Promise.resolve({ enabled: false, enabled_at: null, remaining_backup_codes: 0 }))
const updateProfile = mock(() => Promise.resolve({}))
const deleteAccount = mock(() => Promise.resolve())

let siteSettings = { allow_account_deletion: false, email_verification: false }
let user = {
  id: 'user-1',
  username: 'alice',
  email: 'alice@example.com',
  avatar_url: null,
  auth_source: 'github',
  sso_connections: [{
    id: 'connection-1',
    provider_id: 'github',
    provider_name: 'github',
    provider_display_name: 'GitHub',
    provider_icon_url: null,
    provider_user_id: '42',
    provider_username: 'alice',
    provider_email: 'alice@example.com',
    first_login: '2026-01-01T00:00:00Z',
    last_login: '2026-01-02T00:00:00Z',
  }],
}

mock.module('next-intl', () => ({
  useTranslations: () => (key: string, values?: Record<string, unknown>) =>
    values ? `${key}:${Object.values(values).join(',')}` : key,
}))
mock.module('next/navigation', () => ({ useRouter: () => ({ push }) }))
mock.module('sonner', () => ({ toast: { info: mock(), success: mock(), warning: mock() } }))
const Icon = () => null
mock.module('lucide-react', () => ({
  AlertCircle: Icon, Clock: Icon, Copy: Icon, Download: Icon, KeyRound: Icon, Link: Icon,
  Loader2: Icon, Mail: Icon, Shield: Icon, Unlink: Icon, User: Icon,
}))
mock.module('@/contexts/site-settings-context', () => ({ useSiteSettings: () => ({ settings: siteSettings }) }))
mock.module('@/lib/api', () => ({
  authApi: { getCurrentUser, sendVerification: mock() },
  usersApi: { getPasswordStatus, updateProfile, changePassword: mock(), deleteAccount },
  ssoApi: { disconnectConnection: mock() },
  totpApi: { getStatus: getTotpStatus, disable: mock(), regenerateBackupCodes: mock() },
}))
mock.module('@/components/ui/dialog', () => ({
  Dialog: ({ open, children }: { open: boolean; children: React.ReactNode }) => open ? <div role="dialog">{children}</div> : null,
  DialogContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogDescription: ({ children }: { children: React.ReactNode }) => <p>{children}</p>,
  DialogHeader: ({ children }: { children: React.ReactNode }) => <header>{children}</header>,
  DialogTitle: ({ children }: { children: React.ReactNode }) => <h1>{children}</h1>,
}))

const TabsContext = React.createContext<{ value: string; setValue: (value: string) => void } | null>(null)
mock.module('@/components/ui/tabs', () => ({
  Tabs: ({ defaultValue, children }: { defaultValue: string; children: React.ReactNode }) => {
    const [value, setValue] = React.useState(defaultValue)
    return <TabsContext.Provider value={{ value, setValue }}>{children}</TabsContext.Provider>
  },
  TabsList: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  TabsTrigger: ({ value, children }: { value: string; children: React.ReactNode }) => {
    const tabs = React.useContext(TabsContext)!
    return <button onClick={() => tabs.setValue(value)}>{children}</button>
  },
  TabsContent: ({ value, children }: { value: string; children: React.ReactNode }) =>
    React.useContext(TabsContext)!.value === value ? <section>{children}</section> : null,
}))

const passthrough = ({ children }: { children?: React.ReactNode }) => <div>{children}</div>
mock.module('@/components/ui/card', () => ({
  Card: passthrough, CardContent: passthrough, CardDescription: passthrough, CardHeader: passthrough, CardTitle: passthrough,
}))
mock.module('@/components/ui/alert', () => ({ Alert: passthrough, AlertDescription: passthrough }))
mock.module('@/components/ui/alert-dialog', () => ({
  AlertDialog: passthrough,
  AlertDialogAction: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => <button {...props}>{children}</button>,
  AlertDialogCancel: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => <button {...props}>{children}</button>,
  AlertDialogContent: passthrough,
  AlertDialogDescription: passthrough,
  AlertDialogFooter: passthrough,
  AlertDialogHeader: passthrough,
  AlertDialogTitle: passthrough,
  AlertDialogTrigger: ({ render }: { render: React.ReactNode | ((props: object) => React.ReactNode) }) =>
    typeof render === 'function' ? render({}) : render,
}))
mock.module('@/components/ui/button', () => ({
  Button: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => <button {...props}>{children}</button>,
}))
mock.module('@/components/ui/input', () => ({ Input: (props: React.InputHTMLAttributes<HTMLInputElement>) => <input {...props} /> }))
mock.module('@/components/ui/label', () => ({ Label: ({ children, ...props }: React.LabelHTMLAttributes<HTMLLabelElement>) => <label {...props}>{children}</label> }))
mock.module('@/components/ui/skeleton', () => ({ Skeleton: () => <div data-testid="skeleton" /> }))
mock.module('@/components/ui/image-upload', () => ({ ImageUpload: () => <div data-testid="image-upload" /> }))
mock.module('@/components/ui/input-otp', () => ({ InputOTP: passthrough, InputOTPGroup: passthrough, InputOTPSlot: () => null }))
mock.module('@/components/ui/field', () => ({ FieldError: ({ children }: { children?: React.ReactNode }) => children ? <p role="alert">{children}</p> : null }))
mock.module('./totp-setup-wizard', () => ({ TOTPSetupWizard: () => null }))

let container: HTMLDivElement
let root: Root

async function render(open = true, onOpenChange = mock<(open: boolean) => void>()) {
  const { SettingsDialog } = await import('./settings-dialog')
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
  await act(async () => root.render(<SettingsDialog open={open} onOpenChange={onOpenChange} />))
  return onOpenChange
}

async function click(text: string, occurrence = 0) {
  const buttons = [...container.querySelectorAll('button')].filter((node) => node.textContent === text)
  expect(buttons[occurrence]).toBeTruthy()
  await act(async () => buttons[occurrence]!.dispatchEvent(new MouseEvent('click', { bubbles: true })))
}

beforeEach(() => {
  siteSettings = { allow_account_deletion: false, email_verification: false }
  getCurrentUser.mockReset()
  getCurrentUser.mockImplementation(() => Promise.resolve(user))
  for (const fn of [getPasswordStatus, getTotpStatus, updateProfile, deleteAccount, push]) fn.mockClear()
  localStorage.setItem('access_token', 'token')
})

afterEach(() => {
  act(() => root?.unmount())
  container?.remove()
})

describe('SettingsDialog', () => {
  test('loads only when open and populates the profile tab', async () => {
    await render(false)
    expect(getCurrentUser).not.toHaveBeenCalled()
    expect(container.querySelector('[role="dialog"]')).toBeNull()

    act(() => root.unmount())
    container.remove()
    await render()
    expect(getCurrentUser).toHaveBeenCalledWith({ skipAuthRedirect: true })
    expect((container.querySelector('#username') as HTMLInputElement).value).toBe('alice')
    expect((container.querySelector('#email') as HTMLInputElement).value).toBe('alice@example.com')
    expect(container.textContent).not.toContain('connectedAccounts')
  })

  test('switches to account options appropriate for an SSO user and site policy', async () => {
    await render()
    expect(container.textContent).not.toContain('connectedAccounts')

    await click('account')
    expect(container.textContent).toContain('connectedAccounts')
    expect(container.textContent).toContain('GitHub')
    expect(container.textContent).toContain('setPassword')
    expect(container.querySelector('#current')).toBeNull()
    expect(container.textContent).not.toContain('dangerZone')
  })

  test('shows account deletion only when policy allows it for a local user', async () => {
    siteSettings.allow_account_deletion = true
    user = { ...user, auth_source: 'local', sso_connections: [] }
    await render()

    await click('account')
    expect(container.textContent).toContain('changePassword')
    expect(container.querySelector('#current')).toBeTruthy()
    expect(container.textContent).toContain('dangerZone')
    expect(container.querySelector('#delete-password')).toBeTruthy()
  })
})
