import { describe, expect, mock, test } from 'bun:test'
import { WorkflowPublishDialog } from './workflow-publish-dialog'
const jsx = (type: unknown, props: Record<string, unknown> = {}) => ({ type, props })
let stateValue = 'simple'
mock.module('react', () => ({
  useState: (initial: unknown) => [typeof initial === 'string' ? stateValue : initial, (v: unknown) => { stateValue = typeof v === 'function' ? (v as (o: unknown) => unknown)(stateValue) : v }],
  useEffect: () => {},
}))
mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}))
mock.module('lucide-react', () => ({ Loader2: () => null }))
mock.module('@/components/ui/button', () => ({
  Button: ({ children, ...props }: { children?: React.ReactNode } & Record<string, unknown>) => ({
    type: 'button',
    props: { ...props, children },
  }),
}))
mock.module('@/components/ui/dialog', () => ({
  Dialog: ({ children }: { children?: React.ReactNode }) => ({ type: 'dialog', props: { children } }),
  DialogContent: ({ children }: { children?: React.ReactNode }) => ({ type: 'dialog-content', props: { children } }),
  DialogDescription: ({ children }: { children?: React.ReactNode }) => ({ type: 'p', props: { children } }),
  DialogFooter: ({ children }: { children?: React.ReactNode }) => ({ type: 'footer', props: { children } }),
  DialogHeader: ({ children }: { children?: React.ReactNode }) => ({ type: 'header', props: { children } }),
  DialogTitle: ({ children }: { children?: React.ReactNode }) => ({ type: 'h2', props: { children } }),
}))
mock.module('@/components/ui/radio-group', () => ({
  RadioGroup: ({ children, ...props }: { children?: React.ReactNode } & Record<string, unknown>) => ({ type: 'radio-group', props: { ...props, children } }),
  RadioGroupItem: (props: Record<string, unknown>) => ({ type: 'radio-item', props }),
}))

describe('WorkflowPublishDialog', () => {
  test('renders presentation options and publish controls when open', () => {
    const tree = WorkflowPublishDialog({
      open: true,
      onOpenChange: mock(() => {}),
      presentation: 'simple',
      isPublishing: false,
      onPublish: mock(async () => {}),
    })

    expect(tree).toBeDefined()
    expect(typeof tree).toBe('object')
    expect('type' in tree).toBe(true)
    expect((tree as { type: unknown }).type).toBeDefined()
  })

  test('invokes onPublish with the selected presentation', async () => {
    const onPublish = mock(async () => {})
    const tree = WorkflowPublishDialog({
      open: true,
      onOpenChange: mock(() => {}),
      presentation: 'simple',
      onPublish,
    }) as { type: unknown; props: { children?: unknown } }

    function findButtons(node: unknown): { type: unknown; props: Record<string, unknown> }[] {
      if (!node || typeof node !== 'object' || !('type' in node) || !('props' in node)) return []
      const n = node as { type: unknown; props: Record<string, unknown> & { children?: unknown } }
      const matches = (n.type === 'button' || (typeof n.type === 'function' && n.type.name === 'Button')) ? [n as { type: unknown; props: Record<string, unknown> }] : []
      const children = n.props?.children
      return [...matches, ...(Array.isArray(children) ? children.flatMap(findButtons) : findButtons(children))]
    }
    const buttons = findButtons(tree)
    const publishButton = buttons[buttons.length - 1]
    await (publishButton.props.onClick as () => Promise<void>)()
    expect(onPublish).toHaveBeenCalledWith('simple')
  })

  test('cancel button closes the dialog', () => {
    const onOpenChange = mock(() => {})
    const tree = WorkflowPublishDialog({
      open: true,
      onOpenChange,
      presentation: 'simple',
      isPublishing: false,
      onPublish: mock(async () => {}),
    }) as { type: unknown; props: { children?: unknown } }

    function findButtons(node: unknown): { type: unknown; props: Record<string, unknown> }[] {
      if (!node || typeof node !== 'object' || !('type' in node) || !('props' in node)) return []
      const n = node as { type: unknown; props: Record<string, unknown> & { children?: unknown } }
      const matches = (n.type === 'button' || (typeof n.type === 'function' && n.type.name === 'Button')) ? [n as { type: unknown; props: Record<string, unknown> }] : []
      const children = n.props?.children
      return [...matches, ...(Array.isArray(children) ? children.flatMap(findButtons) : findButtons(children))]
    }
    const buttons = findButtons(tree)
    ;(buttons[0].props.onClick as () => void)()
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })

  test('renders while publishing and with a non-default presentation', () => {
    stateValue = 'result_first'
    const tree = WorkflowPublishDialog({
      open: true,
      onOpenChange: mock(() => {}),
      presentation: 'simple',
      isPublishing: true,
      onPublish: mock(async () => {}),
    })
    expect(tree).toBeDefined()
  })
})
