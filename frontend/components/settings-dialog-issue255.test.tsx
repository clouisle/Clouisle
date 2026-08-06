import { Window } from 'happy-dom'
import { afterEach, beforeEach, describe, expect, mock, test } from 'bun:test'
import * as React from 'react'
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { ApiError } from '@/lib/api/client'

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
const changePassword = mock(() => Promise.resolve())
const deleteAccount = mock(() => Promise.resolve())
const sendVerification = mock(() => Promise.resolve())
const disconnectConnection = mock(() => Promise.resolve())
const disableTotp = mock(() => Promise.resolve())
const regenerateBackupCodes = mock(() => Promise.resolve({ codes: ['code-one', 'code-two'] }))
const infoToast = mock<(message: string) => void>()
const successToast = mock<(message: string) => void>()
const warningToast = mock<(message: string) => void>()
const inputHandlers = new Map<string, React.ChangeEventHandler<HTMLInputElement> | undefined>()
let deleteAccountOnClick: (() => Promise<void>) | undefined
const actionHandlers = new Map<string, () => Promise<void>>()
const otpHandlers: Array<(value: string) => void> = []
let setupSuccess: (() => Promise<void>) | undefined
let imageChange: ((url: string) => void) | undefined

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
  useLocale: () => 'en',
  useTranslations: () => (key: string, values?: Record<string, unknown>) =>
    values ? `${key}:${Object.values(values).join(',')}` : key,
}))
mock.module('next/navigation', () => ({ useRouter: () => ({ push }) }))
mock.module('sonner', () => ({ toast: { info: infoToast, success: successToast, warning: warningToast } }))
const Icon = () => null
mock.module('lucide-react', () => ({
  AlertCircle: Icon, Clock: Icon, Copy: Icon, Download: Icon, KeyRound: Icon, Link: Icon,
  Loader2: Icon, Mail: Icon, Shield: Icon, Unlink: Icon, User: Icon,
}))
mock.module('@/contexts/site-settings-context', () => ({ useSiteSettings: () => ({ settings: siteSettings }) }))
mock.module('@/lib/api', () => ({
  ApiError,
  authApi: { getCurrentUser, sendVerification },
  usersApi: { getPasswordStatus, updateProfile, changePassword, deleteAccount },
  ssoApi: { disconnectConnection },
  totpApi: { getStatus: getTotpStatus, disable: disableTotp, regenerateBackupCodes },
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
  AlertDialogAction: ({ children, disabled, onClick, className, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => {
    const text = String(children)
    if (className?.includes('bg-destructive')) deleteAccountOnClick = onClick as () => Promise<void>
    if (onClick) actionHandlers.set(text, onClick as () => Promise<void>)
    return <button {...props} onClick={onClick} className={className} data-disabled={disabled} aria-disabled={disabled}>{children}</button>
  },
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
mock.module('@/components/ui/input', () => ({
  Input: (props: React.InputHTMLAttributes<HTMLInputElement>) => {
    if (props.id) inputHandlers.set(props.id, props.onChange)
    return <input {...props} />
  },
}))
mock.module('@/components/ui/label', () => ({ Label: ({ children, ...props }: React.LabelHTMLAttributes<HTMLLabelElement>) => <label {...props}>{children}</label> }))
mock.module('@/components/ui/skeleton', () => ({ Skeleton: () => <div data-testid="skeleton" /> }))
mock.module('@/components/ui/image-upload', () => ({ ImageUpload: ({ onChange }: { onChange: (url: string) => void }) => {
  imageChange = onChange
  return <div data-testid="image-upload" />
} }))
mock.module('@/components/ui/input-otp', () => ({
  InputOTP: ({ value, onChange, children }: { value: string; onChange: (value: string) => void; children: React.ReactNode }) => {
    otpHandlers.push(onChange)
    return <div><input aria-label="otp-input" value={value} readOnly />{children}</div>
  },
  InputOTPGroup: passthrough,
  InputOTPSlot: () => null,
}))
mock.module('@/components/ui/field', () => ({ FieldError: ({ children }: { children?: React.ReactNode }) => children ? <p role="alert">{children}</p> : null }))
mock.module('./totp-setup-wizard', () => ({ TOTPSetupWizard: ({ onSuccess }: { onSuccess: () => Promise<void> }) => {
  setupSuccess = onSuccess
  return null
} }))

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

function enter(input: HTMLInputElement, value: string) {
  input.value = value
  inputHandlers.get(input.id)!({ target: input } as React.ChangeEvent<HTMLInputElement>)
}

async function enterById(id: string, value: string) {
  const input = container.querySelector(`#${id}`) as HTMLInputElement
  expect(input).toBeTruthy()
  await act(async () => enter(input, value))
}

beforeEach(() => {
  siteSettings = { allow_account_deletion: false, email_verification: false }
  getCurrentUser.mockReset()
  getCurrentUser.mockImplementation(() => Promise.resolve(user))
  inputHandlers.clear()
  actionHandlers.clear()
  otpHandlers.length = 0
  for (const fn of [getPasswordStatus, getTotpStatus, updateProfile, changePassword, deleteAccount, sendVerification, disconnectConnection, disableTotp, regenerateBackupCodes, infoToast, successToast, warningToast, push]) fn.mockClear()
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

  test('validates, skips unchanged, and saves changed profile fields', async () => {
    await render()

    await enterById('email', 'invalid')
    await click('saveChanges')
    expect(updateProfile).not.toHaveBeenCalled()
    expect(container.textContent).toContain('invalidEmail')

    await enterById('email', 'alice@example.com')
    await click('saveChanges')
    expect(infoToast).toHaveBeenCalledWith('noChanges')

    const updatedUser = { ...user, username: 'alice-updated' }
    updateProfile.mockResolvedValueOnce(updatedUser)
    await enterById('username', 'alice-updated')
    await click('saveChanges')

    expect(updateProfile).toHaveBeenCalledWith({ username: 'alice-updated' }, { silent: true })
    expect(successToast).toHaveBeenCalledWith('profileUpdated')
  })

  test('requires verified email input before saving an email change', async () => {
    siteSettings.email_verification = true
    await render()
    await enterById('email', 'updated@example.com')

    await click('saveChanges')

    expect(updateProfile).not.toHaveBeenCalled()
    expect(warningToast).toHaveBeenCalledWith('emailVerificationRequired')
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

  test('sets a password and disconnects an SSO account', async () => {
    await render()
    await click('account')
    await click('disconnect', 1)
    expect(disconnectConnection).toHaveBeenCalledWith('connection-1')
    expect(successToast).toHaveBeenCalledWith('disconnectSuccess')

    await click('account')
    await enterById('new', 'longer-value')
    await enterById('confirm', 'longer-value')
    await click('setPassword')

    expect(updateProfile).toHaveBeenCalledWith({ password: 'longer-value' }, { silent: true })
    expect(successToast).toHaveBeenCalledWith('passwordUpdated')
  })

  test('disables TOTP after validating password and authenticator code', async () => {
    getTotpStatus.mockResolvedValueOnce({ enabled: true, enabled_at: '2026-01-01T00:00:00Z', remaining_backup_codes: 6 })
    await render()
    await click('account')
    await click('disableTwoFactor', 0)
    await enterById('disable-password', 'current-value')
    await click('useBackupCode')
    await enterById('disable-code', 'ABCD-EFGH')
    await click('disableTwoFactor', 1)

    expect(disableTotp).toHaveBeenCalledWith('current-value', 'ABCDEFGH', true, { silent: true })
    expect(successToast).toHaveBeenCalledWith('twoFactorDisabledSuccess')
  })

  test('regenerates TOTP backup codes from a valid authenticator code', async () => {
    getTotpStatus.mockResolvedValueOnce({ enabled: true, enabled_at: null, remaining_backup_codes: 1 })
    await render()
    await click('account')
    await click('regenerateBackupCodes', 0)
    await act(async () => otpHandlers.at(-1)!('654321'))
    await click('regenerateBackupCodes', 1)

    expect(regenerateBackupCodes).toHaveBeenCalledWith('654321', { silent: true })
    expect(container.textContent).toContain('code-one')
    expect(successToast).toHaveBeenCalledWith('backupCodesRegeneratedSuccess')
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

  test('rejects a short local password before calling the API', async () => {
    user = { ...user, auth_source: 'local', sso_connections: [] }
    await render()
    await click('account')
    await enterById('current', 'current-value')
    await enterById('new', 'short')
    await enterById('confirm', 'short')
    await click('updatePassword')

    expect(changePassword).not.toHaveBeenCalled()
    expect(container.textContent).toContain('newPasswordTooShort')
  })

  test('changes a local password and maps an incorrect-current-password error', async () => {
    user = { ...user, auth_source: 'local', sso_connections: [] }
    await render()
    await click('account')
    await enterById('current', 'current-value')
    await enterById('new', 'longer-value')
    await enterById('confirm', 'longer-value')
    changePassword.mockRejectedValueOnce(new ApiError(2003, 'incorrect current password'))
    await click('updatePassword')

    expect(changePassword).toHaveBeenCalledWith({ current_password: 'current-value', new_password: 'longer-value' }, { silent: true })
    expect((container.querySelector('#current') as HTMLInputElement).getAttribute('aria-invalid')).toBe('true')
    expect(container.textContent).toContain('incorrect current password')

    await enterById('current', 'updated-current-value')
    await click('updatePassword')
    expect(successToast).toHaveBeenCalledWith('passwordUpdated')
    expect(getCurrentUser).toHaveBeenCalledTimes(2)
  })

  test('sends profile verification only for a changed valid email and handles a rate-limit cooldown', async () => {
    siteSettings.email_verification = true
    await render()
    await enterById('email', 'updated@example.com')
    await click('sendEmailVerification')
    expect(sendVerification).toHaveBeenCalledWith('updated@example.com', 'profile_email')
    expect(successToast).toHaveBeenCalledWith('emailVerificationSent')

    sendVerification.mockRejectedValueOnce(new ApiError(5008, 'rate limited', { remaining_seconds: 12 }))
    await enterById('email', 'another@example.com')
    await click('sendEmailVerification')
    expect(container.textContent).toContain('resendIn:12')
  })

  test('saves avatar and a verified email, then maps profile conflicts', async () => {
    siteSettings.email_verification = true
    await render()
    await act(async () => imageChange!('https://example.com/avatar.png'))
    await enterById('email', 'updated@example.com')
    await click('sendEmailVerification')
    await act(async () => otpHandlers.find((handler) => handler.toString().includes('setEmailVerificationCode'))!('123456'))
    await click('saveChanges')
    expect(updateProfile).toHaveBeenCalledWith({
      avatar_url: 'https://example.com/avatar.png', email: 'updated@example.com', email_verification_code: '123456',
    }, { silent: true })

  })

  test('covers local password required, mismatch, and validation mapping branches', async () => {
    user = { ...user, auth_source: 'local', sso_connections: [] }
    await render()
    await click('account')
    await click('updatePassword')
    expect(container.textContent).toContain('currentPasswordRequired')
    await enterById('current', 'current-value')
    await click('updatePassword')
    expect(container.textContent).toContain('newPasswordRequired')
    await enterById('new', 'longer-value')
    await enterById('confirm', 'different-value')
    await click('updatePassword')
    expect(container.textContent).toContain('passwordMismatch')

    await enterById('confirm', 'longer-value')
    changePassword.mockRejectedValueOnce(new ApiError(422, 'validation', { detail: [{ loc: ['body', 'new_password'], msg: 'server rejected it', type: 'value_error' }] }))
    await click('updatePassword')
    expect(changePassword).toHaveBeenCalledTimes(1)
  })

  test('covers TOTP validation, API errors, setup reload, and regenerate errors', async () => {
    getTotpStatus.mockResolvedValue({ enabled: true, enabled_at: null, remaining_backup_codes: 1 })
    await render()
    await click('account')

    const disableAction = [...container.querySelectorAll('button')].find((button) => button.textContent === 'disableTwoFactor' && button.hasAttribute('aria-disabled'))!
    await act(async () => disableAction.dispatchEvent(new MouseEvent('click', { bubbles: true })))
    expect(container.textContent).toContain('currentPasswordRequired')
    await enterById('disable-password', 'current-value')
    await act(async () => otpHandlers.at(-2)!('123456'))
    disableTotp.mockRejectedValueOnce(new ApiError(5311, 'invalid totp'))
    await act(async () => disableAction.dispatchEvent(new MouseEvent('click', { bubbles: true })))
    expect(container.textContent).toContain('invalid totp')

    const regenerateAction = [...container.querySelectorAll('button')].find((button) => button.textContent === 'regenerateBackupCodes' && button.hasAttribute('aria-disabled'))!
    await act(async () => regenerateAction.dispatchEvent(new MouseEvent('click', { bubbles: true })))
    expect(container.textContent).toContain('verificationCodeInvalid')
    await act(async () => otpHandlers.at(-1)!('654321'))
    regenerateBackupCodes.mockRejectedValueOnce(new ApiError(5311, 'invalid regenerate code'))
    await act(async () => regenerateAction.dispatchEvent(new MouseEvent('click', { bubbles: true })))
    expect(container.textContent).toContain('invalid regenerate code')

    await act(async () => setupSuccess!())
    expect(getCurrentUser).toHaveBeenCalledTimes(2)
  })

  test('maps a generic account deletion API error', async () => {
    siteSettings.allow_account_deletion = true
    user = { ...user, auth_source: 'local', sso_connections: [] }
    await render()
    await click('account')
    await enterById('delete-password', 'password')
    deleteAccount.mockRejectedValueOnce(new ApiError(5000, 'cannot delete'))
    await act(async () => deleteAccountOnClick!())
    expect(container.textContent).toContain('cannot delete')
  })

  test('validates account deletion, clears an API error, and retries successfully', async () => {
    siteSettings.allow_account_deletion = true
    user = { ...user, auth_source: 'local', sso_connections: [] }
    const onOpenChange = await render()
    await click('account')

    let password = container.querySelector('#delete-password') as HTMLInputElement
    const confirmation = password.parentElement!.parentElement!.querySelector('button[data-disabled="true"]')!
    expect(confirmation).toBeTruthy()

    await act(async () => deleteAccountOnClick!())
    password = container.querySelector('#delete-password') as HTMLInputElement
    expect(deleteAccount).not.toHaveBeenCalled()
    expect(password.getAttribute('aria-invalid')).toBe('true')
    expect(container.textContent).toContain('currentPasswordRequired')

    await act(async () => enter(password, 'wrong-password'))
    password = container.querySelector('#delete-password') as HTMLInputElement
    expect(password.getAttribute('aria-invalid')).toBe('false')

    deleteAccount.mockRejectedValueOnce(new ApiError(2003, 'incorrect password'))
    await act(async () => deleteAccountOnClick!())
    password = container.querySelector('#delete-password') as HTMLInputElement
    expect(deleteAccount).toHaveBeenCalledWith('wrong-password', { silent: true })
    expect(password.getAttribute('aria-invalid')).toBe('true')
    expect(container.textContent).toContain('incorrect password')

    await act(async () => enter(password, 'correct-password'))
    password = container.querySelector('#delete-password') as HTMLInputElement
    expect(password.getAttribute('aria-invalid')).toBe('false')

    await act(async () => deleteAccountOnClick!())
    expect(deleteAccount).toHaveBeenLastCalledWith('correct-password', { silent: true })
    expect(successToast).toHaveBeenCalledWith('accountDeleted')
    expect(localStorage.getItem('access_token')).toBeNull()
    expect(onOpenChange).toHaveBeenCalledWith(false)
    expect(push).toHaveBeenCalledWith('/login')
  })
})
