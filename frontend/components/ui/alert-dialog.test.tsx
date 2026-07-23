import { expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })

function Root() {}
function Trigger() {}
function Portal() {}
function Backdrop() {}
function Popup() {}
function Title() {}
function Description() {}
function Close() {}
function Button() {}

mock.module('react/jsx-runtime', () => ({
  jsx,
  jsxs: jsx,
  Fragment: Symbol.for('react.fragment'),
}))
mock.module('react/jsx-dev-runtime', () => ({
  jsxDEV: jsx,
  Fragment: Symbol.for('react.fragment'),
}))
mock.module('@base-ui/react/alert-dialog', () => ({
  AlertDialog: { Root, Trigger, Portal, Backdrop, Popup, Title, Description, Close },
}))
mock.module('@/components/ui/button', () => ({ Button }))
mock.module('@/lib/utils', () => ({
  cn: (...values: unknown[]) => values.filter(Boolean).join(' '),
}))

const {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogMedia,
  AlertDialogOverlay,
  AlertDialogPortal,
  AlertDialogTitle,
  AlertDialogTrigger,
} = await import('./alert-dialog')

test('renders dialog primitives with slots and forwarded details', () => {
  const dialog = AlertDialog({ open: true }) as { props: Record<string, unknown> }
  const trigger = AlertDialogTrigger({ children: 'Delete' }) as { props: Record<string, unknown> }
  const portal = AlertDialogPortal({ children: 'Dialog body' }) as {
    props: Record<string, unknown>
  }
  const overlay = AlertDialogOverlay({ className: 'dimmed' }) as { props: Record<string, unknown> }
  const header = AlertDialogHeader({ className: 'heading' }) as { props: Record<string, unknown> }
  const footer = AlertDialogFooter({ className: 'actions' }) as { props: Record<string, unknown> }
  const media = AlertDialogMedia({ className: 'icon' }) as { props: Record<string, unknown> }
  const title = AlertDialogTitle({ children: 'Confirm' }) as { props: Record<string, unknown> }
  const description = AlertDialogDescription({ children: 'Cannot undo' }) as {
    props: Record<string, unknown>
  }

  expect(dialog.props['data-slot']).toBe('alert-dialog')
  expect(trigger.props['data-slot']).toBe('alert-dialog-trigger')
  expect(portal.props['data-slot']).toBe('alert-dialog-portal')
  expect(overlay.props.className).toContain('dimmed')
  expect(header.props.className).toContain('heading')
  expect(footer.props.className).toContain('actions')
  expect(media.props.className).toContain('icon')
  expect(title.props['data-slot']).toBe('alert-dialog-title')
  expect(description.props['data-slot']).toBe('alert-dialog-description')
})

test('composes sized content and action controls with defaults', () => {
  const content = AlertDialogContent({
    children: 'details',
    className: 'warning',
    overlayClassName: 'soft',
    size: 'sm',
  }) as { props: Record<string, unknown> }
  const [overlay, popup] = content.props.children as Array<{ props: Record<string, unknown> }>
  const action = AlertDialogAction({ children: 'Remove', className: 'danger' }) as {
    props: Record<string, unknown>
  }
  const cancel = AlertDialogCancel({ children: 'Keep' }) as { props: Record<string, unknown> }
  const customCancel = AlertDialogCancel({ variant: 'ghost', size: 'sm' }) as {
    props: Record<string, unknown>
  }

  expect((content.type as { name?: string }).name).toBe('AlertDialogPortal')
  expect((overlay.type as { name?: string }).name).toBe('AlertDialogOverlay')
  expect(overlay.props.className).toBe('soft')
  expect(popup.props['data-size']).toBe('sm')
  expect(popup.props.className).toContain('warning')
  expect(action.props['data-slot']).toBe('alert-dialog-action')
  expect(action.props.className).toBe('danger')
  expect((cancel.props.render as { props: Record<string, unknown> }).props.variant).toBe('outline')
  expect((cancel.props.render as { props: Record<string, unknown> }).props.size).toBe('default')
  expect((customCancel.props.render as { props: Record<string, unknown> }).props.variant).toBe(
    'ghost',
  )
  expect((customCancel.props.render as { props: Record<string, unknown> }).props.size).toBe('sm')
})
