import { afterEach, describe, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'

const toast = { success: mock(() => {}), warning: mock(() => {}) }
const usersApi = {
  activateUser: mock(async () => user),
  deactivateUser: mock(async () => user),
  deleteUser: mock(async () => user),
  sendEmail: mock(async () => ({ sent_count: 1, skipped_count: 0, total: 1 })),
}

mock.module('next-intl', () => ({
  useLocale: () => 'en',
  useTranslations: () => (key: string, values?: Record<string, string | number>) =>
    values ? `${key}:${Object.values(values).join(',')}` : key,
}))
mock.module('sonner', () => ({ toast }))
mock.module('@/lib/api/admin/users', () => ({ usersApi }))
mock.module('@/components/ui/button', () => ({
  Button: (props: React.ButtonHTMLAttributes<HTMLButtonElement>) => <button {...props} />,
}))
mock.module('@/components/ui/badge', () => ({
  Badge: ({ children, ...props }: React.HTMLAttributes<HTMLSpanElement>) => <span {...props}>{children}</span>,
}))
mock.module('@/components/ui/dialog', () => ({
  Dialog: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  DialogContent: ({ children }: { children: React.ReactNode }) => <section>{children}</section>,
  DialogDescription: ({ children }: { children: React.ReactNode }) => <p>{children}</p>,
  DialogFooter: ({ children }: { children: React.ReactNode }) => <footer>{children}</footer>,
  DialogHeader: ({ children }: { children: React.ReactNode }) => <header>{children}</header>,
  DialogTitle: ({ children }: { children: React.ReactNode }) => <h2>{children}</h2>,
}))
mock.module('@/components/ui/input', () => ({ Input: (props: React.InputHTMLAttributes<HTMLInputElement>) => <input {...props} /> }))
mock.module('@/components/ui/textarea', () => ({ Textarea: (props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) => <textarea {...props} /> }))
mock.module('@/components/ui/label', () => ({ Label: (props: React.LabelHTMLAttributes<HTMLLabelElement>) => <label {...props} /> }))
mock.module('@/components/ui/field', () => ({ FieldError: ({ children }: { children: React.ReactNode }) => <p role="alert">{children}</p> }))
mock.module('@/components/ui/dropdown-menu', () => ({
  DropdownMenu: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  DropdownMenuContent: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  DropdownMenuItem: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => <button {...props}>{children}</button>,
  DropdownMenuSeparator: () => <hr />,
  DropdownMenuTrigger: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => <button {...props}>{children}</button>,
}))
mock.module('@/components/ui/tooltip', () => ({
  Tooltip: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  TooltipContent: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  TooltipProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  TooltipTrigger: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}))
mock.module('lucide-react', () => new Proxy({}, { get: () => () => <span /> }))

import { DeleteUserDialog } from './delete-user-dialog'
import { SendEmailDialog } from './send-email-dialog'
import { UserHeader } from './user-header'
import { UserTable } from './user-table'
import type { User } from '@/lib/api/admin/users'

globalThis.IS_REACT_ACT_ENVIRONMENT = true

const user: User = {
  id: 'user-1',
  username: 'Ada Lovelace',
  email: 'ada@example.com',
  is_active: true,
  approval_status: 'approved',
  status: 'active',
  is_superuser: false,
  email_verified: true,
  avatar_url: null,
  locale: 'en',
  created_at: '2026-01-02T03:04:00Z',
  last_login: null,
  auth_source: 'local',
  external_id: null,
  force_password_change: false,
  password_expiration_exempt: false,
  roles: [],
  sso_connections: [],
}

const renderers: ReactTestRenderer[] = []

function render(component: React.ReactNode) {
  let renderer: ReactTestRenderer
  act(() => {
    renderer = create(component)
  })
  renderers.push(renderer!)
  return renderer!
}

function button(renderer: ReactTestRenderer, label: string) {
  return renderer.root.findAllByType('button').find(node => node.children.includes(label))!
}

afterEach(() => {
  for (const renderer of renderers) act(() => renderer.unmount())
  renderers.length = 0
  mock.restore()
  toast.success.mockClear()
  toast.warning.mockClear()
})

describe('dashboard user administration semantic behavior', () => {
  test('renders the user heading and exposes its create action', () => {
    const onCreateClick = mock(() => {})
    const renderer = render(<UserHeader onCreateClick={onCreateClick} />)

    expect(renderer.root.findByType('h1').children).toEqual(['title'])
    act(() => button(renderer, 'createUser').props.onClick())
    expect(onCreateClick).toHaveBeenCalledTimes(1)
  })

  test('renders an accessible empty user table and keeps superuser actions read-only', () => {
    const empty = render(<UserTable users={[]} />)
    expect(empty.root.findAllByType('th').map(cell => cell.children[0])).toEqual([
      'allUsers', 'email', 'status', 'passwordStatus', 'createdAt',
    ])
    expect(empty.root.findByType('td').children).toEqual(['noUsers'])

    const superuser = render(<UserTable users={[{ ...user, is_superuser: true }]} />)
    const actions = superuser.root.findAllByType('button').map(node => node.children.join(''))
    expect(actions.some(label => label.includes('edit'))).toBe(true)
    expect(actions.some(label => label.includes('deactivate'))).toBe(false)
    expect(actions.some(label => label.includes('delete'))).toBe(false)
  })

  test('sends the selected user through status and edit actions', async () => {
    const onEdit = mock(() => {})
    const onStatusChange = mock(() => {})
    const renderer = render(<UserTable users={[user]} onEdit={onEdit} onStatusChange={onStatusChange} />)

    act(() => button(renderer, 'edit').props.onClick())
    await act(async () => button(renderer, 'deactivate').props.onClick())

    expect(onEdit).toHaveBeenCalledWith(user)
    expect(usersApi.deactivateUser).toHaveBeenCalledWith('user-1')
    expect(onStatusChange).toHaveBeenCalledWith(user)
    expect(toast.success).toHaveBeenCalledWith('userDeactivated')
  })

  test('validates email fields before submitting the selected recipients', async () => {
    const renderer = render(<SendEmailDialog open onOpenChange={mock(() => {})} users={[user]} />)
    const inputs = renderer.root.findAllByType('input')
    const content = renderer.root.findByType('textarea')

    await act(async () => button(renderer, 'send').props.onClick())
    expect(inputs[0].props['aria-invalid']).toBe(true)
    expect(usersApi.sendEmail).not.toHaveBeenCalled()

    act(() => inputs[0].props.onChange({ target: { value: 'Welcome' } }))
    act(() => content.props.onChange({ target: { value: 'Hello Ada' } }))
    await act(async () => button(renderer, 'send').props.onClick())

    expect(usersApi.sendEmail).toHaveBeenCalledWith(['user-1'], 'Welcome', 'Hello Ada', { silent: true })
    expect(toast.success).toHaveBeenCalledWith('emailSent:1')
  })

  test('does not delete without a selected user and preserves the dialog after an API error', async () => {
    const onOpenChange = mock(() => {})
    const renderer = render(<DeleteUserDialog open onOpenChange={onOpenChange} user={null} />)

    await act(async () => button(renderer, 'delete').props.onClick())
    expect(usersApi.deleteUser).not.toHaveBeenCalled()

    usersApi.deleteUser.mockRejectedValueOnce(new Error('unavailable'))
    act(() => renderer.update(<DeleteUserDialog open onOpenChange={onOpenChange} user={user} />))
    await act(async () => button(renderer, 'delete').props.onClick())
    expect(usersApi.deleteUser).toHaveBeenCalledWith('user-1')
    expect(onOpenChange).not.toHaveBeenCalled()
  })
})
