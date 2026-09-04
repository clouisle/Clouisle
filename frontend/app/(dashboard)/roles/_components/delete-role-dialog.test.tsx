import { afterEach, beforeEach, describe, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'

const deleteRole = mock()
const toast = { success: mock() }

mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('sonner', () => ({ toast }))
mock.module('@/lib/api/admin/roles', () => ({ rolesApi: { deleteRole } }))
mock.module('@/components/ui/alert-dialog', () => ({
  AlertDialog: ({ children, open }: { children: React.ReactNode; open: boolean }) => open ? <div role="dialog">{children}</div> : null,
  AlertDialogAction: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => <button {...props}>{children}</button>,
  AlertDialogCancel: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => <button {...props}>{children}</button>,
  AlertDialogContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogDescription: ({ children }: { children: React.ReactNode }) => <p>{children}</p>,
  AlertDialogFooter: ({ children }: { children: React.ReactNode }) => <footer>{children}</footer>,
  AlertDialogHeader: ({ children }: { children: React.ReactNode }) => <header>{children}</header>,
  AlertDialogTitle: ({ children }: { children: React.ReactNode }) => <h2>{children}</h2>,
}))

const { DeleteRoleDialog } = await import('./delete-role-dialog')

globalThis.IS_REACT_ACT_ENVIRONMENT = true

let renderer: ReactTestRenderer

beforeEach(() => {
  deleteRole.mockReset()
  toast.success.mockReset()
})

afterEach(() => {
  if (renderer) act(() => renderer.unmount())
})

function render(role = { id: 'role-1', name: 'Editor' } as never, onSuccess = mock(), onOpenChange = mock()) {
  act(() => { renderer = create(<DeleteRoleDialog open role={role} onSuccess={onSuccess} onOpenChange={onOpenChange} />) })
  return { onSuccess, onOpenChange }
}

describe('DeleteRoleDialog', () => {
  test('deletes the selected role then reports success and closes', async () => {
    deleteRole.mockResolvedValue(undefined)
    const { onSuccess, onOpenChange } = render()

    await act(async () => renderer.root.findAllByType('button')[1].props.onClick())

    expect(deleteRole).toHaveBeenCalledWith('role-1')
    expect(toast.success).toHaveBeenCalledWith('roleDeleted')
    expect(onSuccess).toHaveBeenCalledTimes(1)
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })

  test('does not call the API when no role is selected', async () => {
    render(null)

    await act(async () => renderer.root.findAllByType('button')[1].props.onClick())

    expect(deleteRole).not.toHaveBeenCalled()
    expect(toast.success).not.toHaveBeenCalled()
  })

  test('keeps the dialog open when deletion fails', async () => {
    deleteRole.mockRejectedValue(new Error('forbidden'))
    const { onSuccess, onOpenChange } = render()

    await act(async () => renderer.root.findAllByType('button')[1].props.onClick())

    expect(onSuccess).not.toHaveBeenCalled()
    expect(onOpenChange).not.toHaveBeenCalled()
    expect(toast.success).not.toHaveBeenCalled()
  })
})
