import { afterEach, beforeEach, describe, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from 'react-test-renderer'

const teamsApi = {
  createTeam: mock(),
  updateTeam: mock(),
}
const toast = { success: mock() }

mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('sonner', () => ({ toast }))
mock.module('@/lib/api/admin', () => ({ teamsApi }))
mock.module('@/lib/validation', () => ({
  clearValidationError: (errors: Record<string, string>, field: string) => {
    const next = { ...errors }
    delete next[field]
    return next
  },
  formatValidationSummaryMessage: (_field: string, message: string) => message,
  getValidationSummaryEntries: (errors: Record<string, string>) => Object.entries(errors),
  normalizeValidationErrors: (error: unknown) => error as Record<string, string>,
}))
mock.module('@/components/ui/button', () => ({
  Button: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => <button {...props}>{children}</button>,
}))
mock.module('@/components/ui/input', () => ({
  Input: (props: React.InputHTMLAttributes<HTMLInputElement>) => <input {...props} />,
}))
mock.module('@/components/ui/textarea', () => ({
  Textarea: (props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) => <textarea {...props} />,
}))
mock.module('@/components/ui/label', () => ({
  Label: ({ children, ...props }: React.LabelHTMLAttributes<HTMLLabelElement>) => <label {...props}>{children}</label>,
}))
mock.module('@/components/ui/image-upload', () => ({
  ImageUpload: ({ value, onChange }: { value: string; onChange: (value: string) => void }) => (
    <input aria-label="avatar" value={value} onChange={(event) => onChange(event.target.value)} />
  ),
}))
mock.module('@/components/ui/field', () => ({
  FieldError: ({ children }: { children?: React.ReactNode }) => children ? <p role="alert">{children}</p> : null,
}))
mock.module('@/components/ui/dialog', () => ({
  Dialog: ({ children, open }: { children: React.ReactNode; open: boolean }) => open ? <div role="dialog">{children}</div> : null,
  DialogContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogDescription: ({ children }: { children: React.ReactNode }) => <p>{children}</p>,
  DialogFooter: ({ children }: { children: React.ReactNode }) => <footer>{children}</footer>,
  DialogHeader: ({ children }: { children: React.ReactNode }) => <header>{children}</header>,
  DialogTitle: ({ children }: { children: React.ReactNode }) => <h2>{children}</h2>,
}))

const { TeamDialog } = await import('./team-dialog')

globalThis.IS_REACT_ACT_ENVIRONMENT = true

function input(renderer: ReactTestRenderer, id: string) {
  return renderer.root.findByProps({ id })
}

function submit(renderer: ReactTestRenderer) {
  return renderer.root.findByType('form').props.onSubmit({ preventDefault() {} })
}

beforeEach(() => {
  teamsApi.createTeam.mockReset()
  teamsApi.updateTeam.mockReset()
  toast.success.mockReset()
})

afterEach(() => mock.restore())

describe('TeamDialog team management behavior', () => {
  test('creates a team with trimmed API payload and success callbacks', async () => {
    teamsApi.createTeam.mockResolvedValue({})
    const onOpenChange = mock()
    const onSuccess = mock()
    let renderer: ReactTestRenderer

    await act(() => { renderer = create(<TeamDialog open onOpenChange={onOpenChange} onSuccess={onSuccess} />) })
    await act(() => input(renderer!, 'name').props.onChange({ target: { value: '  Platform  ' } }))
    await act(() => input(renderer!, 'description').props.onChange({ target: { value: '  Shared work  ' } }))
    await act(() => renderer!.root.findByProps({ 'aria-label': 'avatar' }).props.onChange({ target: { value: '  /team.png  ' } }))
    await act(async () => { await submit(renderer!) })

    expect(teamsApi.createTeam).toHaveBeenCalledWith({ name: 'Platform', description: 'Shared work', avatar_url: '/team.png' })
    expect(toast.success).toHaveBeenCalledWith('teamCreated')
    expect(onOpenChange).toHaveBeenCalledWith(false)
    expect(onSuccess).toHaveBeenCalledTimes(1)
    act(() => renderer!.unmount())
  })

  test('edits an existing team and omits blank optional fields', async () => {
    teamsApi.updateTeam.mockResolvedValue({})
    const onOpenChange = mock()
    const onSuccess = mock()
    let renderer: ReactTestRenderer

    await act(() => {
      renderer = create(<TeamDialog open onOpenChange={onOpenChange} onSuccess={onSuccess} team={{ id: 'team-1', name: 'Core', description: 'Old', avatar_url: '/old.png' } as never} />)
    })
    await act(() => input(renderer!, 'name').props.onChange({ target: { value: '  Core team ' } }))
    await act(() => input(renderer!, 'description').props.onChange({ target: { value: '  ' } }))
    await act(() => renderer!.root.findByProps({ 'aria-label': 'avatar' }).props.onChange({ target: { value: ' ' } }))
    await act(async () => { await submit(renderer!) })

    expect(teamsApi.updateTeam).toHaveBeenCalledWith('team-1', { name: 'Core team', description: undefined, avatar_url: undefined })
    expect(toast.success).toHaveBeenCalledWith('teamUpdated')
    expect(onOpenChange).toHaveBeenCalledWith(false)
    expect(onSuccess).toHaveBeenCalledTimes(1)
    act(() => renderer!.unmount())
  })

  test('keeps submission unavailable until a non-blank team name is entered', async () => {
    let renderer: ReactTestRenderer
    await act(() => { renderer = create(<TeamDialog open onOpenChange={mock()} />) })

    const save = renderer!.root.findAllByType('button').find((button) => button.props.type === 'submit')!
    expect(save.props.disabled).toBe(true)
    await act(async () => { await submit(renderer!) })
    expect(teamsApi.createTeam).not.toHaveBeenCalled()

    await act(() => input(renderer!, 'name').props.onChange({ target: { value: 'Ready' } }))
    expect(renderer!.root.findAllByType('button').find((button) => button.props.type === 'submit')!.props.disabled).toBe(false)
    act(() => renderer!.unmount())
  })

  test('renders returned validation errors and leaves the dialog open', async () => {
    teamsApi.createTeam.mockRejectedValue({ name: 'Already exists', description: 'Too long' })
    const onOpenChange = mock()
    let renderer: ReactTestRenderer

    await act(() => { renderer = create(<TeamDialog open onOpenChange={onOpenChange} />) })
    await act(() => input(renderer!, 'name').props.onChange({ target: { value: 'Duplicate' } }))
    await act(async () => { await submit(renderer!) })

    const alerts = renderer!.root.findAllByProps({ role: 'alert' }).map((node) => node.children.join(''))
    expect(alerts).toContain('Already exists')
    expect(alerts).toContain('Too long')
    expect(input(renderer!, 'name').props['aria-invalid']).toBe(true)
    expect(onOpenChange).not.toHaveBeenCalled()
    act(() => renderer!.unmount())
  })
})
