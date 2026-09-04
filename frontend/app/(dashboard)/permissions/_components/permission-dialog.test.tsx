import { afterEach, describe, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'

const createPermission = mock(() => Promise.resolve())
const updatePermission = mock(() => Promise.resolve())
const success = mock(() => undefined)
const validationError = new Error('validation error')

mock.module('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}))
mock.module('sonner', () => ({ toast: { success } }))
mock.module('@/lib/api/admin/roles', () => ({
  permissionsApi: { createPermission, updatePermission },
}))
mock.module('@/lib/validation', () => ({
  normalizeValidationErrors: (error: unknown) => error === validationError
    ? { code: 'Code already exists', other: 'Server rejected permission' }
    : {},
  clearValidationError: (errors: Record<string, string>, key: string) => {
    const next = { ...errors }
    delete next[key]
    return next
  },
  getValidationSummaryEntries: (errors: Record<string, string>, inlineFields: Iterable<string>) =>
    Object.entries(errors).filter(([key]) => !new Set(inlineFields).has(key)),
  formatValidationSummaryMessage: (_field: string, message: string) => message,
}))
mock.module('@/components/ui/dialog', () => ({
  Dialog: ({ children }: { children: React.ReactNode }) => children,
  DialogContent: ({ children }: { children: React.ReactNode }) => children,
  DialogDescription: ({ children }: { children: React.ReactNode }) => children,
  DialogFooter: ({ children }: { children: React.ReactNode }) => children,
  DialogHeader: ({ children }: { children: React.ReactNode }) => children,
  DialogTitle: ({ children }: { children: React.ReactNode }) => children,
}))
mock.module('@/components/ui/button', () => ({
  Button: (props: React.ComponentProps<'button'>) => <button {...props} />,
}))
mock.module('@/components/ui/input', () => ({
  Input: (props: React.ComponentProps<'input'>) => <input {...props} />,
}))
mock.module('@/components/ui/label', () => ({
  Label: (props: React.ComponentProps<'label'>) => <label {...props} />,
}))
mock.module('@/components/ui/textarea', () => ({
  Textarea: (props: React.ComponentProps<'textarea'>) => <textarea {...props} />,
}))
mock.module('@/components/ui/field', () => ({
  FieldError: ({ children }: { children?: React.ReactNode }) => children ? <span>{children}</span> : null,
}))

const { PermissionDialog } = await import('./permission-dialog')

globalThis.IS_REACT_ACT_ENVIRONMENT = true

const renderers: ReactTestRenderer[] = []

function render(permission = null) {
  const onOpenChange = mock(() => undefined)
  const onSuccess = mock(() => undefined)
  let renderer: ReactTestRenderer
  act(() => {
    renderer = create(<PermissionDialog open onOpenChange={onOpenChange} permission={permission} onSuccess={onSuccess} />)
  })
  renderers.push(renderer!)
  return { renderer: renderer!, onOpenChange, onSuccess }
}

function change(renderer: ReactTestRenderer, id: string, value: string) {
  act(() => renderer.root.findByProps({ id }).props.onChange({ target: { value } }))
}

afterEach(() => {
  for (const renderer of renderers) act(() => renderer.unmount())
  renderers.length = 0
  createPermission.mockReset()
  updatePermission.mockReset()
  success.mockReset()
})

describe('PermissionDialog', () => {
  test('requires scope and code before creating a permission', () => {
    const { renderer } = render()
    const submit = renderer.root.findAllByType('button').at(-1)!

    expect(submit.props.disabled).toBe(true)
    change(renderer, 'scope', 'projects')
    expect(submit.props.disabled).toBe(true)
    change(renderer, 'code', 'read')
    expect(submit.props.disabled).toBe(false)
  })

  test('creates a permission and closes after a successful save', async () => {
    const { renderer, onOpenChange, onSuccess } = render()
    change(renderer, 'scope', 'projects')
    change(renderer, 'code', 'read')
    change(renderer, 'description', 'Read projects')

    await act(async () => renderer.root.findByType('form').props.onSubmit({ preventDefault() {} }))

    expect(createPermission).toHaveBeenCalledWith({ scope: 'projects', code: 'read', description: 'Read projects' })
    expect(success).toHaveBeenCalledWith('permissionCreated')
    expect(onSuccess).toHaveBeenCalledTimes(1)
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })

  test('loads and updates an existing permission', async () => {
    const permission = { id: 'permission-1', scope: 'users', code: 'read', description: 'Read users', is_system: false }
    const { renderer, onOpenChange, onSuccess } = render(permission)

    expect(renderer.root.findByProps({ id: 'scope' }).props.value).toBe('users')
    expect(renderer.root.findByProps({ id: 'code' }).props.value).toBe('read')
    expect(renderer.root.findByProps({ id: 'description' }).props.value).toBe('Read users')
    change(renderer, 'description', 'List users')

    await act(async () => renderer.root.findByType('form').props.onSubmit({ preventDefault() {} }))

    expect(updatePermission).toHaveBeenCalledWith('permission-1', { scope: 'users', code: 'read', description: 'List users' })
    expect(success).toHaveBeenCalledWith('permissionUpdated')
    expect(onSuccess).toHaveBeenCalledTimes(1)
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })

  test('shows validation errors without reporting success and clears changed field errors', async () => {
    createPermission.mockImplementationOnce(() => Promise.reject(validationError))
    const { renderer, onOpenChange, onSuccess } = render()
    change(renderer, 'scope', 'projects')
    change(renderer, 'code', 'read')

    await act(async () => renderer.root.findByType('form').props.onSubmit({ preventDefault() {} }))

    expect(JSON.stringify(renderer.toJSON())).toContain('Code already exists')
    expect(JSON.stringify(renderer.toJSON())).toContain('Server rejected permission')
    expect(renderer.root.findByProps({ id: 'code' }).props['aria-invalid']).toBe(true)
    expect(onSuccess).not.toHaveBeenCalled()
    expect(onOpenChange).not.toHaveBeenCalled()

    change(renderer, 'code', 'write')
    expect(renderer.root.findByProps({ id: 'code' }).props['aria-invalid']).toBe(false)
  })
})
