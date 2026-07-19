import { afterEach, beforeEach, describe, expect, mock, test } from 'bun:test'
import { GlobalRegistrator } from '@happy-dom/global-registrator'
import React from 'react'

GlobalRegistrator.register()

const apiKeysApi = {
  createAPIKey: mock(),
  deleteAPIKey: mock(),
}
const toast = { success: mock(), error: mock() }

mock.module('@/lib/api', () => ({
  apiKeysApi,
  agentsApi: { getAgents: mock(() => Promise.resolve({ items: [] })) },
  workflowsApi: { getWorkflows: mock(() => Promise.resolve({ items: [] })) },
}))
mock.module('sonner', () => ({ toast }))
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('@/lib/validation', () => ({
  clearValidationError: (errors: Record<string, string>, field: string) => {
    const rest = { ...errors }
    delete rest[field]
    return rest
  },
  getValidationSummaryEntries: (errors: Record<string, string>) => Object.entries(errors),
  normalizeValidationErrors: (error: unknown) => error as Record<string, string>,
  formatValidationSummaryMessage: (_field: string, message: string) => message,
}))
mock.module('@/components/ui/button', () => ({
  Button: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => <button {...props}>{children}</button>,
}))
mock.module('@/components/ui/input', () => ({
  Input: (props: React.InputHTMLAttributes<HTMLInputElement>) => <input {...props} />,
}))
mock.module('@/components/ui/number-input', () => ({
  NumberInput: ({ onChange, ...props }: { onChange: (value: number) => void } & React.InputHTMLAttributes<HTMLInputElement>) => (
    <input {...props} onChange={(event) => onChange(Number(event.target.value))} />
  ),
}))
mock.module('@/components/ui/label', () => ({ Label: ({ children, ...props }: React.LabelHTMLAttributes<HTMLLabelElement>) => <label {...props}>{children}</label> }))
mock.module('@/components/ui/switch', () => ({ Switch: () => null }))
mock.module('@/components/ui/checkbox', () => ({ Checkbox: () => null }))
mock.module('@/components/ui/scroll-area', () => ({ ScrollArea: ({ children }: { children: React.ReactNode }) => <div>{children}</div> }))
mock.module('@/components/ui/field', () => ({ FieldError: ({ children }: { children?: React.ReactNode }) => children ? <p>{children}</p> : null }))
mock.module('@/components/ui/dialog', () => ({
  Dialog: ({ children, open }: { children: React.ReactNode; open: boolean }) => open ? <div>{children}</div> : null,
  DialogContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogDescription: ({ children }: { children: React.ReactNode }) => <p>{children}</p>,
  DialogFooter: ({ children }: { children: React.ReactNode }) => <footer>{children}</footer>,
  DialogHeader: ({ children }: { children: React.ReactNode }) => <header>{children}</header>,
  DialogTitle: ({ children }: { children: React.ReactNode }) => <h2>{children}</h2>,
}))
mock.module('@/components/ui/alert', () => ({
  Alert: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDescription: ({ children }: { children: React.ReactNode }) => <p>{children}</p>,
}))

const { cleanup, fireEvent, render, screen, waitFor } = await import('@testing-library/react')
const { APIKeyDialog } = await import('./api-key-dialog')
const { DeleteAPIKeyDialog } = await import('./delete-api-key-dialog')
const { ShowKeyDialog } = await import('./show-key-dialog')

describe('API key dialogs', () => {
  beforeEach(() => {
    apiKeysApi.createAPIKey.mockReset()
    apiKeysApi.deleteAPIKey.mockReset()
    toast.success.mockReset()
    toast.error.mockReset()
  })

  afterEach(cleanup)

  test('creates a key and returns its one-time secret', async () => {
    const onOpenChange = mock()
    const onSuccess = mock()
    apiKeysApi.createAPIKey.mockResolvedValue({ key: 'clsk_secret' })

    render(<APIKeyDialog open onOpenChange={onOpenChange} onSuccess={onSuccess} />)
    fireEvent.change(screen.getByLabelText('name'), { target: { value: 'deploy' } })
    fireEvent.click(screen.getByRole('button', { name: 'create' }))

    await waitFor(() => expect(apiKeysApi.createAPIKey).toHaveBeenCalledWith(expect.objectContaining({ name: 'deploy' })))
    expect(toast.success).toHaveBeenCalledWith('keyCreated')
    expect(onSuccess).toHaveBeenCalledWith('clsk_secret')
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })

  test('shows field validation errors returned by key creation', async () => {
    apiKeysApi.createAPIKey.mockRejectedValue({ name: 'Name is already in use' })

    render(<APIKeyDialog open onOpenChange={mock()} />)
    fireEvent.change(screen.getByLabelText('name'), { target: { value: 'deploy' } })
    fireEvent.click(screen.getByRole('button', { name: 'create' }))

    expect((await screen.findAllByText('Name is already in use')).length).toBe(2)
  })

  test('deletes a key only on a successful request', async () => {
    const onOpenChange = mock()
    const onSuccess = mock()
    apiKeysApi.deleteAPIKey.mockResolvedValue({})

    render(<DeleteAPIKeyDialog open onOpenChange={onOpenChange} onSuccess={onSuccess} apiKey={{ id: 'key-1', name: 'deploy' } as never} />)
    fireEvent.click(screen.getByRole('button', { name: 'delete' }))

    await waitFor(() => expect(apiKeysApi.deleteAPIKey).toHaveBeenCalledWith('key-1'))
    expect(toast.success).toHaveBeenCalledWith('keyDeleted')
    expect(onSuccess).toHaveBeenCalledTimes(1)
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })

  test('keeps the delete dialog open when deletion fails', async () => {
    const onOpenChange = mock()
    apiKeysApi.deleteAPIKey.mockRejectedValue(new Error('network'))

    render(<DeleteAPIKeyDialog open onOpenChange={onOpenChange} apiKey={{ id: 'key-1', name: 'deploy' } as never} />)
    fireEvent.click(screen.getByRole('button', { name: 'delete' }))

    await waitFor(() => expect(apiKeysApi.deleteAPIKey).toHaveBeenCalledWith('key-1'))
    expect(onOpenChange).not.toHaveBeenCalled()
  })

  test('reports clipboard failures when showing a new key', async () => {
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: mock(() => Promise.reject(new Error('denied'))) } })

    render(<ShowKeyDialog open onOpenChange={mock()} apiKey="clsk_secret" />)
    fireEvent.click(screen.getAllByRole('button')[0])

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('copyFailed'))
  })
})
