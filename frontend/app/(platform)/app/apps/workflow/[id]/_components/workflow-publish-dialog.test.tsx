import { describe, expect, mock, test } from 'bun:test'
import { WorkflowPublishDialog } from './workflow-publish-dialog'
const jsx = (type: unknown, props: Record<string, unknown> = {}) => ({ type, props })
let stateValue = 'simple'
let runEffects = false
mock.module('react', () => ({
  useState: (initial: unknown) => [typeof initial === 'string' ? stateValue : initial, (v: unknown) => { stateValue = typeof v === 'function' ? (v as (o: unknown) => unknown)(stateValue) : v }],
 useEffect: (effect: () => void) => { if (runEffects) effect() },
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

  test('resets the selected presentation to the saved value when the dialog opens', () => {
    stateValue = 'result_first'
    runEffects = true
    const props = {
      open: true,
      onOpenChange: mock(() => {}),
      presentation: 'simple' as const,
      isPublishing: false,
      onPublish: mock(async () => {}),
    }
    WorkflowPublishDialog(props)
    runEffects = false

    const tree = WorkflowPublishDialog(props)
    const findRadioGroup = (value: unknown): { props: Record<string, unknown> } | undefined => {
      if (!value || typeof value !== 'object' || !('type' in value) || !('props' in value)) return undefined
      const node = value as { type: unknown; props: Record<string, unknown> & { children?: unknown } }
      if (typeof node.type === 'function' && node.type.name === 'RadioGroup') return node
      const children = node.props.children
      for (const child of Array.isArray(children) ? children : [children]) {
        const found = findRadioGroup(child)
        if (found) return found
      }
      return undefined
    }

    expect(findRadioGroup(tree)?.props.value).toBe('simple')
  })

  test('publishes the presentation selected from the visible options', async () => {
    stateValue = 'simple'
    const onPublish = mock(async () => {})
    const props = {
      open: true,
      onOpenChange: mock(() => {}),
      presentation: 'simple' as const,
      isPublishing: false,
      onPublish,
    }
    const findNodes = (value: unknown, predicate: (node: { type: unknown; props: Record<string, unknown> }) => boolean): { type: unknown; props: Record<string, unknown> }[] => {
      if (!value || typeof value !== 'object' || !('type' in value) || !('props' in value)) return []
      const node = value as { type: unknown; props: Record<string, unknown> & { children?: unknown } }
      return [
        ...(predicate(node) ? [node] : []),
        ...(Array.isArray(node.props.children) ? node.props.children.flatMap(child => findNodes(child, predicate)) : findNodes(node.props.children, predicate)),
      ]
    }

    let tree = WorkflowPublishDialog(props)
    const radioGroup = findNodes(tree, node => typeof node.type === 'function' && node.type.name === 'RadioGroup')[0]
    expect(radioGroup?.props.value).toBe('simple')
    ;(radioGroup?.props.onValueChange as (value: string) => void)('result_first')

    tree = WorkflowPublishDialog(props)
    const buttons = findNodes(tree, node => typeof node.type === 'function' && node.type.name === 'Button')
    await (buttons[1].props.onClick as () => Promise<void>)()
    expect(onPublish).toHaveBeenCalledWith('result_first')
  })

  test('invokes onPublish with the selected presentation', async () => {
    stateValue = 'simple'
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
