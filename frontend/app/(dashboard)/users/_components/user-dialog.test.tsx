import { beforeEach, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from 'react-test-renderer'

const createUser = mock()
const updateUser = mock()
const getUser = mock()
const adminDisconnectConnection = mock()
const getRoles = mock(async () => ({ items: [{ id: 'role-1', name: 'admin', description: 'Administrator' }] }))
const success = mock()
let canManageSSO = false
const onOpenChange = mock()
const onSuccess = mock()

mock.module('next-intl', () => ({
  useTranslations: () => (key: string, values?: { length?: string }) =>
    values?.length ? `${key}:${values.length}` : key,
}))
mock.module('sonner', () => ({ toast: { success } }))
mock.module('@/lib/api/admin/users', () => ({ usersApi: { createUser, updateUser, getUser } }))
mock.module('@/lib/api/admin/roles', () => ({ rolesApi: { getRoles } }))
mock.module('@/lib/api/admin/sso', () => ({ ssoApi: { adminDisconnectConnection } }))
mock.module('@/components/permission-guard', () => ({ useCanPerform: () => ({ canPerform: () => canManageSSO }) }))
mock.module('@/lib/utils', () => ({ isValidEmail: (email: string) => email.includes('@') }))
mock.module('@/lib/validation', () => ({
  clearValidationError: (errors: Record<string, string>, field: string) => {
    const rest = { ...errors }
    delete rest[field]
    return rest
  },
  clearValidationErrorsByPrefix: (errors: Record<string, string>) => errors,
  getValidationSummaryEntries: (errors: Record<string, string>) => Object.entries(errors),
  normalizeValidationErrors: (error: { errors?: Record<string, string> }) => error.errors ?? {},
  normalizeValidationErrorsRaw: (error: { errors?: Record<string, string[]> }) => error.errors ?? {},
  formatValidationSummaryMessage: (field: string, message: string) => `${field}: ${message}`,
}))

const element = ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) => <div {...props}>{children}</div>
mock.module('@/components/ui/dialog', () => ({ Dialog: element, DialogContent: element, DialogDescription: element, DialogFooter: element, DialogHeader: element, DialogTitle: element }))
mock.module('@/components/ui/alert-dialog', () => ({ AlertDialog: element, AlertDialogAction: element, AlertDialogCancel: element, AlertDialogContent: element, AlertDialogDescription: element, AlertDialogFooter: element, AlertDialogHeader: element, AlertDialogTitle: element, AlertDialogTrigger: element }))
mock.module('@/components/ui/button', () => ({ Button: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => <button {...props}>{children}</button> }))
mock.module('@/components/ui/input', () => ({ Input: (props: React.InputHTMLAttributes<HTMLInputElement>) => <input {...props} /> }))
mock.module('@/components/ui/label', () => ({ Label: element }))
mock.module('@/components/ui/field', () => ({ FieldError: element }))
mock.module('@/components/ui/switch', () => ({ Switch: ({ onCheckedChange, ...props }: { onCheckedChange: (checked: boolean) => void }) => <input type="checkbox" onChange={() => onCheckedChange(false)} {...props} /> }))
mock.module('@/components/ui/checkbox', () => ({ Checkbox: ({ onCheckedChange, ...props }: { onCheckedChange: (checked: boolean) => void }) => <input type="checkbox" onChange={() => onCheckedChange(true)} {...props} /> }))
mock.module('lucide-react', () => ({ Link: () => null, Loader2: () => null, Unlink: () => null }))

const { UserDialog } = await import('./user-dialog')
globalThis.IS_REACT_ACT_ENVIRONMENT = true

const user = { id: 'user-1', username: 'Ada', email: 'ada@example.test', is_active: true, roles: [{ name: 'admin' }] }
const render = (editing = false) => {
  let renderer: ReactTestRenderer
  act(() => {
    renderer = create(<UserDialog open onOpenChange={onOpenChange} user={editing ? user as never : null} onSuccess={onSuccess} />)
  })
  return renderer!
}
const submit = async (renderer: ReactTestRenderer) => act(async () => {
  await renderer.root.findByType('form').props.onSubmit({ preventDefault: mock() })
})
const input = (renderer: ReactTestRenderer, id: string) => renderer.root.findAllByType('input').find((node) => node.props.id === id)!
const change = async (renderer: ReactTestRenderer, id: string, value: string) => act(async () => {
  input(renderer, id).props.onChange({ target: { value } })
})

beforeEach(() => {
  createUser.mockReset()
  updateUser.mockReset()
  getUser.mockReset()
  adminDisconnectConnection.mockReset()
  canManageSSO = false
  getRoles.mockClear()
  success.mockClear()
  onOpenChange.mockClear()
  onSuccess.mockClear()
})

test('loads roles and saves edited user data', async () => {
  updateUser.mockResolvedValue(user)
  const renderer = render(true)

  await act(async () => {})
  expect(getRoles).toHaveBeenCalledWith(1, 100)
  expect(input(renderer, 'username').props.value).toBe('Ada')
  await submit(renderer)

  expect(updateUser).toHaveBeenCalledWith('user-1', { email: 'ada@example.test', is_active: true, roles: ['admin'] })
  expect(success).toHaveBeenCalledWith('userUpdated')
  expect(onSuccess).toHaveBeenCalledWith(user)
  expect(onOpenChange).toHaveBeenCalledWith(false)
  act(() => renderer.unmount())
})

test('blocks create submission for an invalid email', async () => {
  const renderer = render()
  await submit(renderer)

  expect(createUser).not.toHaveBeenCalled()
  expect(JSON.stringify(renderer.toJSON())).toContain('invalidEmail')
  act(() => renderer.unmount())
})

test('creates a user after valid input', async () => {
  createUser.mockResolvedValue(user)
  const renderer = render()
  await change(renderer, 'username', 'Ada')
  await change(renderer, 'email', 'ada@example.test')
  await change(renderer, 'password', 'secret1')
  await change(renderer, 'confirmPassword', 'secret1')
  await submit(renderer)

  expect(createUser).toHaveBeenCalledWith({ username: 'Ada', email: 'ada@example.test', password: 'secret1', is_active: true })
  expect(success).toHaveBeenCalledWith('userCreated')
  expect(onOpenChange).toHaveBeenCalledWith(false)
  act(() => renderer.unmount())
})

test('shows API validation errors and recovers on retry', async () => {
  createUser.mockRejectedValueOnce({ errors: { email: 'alreadyUsed' } }).mockResolvedValueOnce(user)
  const renderer = render()
  await change(renderer, 'username', 'Ada')
  await change(renderer, 'email', 'ada@example.test')
  await change(renderer, 'password', 'secret1')
  await change(renderer, 'confirmPassword', 'secret1')
  await submit(renderer)
  expect(JSON.stringify(renderer.toJSON())).toContain('alreadyUsed')

  await act(async () => input(renderer, 'email').props.onChange({ target: { value: 'new@example.test' } }))
  await submit(renderer)
  expect(createUser).toHaveBeenCalledTimes(2)
  expect(onOpenChange).toHaveBeenCalledWith(false)
  act(() => renderer.unmount())
})

test('validates short and mismatched passwords', async () => {
  const renderer = render()
  await change(renderer, 'email', 'ada@example.test')
  await change(renderer, 'password', 'short')
  await submit(renderer)
  expect(JSON.stringify(renderer.toJSON())).toContain('passwordTooShort')

  await change(renderer, 'password', 'secret1')
  await change(renderer, 'confirmPassword', 'different')
  await submit(renderer)
  expect(JSON.stringify(renderer.toJSON())).toContain('passwordMismatch')
  expect(createUser).not.toHaveBeenCalled()
  act(() => renderer.unmount())
})

test('includes a new password when editing and toggles fields', async () => {
  updateUser.mockResolvedValue(user)
  const renderer = render(true)
  await act(async () => {})

  await change(renderer, 'password', 'changed1')
  await change(renderer, 'confirmPassword', 'changed1')
  const checkboxes = renderer.root.findAllByType('input').filter((node) => node.props.type === 'checkbox')
  await act(async () => checkboxes[1].props.onChange())
  await submit(renderer)

  expect(updateUser).toHaveBeenCalledWith('user-1', {
    email: 'ada@example.test', is_active: false, roles: ['admin'], password: 'changed1',
  })
  act(() => renderer.unmount())
})

test('disconnects an SSO account and refreshes the user', async () => {
  canManageSSO = true
  const connectedUser = {
    ...user,
    sso_connections: [{
      id: 'connection-1', provider_display_name: 'Corporate', provider_email: 'ada@example.test',
      provider_icon_url: null,
    }],
  }
  adminDisconnectConnection.mockResolvedValue(undefined)
  getUser.mockResolvedValue(connectedUser)

  let renderer: ReactTestRenderer
  act(() => {
    renderer = create(<UserDialog open onOpenChange={onOpenChange} user={connectedUser as never} onSuccess={onSuccess} />)
  })
  await act(async () => {})
  const action = renderer!.root.findAllByType('div').find((node) => node.props.onClick)
  await act(async () => action?.props.onClick())

  expect(adminDisconnectConnection).toHaveBeenCalledWith('connection-1')
  expect(getUser).toHaveBeenCalledWith('user-1')
  expect(onSuccess).toHaveBeenCalledWith(connectedUser)
  act(() => renderer!.unmount())
})
