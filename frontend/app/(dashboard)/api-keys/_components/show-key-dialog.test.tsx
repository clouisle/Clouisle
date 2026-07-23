import { beforeEach, describe, expect, mock, test } from 'bun:test'
import type { ReactNode } from 'react'

const writeText = mock(() => Promise.resolve())
const toastSuccess = mock()
const toastError = mock()
const timers: Array<() => void> = []
let state: unknown[] = []
let effects: unknown[][] = []
let stateIndex = 0
let effectIndex = 0

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx }))
mock.module('react', () => ({
  useState: <T,>(initial: T) => {
    const index = stateIndex++
    state[index] ??= initial
    return [state[index] as T, (value: T) => { state[index] = value }] as const
  },
  useEffect: (effect: () => void, dependencies: unknown[]) => {
    const index = effectIndex++
    if (!effects[index] || dependencies.some((value, dependency) => value !== effects[index][dependency])) {
      effects[index] = dependencies
      effect()
    }
  },
}))
mock.module('next-intl', () => ({
  useTranslations: (namespace: string) => (key: string) => `${namespace}.${key}`,
}))
mock.module('sonner', () => ({ toast: { success: toastSuccess, error: toastError } }))

const element = (tag: string) => ({ children, ...props }: { children?: ReactNode }) => ({
  type: tag,
  props: { ...props, children },
})
mock.module('@/components/ui/button', () => ({ Button: element('button') }))
mock.module('@/components/ui/input', () => ({ Input: element('input') }))
mock.module('@/components/ui/dialog', () => ({
  Dialog: element('dialog'),
  DialogContent: element('section'),
  DialogDescription: element('p'),
  DialogFooter: element('footer'),
  DialogHeader: element('header'),
  DialogTitle: element('h2'),
}))
mock.module('@/components/ui/alert', () => ({
  Alert: element('aside'),
  AlertDescription: element('p'),
}))
mock.module('lucide-react', () => ({
  AlertTriangle: element('alert-icon'),
  Check: element('check-icon'),
  Copy: element('copy-icon'),
}))

const { ShowKeyDialog } = await import('./show-key-dialog')

type Tree = { type: unknown; props: Record<string, unknown> }

function resolve(node: ReactNode): Tree | ReactNode {
  if (!node || typeof node !== 'object' || !('type' in node)) return node
  const tree = node as Tree
  return typeof tree.type === 'function'
    ? resolve((tree.type as (props: Record<string, unknown>) => ReactNode)(tree.props))
    : tree
}

function find(node: ReactNode, predicate: (tree: Tree) => boolean): Tree {
  const resolved = resolve(node)
  if (!resolved || typeof resolved !== 'object' || !('type' in resolved)) throw new Error('Element not found')
  const tree = resolved as Tree
  if (predicate(tree)) return tree
  for (const child of Array.isArray(tree.props.children) ? tree.props.children : [tree.props.children]) {
    try {
      return find(child as ReactNode, predicate)
    } catch {
      // Continue searching sibling elements.
    }
  }
  throw new Error('Element not found')
}

function render(open = true, apiKey: string | null = 'secret-key', onOpenChange = mock()) {
  stateIndex = 0
  effectIndex = 0
  return {
    tree: ShowKeyDialog({ open, apiKey, onOpenChange }),
    onOpenChange,
  }
}

beforeEach(() => {
  writeText.mockReset()
  writeText.mockResolvedValue(undefined)
  toastSuccess.mockReset()
  toastError.mockReset()
  state = []
  effects = []
  timers.length = 0
  Object.defineProperty(globalThis, 'navigator', {
    configurable: true,
    value: { clipboard: { writeText } },
  })
  globalThis.setTimeout = ((callback: () => void) => {
    timers.push(callback)
    return timers.length as unknown as ReturnType<typeof setTimeout>
  }) as typeof setTimeout
})

describe('ShowKeyDialog', () => {
  test('forwards visibility, displays the key or empty state, and closes explicitly', () => {
    const onOpenChange = mock()
    const { tree } = render(false, null, onOpenChange)

    expect(find(tree, (node) => node.type === 'dialog').props).toMatchObject({
      open: false,
      onOpenChange,
    })
    expect(find(tree, (node) => node.type === 'input').props).toMatchObject({
      readOnly: true,
      value: '',
    })

    const close = find(tree, (node) => node.props.children === 'common.close')
    ;(close.props.onClick as () => void)()
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })

  test('copies the visible key, shows copied feedback, and resets it after the timer', async () => {
    let { tree } = render()
    expect(find(tree, (node) => node.type === 'input').props.value).toBe('secret-key')

    const copy = find(tree, (node) => node.type === 'button' && node.props.size === 'icon')
    await (copy.props.onClick as () => Promise<void>)()

    expect(writeText).toHaveBeenCalledWith('secret-key')
    expect(toastSuccess).toHaveBeenCalledWith('apiKeys.copied')
    expect(find(render().tree, (node) => node.type === 'check-icon')).toBeDefined()

    timers[0]()
    tree = render().tree
    expect(find(tree, (node) => node.type === 'copy-icon')).toBeDefined()
  })

  test('reports clipboard failures and does not copy without a key', async () => {
    writeText.mockRejectedValueOnce(new Error('denied'))
    let copy = find(render().tree, (node) => node.type === 'button' && node.props.size === 'icon')
    await (copy.props.onClick as () => Promise<void>)()

    expect(toastError).toHaveBeenCalledWith('apiKeys.copyFailed')
    expect(find(render().tree, (node) => node.type === 'copy-icon')).toBeDefined()

    writeText.mockClear()
    copy = find(render(true, null).tree, (node) => node.type === 'button' && node.props.size === 'icon')
    await (copy.props.onClick as () => Promise<void>)()
    expect(writeText).not.toHaveBeenCalled()
  })
})
