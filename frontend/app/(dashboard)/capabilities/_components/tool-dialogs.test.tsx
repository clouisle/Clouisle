import { afterEach, beforeAll, describe, expect, it, mock } from 'bun:test'
import { Window } from 'happy-dom'
import * as React from 'react'
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'

const window = new Window({ url: 'http://localhost' })
Object.assign(globalThis, {
  window,
  document: window.document,
  navigator: window.navigator,
  HTMLElement: window.HTMLElement,
})
;(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true

const deleteTool = mock(async () => {})
const listToolShares = mock(async () => ({ shares: [] as ToolShare[] }))
const shareTool = mock(async () => {})
const unshareTool = mock(async () => {})
const toastSuccess = mock()

mock.module('next-intl', () => ({
  useTranslations: (namespace: string) => (key: string, values?: Record<string, string>) =>
    `${namespace}.${key}${values ? `:${Object.values(values).join(',')}` : ''}`,
}))
mock.module('sonner', () => ({ toast: { success: toastSuccess } }))
mock.module('lucide-react', () => ({
  Loader2: () => <span>loader</span>,
  Share2: () => <span>share-icon</span>,
  Trash2: () => <span>trash-icon</span>,
  Users: () => <span>users-icon</span>,
}))
mock.module('@/lib/api/admin', () => ({
  adminToolsApi: { delete: deleteTool, listToolShares, shareTool, unshareTool },
}))
mock.module('@/lib/validation', () => ({
  clearValidationError: (errors: Record<string, string>, field: string) => {
    const next = { ...errors }
    delete next[field]
    return next
  },
  getValidationSummaryEntries: (errors: Record<string, string>) => Object.entries(errors),
  mapValidationErrors: () => ({ team_id: 'invalid team' }),
  normalizeValidationErrors: (error: unknown) => error,
  formatValidationSummaryMessage: (field: string, message: string) => `${field}: ${message}`,
}))

const SelectContext = React.createContext<(value: string) => void>(() => {})
mock.module('@/components/ui/select', () => ({
  Select: ({ children, onValueChange }: { children: React.ReactNode; onValueChange: (value: string) => void }) => (
    <SelectContext.Provider value={onValueChange}>{children}</SelectContext.Provider>
  ),
  SelectContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectItem: ({ children, value }: { children: React.ReactNode; value: string }) => {
    const onValueChange = React.useContext(SelectContext)
    return <button data-select-value={value} onClick={() => onValueChange(value)}>{children}</button>
  },
  SelectTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectValue: ({ children }: { children: React.ReactNode }) => <span>{children}</span>,
}))
mock.module('@/components/ui/button', () => ({
  Button: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => <button {...props}>{children}</button>,
}))
mock.module('@/components/ui/dialog', () => ({
  Dialog: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogDescription: ({ children }: { children: React.ReactNode }) => <p>{children}</p>,
  DialogFooter: ({ children }: { children: React.ReactNode }) => <footer>{children}</footer>,
  DialogHeader: ({ children }: { children: React.ReactNode }) => <header>{children}</header>,
  DialogTitle: ({ children }: { children: React.ReactNode }) => <h2>{children}</h2>,
}))
mock.module('@/components/ui/alert-dialog', () => ({
  AlertDialog: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogAction: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => <button {...props}>{children}</button>,
  AlertDialogCancel: ({ children }: { children: React.ReactNode }) => <button>{children}</button>,
  AlertDialogContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogDescription: ({ children }: { children: React.ReactNode }) => <p>{children}</p>,
  AlertDialogFooter: ({ children }: { children: React.ReactNode }) => <footer>{children}</footer>,
  AlertDialogHeader: ({ children }: { children: React.ReactNode }) => <header>{children}</header>,
  AlertDialogTitle: ({ children }: { children: React.ReactNode }) => <h2>{children}</h2>,
}))
mock.module('@/components/ui/badge', () => ({ Badge: ({ children }: { children: React.ReactNode }) => <div>{children}</div> }))
mock.module('@/components/ui/field', () => ({ FieldError: ({ children }: { children: React.ReactNode }) => <p>{children}</p> }))
mock.module('@/components/ui/label', () => ({ Label: ({ children }: { children: React.ReactNode }) => <div>{children}</div> }))
mock.module('@/components/ui/scroll-area', () => ({ ScrollArea: ({ children }: { children: React.ReactNode }) => <div>{children}</div> }))

type Tool = import('@/lib/api').Tool
type ToolShare = import('@/lib/api').ToolShare
let DeleteToolDialog: typeof import('./delete-tool-dialog').DeleteToolDialog
let ToolShareDialog: typeof import('./tool-share-dialog').ToolShareDialog

beforeAll(async () => {
  ;({ DeleteToolDialog } = await import('./delete-tool-dialog'))
  ;({ ToolShareDialog } = await import('./tool-share-dialog'))
})

const tool = { id: 'tool-1', display_name: 'Search', team_id: 'owner' } as Tool
const existingShare = {
  id: 'share-1',
  shared_with_team_id: 'team-2',
  shared_with_team_name: 'Beta',
  permission: 'read_only',
  shared_by_name: 'Admin',
} as ToolShare
const roots: Root[] = []

afterEach(() => {
  for (const root of roots.splice(0)) act(() => root.unmount())
  document.body.replaceChildren()
  deleteTool.mockClear()
  listToolShares.mockClear()
  shareTool.mockClear()
  unshareTool.mockClear()
  toastSuccess.mockClear()
  deleteTool.mockImplementation(async () => {})
  listToolShares.mockImplementation(async () => ({ shares: [] }))
  shareTool.mockImplementation(async () => {})
  unshareTool.mockImplementation(async () => {})
})

function render(node: React.ReactNode) {
  const container = document.body.appendChild(document.createElement('div'))
  const root = createRoot(container)
  roots.push(root)
  act(() => root.render(node))
  return container
}

function button(container: HTMLElement, text: string) {
  return [...container.querySelectorAll('button')].find((item) => item.textContent?.includes(text))!
}

async function click(element: HTMLElement) {
  await act(async () => {
    element.click()
    await Promise.resolve()
    await Promise.resolve()
  })
}

describe('DeleteToolDialog callbacks', () => {
  it('closes on cancel and skips deletion without a tool id', async () => {
    const onOpenChange = mock()
    const container = render(<DeleteToolDialog open onOpenChange={onOpenChange} tool={{ display_name: 'Draft' } as Tool} />)

    await click(button(container, 'common.cancel'))
    await click(button(container, 'common.delete'))

    expect(onOpenChange).toHaveBeenCalledWith(false)
    expect(deleteTool).not.toHaveBeenCalled()
  })

  it('reports success and closes only after a successful API call', async () => {
    const onOpenChange = mock()
    const onSuccess = mock()
    const container = render(<DeleteToolDialog open onOpenChange={onOpenChange} tool={tool} onSuccess={onSuccess} />)

    await click(button(container, 'common.delete'))

    expect(deleteTool).toHaveBeenCalledWith('tool-1')
    expect(toastSuccess).toHaveBeenCalledWith('tools.toolDeleted')
    expect(onSuccess).toHaveBeenCalledTimes(1)
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })

  it('keeps the dialog open when deletion fails', async () => {
    deleteTool.mockImplementation(async () => { throw new Error('failed') })
    const onOpenChange = mock()
    const onSuccess = mock()
    const container = render(<DeleteToolDialog open onOpenChange={onOpenChange} tool={tool} onSuccess={onSuccess} />)

    await click(button(container, 'common.delete'))

    expect(onSuccess).not.toHaveBeenCalled()
    expect(onOpenChange).not.toHaveBeenCalled()
    expect(button(container, 'common.delete').disabled).toBe(false)
  })
})

describe('ToolShareDialog callbacks', () => {
  it('selects a team and permission, shares, reloads, and reports success', async () => {
    const onSuccess = mock()
    const onOpenChange = mock()
    const container = render(
      <ToolShareDialog tool={tool} open onOpenChange={onOpenChange} availableTeams={[{ id: 'owner', name: 'Owner' }, { id: 'team-1', name: 'Alpha' }]} onSuccess={onSuccess} />
    )
    await act(async () => { await Promise.resolve() })

    await click(container.querySelector('[data-select-value="team-1"]')!)
    await click(container.querySelector('[data-select-value="read_execute"]')!)
    await click(button(container, 'tools.share.shareButton'))

    expect(shareTool).toHaveBeenCalledWith('tool-1', { team_id: 'team-1', permission: 'read_execute' })
    expect(listToolShares).toHaveBeenCalledTimes(2)
    expect(toastSuccess).toHaveBeenCalledWith('tools.share.shareSuccess')
    expect(onSuccess).toHaveBeenCalledTimes(1)

    await click(button(container, 'common.close'))
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })

  it('shows mapped validation errors and restores the share button after failure', async () => {
    shareTool.mockImplementation(async () => { throw new Error('invalid') })
    const originalError = console.error
    console.error = mock(() => {})
    const container = render(
      <ToolShareDialog tool={tool} open onOpenChange={() => {}} availableTeams={[{ id: 'team-1', name: 'Alpha' }]} />
    )
    await act(async () => { await Promise.resolve() })

    await click(container.querySelector('[data-select-value="team-1"]')!)
    await click(button(container, 'tools.share.shareButton'))

    expect(container.textContent).toContain('team_id: invalid team')
    expect(button(container, 'tools.share.shareButton').disabled).toBe(false)
    console.error = originalError
  })

  it('opens the confirmation and unshares the selected team', async () => {
    listToolShares.mockImplementation(async () => ({ shares: [existingShare] }))
    const onSuccess = mock()
    const container = render(
      <ToolShareDialog tool={tool} open onOpenChange={() => {}} availableTeams={[]} onSuccess={onSuccess} />
    )
    await act(async () => { await Promise.resolve() })

    await click(button(container, 'trash-icon'))
    expect(container.textContent).toContain('tools.share.confirmUnshareDesc:Beta')
    await click(button(container, 'tools.share.unshareButton'))

    expect(unshareTool).toHaveBeenCalledWith('tool-1', 'team-2')
    expect(toastSuccess).toHaveBeenCalledWith('tools.share.unshareSuccess')
    expect(onSuccess).toHaveBeenCalledTimes(1)
  })

  it('handles list and unshare failures without reporting success', async () => {
    const consoleError = mock(() => {})
    const originalError = console.error
    console.error = consoleError
    listToolShares.mockImplementationOnce(async () => { throw new Error('load failed') })
    const first = render(<ToolShareDialog tool={tool} open onOpenChange={() => {}} availableTeams={[]} />)
    await act(async () => { await Promise.resolve() })
    expect(first.textContent).toContain('tools.share.noShares')

    listToolShares.mockImplementation(async () => ({ shares: [existingShare] }))
    unshareTool.mockImplementation(async () => { throw new Error('unshare failed') })
    const onSuccess = mock()
    const second = render(<ToolShareDialog tool={tool} open onOpenChange={() => {}} availableTeams={[]} onSuccess={onSuccess} />)
    await act(async () => { await Promise.resolve() })
    await click(button(second, 'trash-icon'))
    await click(button(second, 'tools.share.unshareButton'))

    expect(onSuccess).not.toHaveBeenCalled()
    expect(consoleError).toHaveBeenCalledTimes(2)
    console.error = originalError
  })
})
