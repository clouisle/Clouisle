import { afterEach, describe, expect, mock, spyOn, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'

import { permissionsApi, rolesApi } from '@/lib/api/admin/roles'
import { ApiError } from '@/lib/api/client'

const translations: Record<string, string> = {
  createRole: 'Create role', editRole: 'Edit role', createRoleDescription: 'Create a role', editRoleDescription: 'Edit a role',
  roleName: 'Role name', roleNamePlaceholder: 'Role name placeholder', description: 'Description', descriptionPlaceholder: 'Description placeholder',
  permissions: 'Permissions', selected: 'selected', searchPermissions: 'Search permissions', noPermissions: 'No permissions',
  roleCreated: 'Role created', roleUpdated: 'Role updated', deleteRole: 'Delete role', deleteRoleConfirm: 'Delete {name}', roleDeleted: 'Role deleted',
  createPermission: 'Create permission', editPermission: 'Edit permission', createPermissionDescription: 'Create permission description', editPermissionDescription: 'Edit permission description',
  scope: 'Scope', scopePlaceholder: 'Scope placeholder', scopeHint: 'Scope hint', code: 'Code', codePlaceholder: 'Code placeholder', codeHint: 'Code hint',
  permissionDescription: 'Permission description', permissionCreated: 'Permission created', permissionUpdated: 'Permission updated', confirmDelete: 'Confirm delete', deletePermissionConfirm: 'Delete {code}', permissionDeleted: 'Permission deleted',
  cancel: 'Cancel', create: 'Create', save: 'Save', delete: 'Delete', loading: 'Loading',
}

mock.module('next-intl', () => ({
  useTranslations: () => (key: string, values?: Record<string, string>) =>
    Object.entries(values ?? {}).reduce((text, [name, value]) => text.replace(`{${name}}`, value), translations[key] ?? key),
}))
mock.module('sonner', () => ({ toast: { success: mock(() => {}) } }))
mock.module('@/components/ui/button', () => ({ Button: (props: React.ComponentProps<'button'>) => <button {...props} /> }))
mock.module('@/components/ui/input', () => ({ Input: (props: React.ComponentProps<'input'>) => <input {...props} /> }))
mock.module('@/components/ui/textarea', () => ({ Textarea: (props: React.ComponentProps<'textarea'>) => <textarea {...props} /> }))
mock.module('@/components/ui/label', () => ({ Label: (props: React.ComponentProps<'label'>) => <label {...props} /> }))
mock.module('@/components/ui/badge', () => ({ Badge: (props: React.ComponentProps<'span'>) => <span {...props} /> }))
mock.module('@/components/ui/checkbox', () => ({ Checkbox: ({ checked }: { checked: boolean }) => <span data-checked={checked} /> }))
mock.module('@/components/ui/field', () => ({ FieldError: ({ children }: { children?: React.ReactNode }) => children ? <span role="alert">{children}</span> : null }))
mock.module('@/components/ui/dialog', () => ({
  Dialog: ({ open, children }: { open: boolean; children: React.ReactNode }) => open ? <>{children}</> : null,
  DialogContent: ({ children }: { children: React.ReactNode }) => <section>{children}</section>,
  DialogDescription: ({ children }: { children: React.ReactNode }) => <p>{children}</p>,
  DialogFooter: ({ children }: { children: React.ReactNode }) => <footer>{children}</footer>,
  DialogHeader: ({ children }: { children: React.ReactNode }) => <header>{children}</header>,
  DialogTitle: ({ children }: { children: React.ReactNode }) => <h2>{children}</h2>,
}))
mock.module('@/components/ui/alert-dialog', () => ({
  AlertDialog: ({ open, children }: { open: boolean; children: React.ReactNode }) => open ? <>{children}</> : null,
  AlertDialogContent: ({ children }: { children: React.ReactNode }) => <section>{children}</section>,
  AlertDialogDescription: ({ children }: { children: React.ReactNode }) => <p>{children}</p>,
  AlertDialogFooter: ({ children }: { children: React.ReactNode }) => <footer>{children}</footer>,
  AlertDialogHeader: ({ children }: { children: React.ReactNode }) => <header>{children}</header>,
  AlertDialogTitle: ({ children }: { children: React.ReactNode }) => <h2>{children}</h2>,
  AlertDialogAction: (props: React.ComponentProps<'button'>) => <button {...props} />,
  AlertDialogCancel: (props: React.ComponentProps<'button'>) => <button {...props} />,
}))

const { RoleDialog } = await import('./roles/_components/role-dialog')
const { PermissionDialog } = await import('./permissions/_components/permission-dialog')
const { DeleteRoleDialog } = await import('./roles/_components/delete-role-dialog')
const { DeletePermissionDialog } = await import('./permissions/_components/delete-permission-dialog')

globalThis.IS_REACT_ACT_ENVIRONMENT = true

async function render(component: React.ReactElement) {
  let renderer!: ReactTestRenderer
  await act(async () => { renderer = create(component) })
  return renderer
}

const findInput = (renderer: ReactTestRenderer, id: string) => renderer.root.findByProps({ id })
const submit = async (renderer: ReactTestRenderer) => act(async () => {
  await renderer.root.findByType('form').props.onSubmit({ preventDefault() {} })
})

afterEach(() => mock.restore())

describe('access management dialogs', () => {
  test('creates a role with selected permission codes and exposes semantic labels', async () => {
    spyOn(permissionsApi, 'getPermissions').mockResolvedValue({ items: [{ id: 'p1', scope: 'knowledge', code: 'knowledge:read', description: 'Read', is_system: false }] } as never)
    const createRole = spyOn(rolesApi, 'createRole').mockResolvedValue({} as never)
    const onSuccess = mock(() => {})
    const onOpenChange = mock(() => {})
    const renderer = await render(<RoleDialog open onOpenChange={onOpenChange} role={null} onSuccess={onSuccess} />)

    expect(renderer.root.findByType('h2').children).toEqual(['Create role'])
    expect(findInput(renderer, 'name').props.required).toBe(true)
    expect(renderer.root.findAllByProps({ role: 'alert' })).toHaveLength(0)
    await act(async () => { findInput(renderer, 'name').props.onChange({ target: { value: 'Editors' } }) })
    await act(async () => { renderer.root.findAllByType('button')[0].props.onClick() })
    await act(async () => { renderer.root.findAllByType('button').filter(button => typeof button.props.onClick === 'function').find(button => button.props.className?.includes('w-full'))!.props.onClick() })
    await submit(renderer)

    expect(createRole).toHaveBeenCalledWith({ name: 'Editors', description: '', permissions: ['knowledge:read'] })
    expect(onSuccess).toHaveBeenCalledTimes(1)
    expect(onOpenChange).toHaveBeenCalledWith(false)
    act(() => renderer.unmount())
  })

  test('shows an empty role permission state and validation errors without completing the action', async () => {
    spyOn(permissionsApi, 'getPermissions').mockResolvedValue({ items: [] } as never)
    const createRole = spyOn(rolesApi, 'createRole').mockRejectedValue(new ApiError(1001, 'Name already exists', { errors: { name: 'Name already exists' } }))
    const onSuccess = mock(() => {})
    const renderer = await render(<RoleDialog open onOpenChange={mock(() => {})} role={null} onSuccess={onSuccess} />)

    expect(JSON.stringify(renderer.toJSON())).toContain('No permissions')
    await act(async () => { findInput(renderer, 'name').props.onChange({ target: { value: 'Editors' } }) })
    await submit(renderer)

    expect(createRole).toHaveBeenCalledTimes(1)
    expect(onSuccess).not.toHaveBeenCalled()
    expect(findInput(renderer, 'name').props['aria-invalid']).toBe(true)
    expect(JSON.stringify(renderer.toJSON())).toContain('Name already exists')
    act(() => renderer.unmount())
  })

  test('updates permission payloads and displays server validation errors', async () => {
    const permission = { id: 'permission-1', scope: 'knowledge', code: 'knowledge:read', description: 'Read content', is_system: false }
    const updatePermission = spyOn(permissionsApi, 'updatePermission').mockResolvedValue(permission)
    const onSuccess = mock(() => {})
    const renderer = await render(<PermissionDialog open onOpenChange={mock(() => {})} permission={permission} onSuccess={onSuccess} />)

    expect(renderer.root.findByType('h2').children).toEqual(['Edit permission'])
    expect(findInput(renderer, 'scope').props.required).toBe(true)
    await act(async () => { findInput(renderer, 'code').props.onChange({ target: { value: 'knowledge:manage' } }) })
    await submit(renderer)
    expect(updatePermission).toHaveBeenCalledWith('permission-1', { scope: 'knowledge', code: 'knowledge:manage', description: 'Read content' })
    expect(onSuccess).toHaveBeenCalledTimes(1)
    act(() => renderer.unmount())
  })

  test('deletes the selected role or permission only and leaves null selections read-only', async () => {
    const deleteRole = spyOn(rolesApi, 'deleteRole').mockResolvedValue({} as never)
    const deletePermission = spyOn(permissionsApi, 'deletePermission').mockResolvedValue({} as never)
    const roleSuccess = mock(() => {})
    const permissionSuccess = mock(() => {})
    const role = await render(<DeleteRoleDialog open onOpenChange={mock(() => {})} role={{ id: 'role-1', name: 'Editors', description: null, is_system_role: false, permissions: [] }} onSuccess={roleSuccess} />)
    await act(async () => { await role.root.findAllByType('button').find(button => button.children.includes('Delete'))!.props.onClick() })
    expect(deleteRole).toHaveBeenCalledWith('role-1')
    expect(roleSuccess).toHaveBeenCalledTimes(1)
    act(() => role.unmount())

    const permission = await render(<DeletePermissionDialog open onOpenChange={mock(() => {})} permission={{ id: 'permission-1', scope: 'knowledge', code: 'knowledge:read', description: null, is_system: false }} onSuccess={permissionSuccess} />)
    await act(async () => { await permission.root.findAllByType('button').find(button => button.children.includes('Delete'))!.props.onClick() })
    expect(deletePermission).toHaveBeenCalledWith('permission-1')
    expect(permissionSuccess).toHaveBeenCalledTimes(1)
    act(() => permission.unmount())

    const readOnly = await render(<DeletePermissionDialog open onOpenChange={mock(() => {})} permission={null} onSuccess={mock(() => {})} />)
    await act(async () => { await readOnly.root.findAllByType('button').find(button => button.children.includes('Delete'))!.props.onClick() })
    expect(deletePermission).toHaveBeenCalledTimes(1)
    act(() => readOnly.unmount())
  })
})
