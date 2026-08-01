import { describe, expect, mock, test } from 'bun:test'
import { DeleteAPIKeyDialog } from './delete-api-key-dialog'

const deleteAPIKey = mock(async () => {})
const successToast = mock(() => {})

const jsx = (type: unknown, props: Record<string, unknown> = {}) => ({ type, props })
let isDeleting = false
mock.module('react', () => ({
  useState: (initial: unknown) => (typeof initial === 'boolean' ? [isDeleting, (v: unknown) => { isDeleting = typeof v === 'function' ? (v as (o: boolean) => boolean)(isDeleting) : v }] : [initial, () => {}]),
  useEffect: () => {},
}))
mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('sonner', () => ({ toast: { success: successToast, error: mock(() => {}) } }))
mock.module('@/lib/api', () => ({ apiKeysApi: { deleteAPIKey } }))
mock.module('@/components/ui/button', () => ({
  Button: ({ children, ...props }: { children?: React.ReactNode } & Record<string, unknown>) => ({ type: 'button', props: { ...props, children } }),
}))
mock.module('@/components/ui/dialog', () => ({
  Dialog: ({ children }: { children?: React.ReactNode }) => ({ type: 'dialog', props: { children } }),
  DialogContent: ({ children }: { children?: React.ReactNode }) => ({ type: 'dialog-content', props: { children } }),
  DialogDescription: ({ children }: { children?: React.ReactNode }) => ({ type: 'p', props: { children } }),
  DialogFooter: ({ children }: { children?: React.ReactNode }) => ({ type: 'footer', props: { children } }),
  DialogHeader: ({ children }: { children?: React.ReactNode }) => ({ type: 'header', props: { children } }),
  DialogTitle: ({ children }: { children?: React.ReactNode }) => ({ type: 'h2', props: { children } }),
}))

function findButtons(node: unknown): { type: unknown; props: Record<string, unknown> }[] {
  if (!node || typeof node !== 'object' || !('type' in node) || !('props' in node)) return []
  const n = node as { type: unknown; props: Record<string, unknown> & { children?: unknown } }
  const matches = (n.type === 'button' || (typeof n.type === 'function' && n.type.name === 'Button')) ? [n as { type: unknown; props: Record<string, unknown> }] : []
  const children = n.props?.children
  return [...matches, ...(Array.isArray(children) ? children.flatMap(findButtons) : findButtons(children))]
}

describe('DeleteAPIKeyDialog', () => {
  test('deletes the key and notifies on success', async () => {
    isDeleting = false
    const onOpenChange = mock(() => {})
    const onSuccess = mock(() => {})
    const tree = DeleteAPIKeyDialog({ open: true, onOpenChange, apiKey: { id: 'key-1', name: 'My Key' } as never, onSuccess })

    const buttons = findButtons(tree)
    const deleteButton = buttons[buttons.length - 1]
    await (deleteButton.props.onClick as () => Promise<void>)()
    expect(deleteAPIKey).toHaveBeenCalledWith('key-1')
    expect(successToast).toHaveBeenCalledWith('keyDeleted')
    expect(onSuccess).toHaveBeenCalled()
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })

  test('cancel button closes without deleting', () => {
    isDeleting = false
    deleteAPIKey.mockClear()
    const onOpenChange = mock(() => {})
    const tree = DeleteAPIKeyDialog({ open: true, onOpenChange, apiKey: { id: 'key-1', name: 'My Key' } as never })

    const buttons = findButtons(tree)
    ;(buttons[0].props.onClick as () => void)()
    expect(onOpenChange).toHaveBeenCalledWith(false)
    expect(deleteAPIKey).not.toHaveBeenCalled()
  })

  test('survives a failed delete', async () => {
    isDeleting = false
    deleteAPIKey.mockRejectedValueOnce(new Error('boom'))
    const onOpenChange = mock(() => {})
    const tree = DeleteAPIKeyDialog({ open: true, onOpenChange, apiKey: { id: 'key-1', name: 'My Key' } as never })

    const buttons = findButtons(tree)
    const deleteButton = buttons[buttons.length - 1]
    await (deleteButton.props.onClick as () => Promise<void>)()
    expect(onOpenChange).not.toHaveBeenCalled()
  })
})
