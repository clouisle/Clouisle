import { describe, expect, mock, test } from 'bun:test'
import type { ReactNode } from 'react'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
const element = (tag: string) => ({ children, ...props }: { children?: ReactNode }) => ({
  type: tag,
  props: { ...props, children },
})

mock.module('react/jsx-runtime', () => ({
  jsx,
  jsxs: jsx,
  Fragment: Symbol.for('react.fragment'),
}))
mock.module('react/jsx-dev-runtime', () => ({
  jsxDEV: jsx,
  Fragment: Symbol.for('react.fragment'),
}))
mock.module('next-intl', () => ({
  useTranslations: () => (key: string, values?: Record<string, unknown>) =>
    values ? `${key}:${JSON.stringify(values)}` : key,
}))
mock.module('@/components/ui/button', () => ({ Button: element('button') }))
mock.module('@/components/ui/input', () => ({ Input: element('input') }))
mock.module('@/components/ui/tooltip', () => ({
  Tooltip: element('tooltip'),
  TooltipContent: element('tooltip-content'),
  TooltipProvider: element('tooltip-provider'),
  TooltipTrigger: element('tooltip-trigger'),
}))
mock.module('@/components/ui/alert-dialog', () => ({
  AlertDialog: element('alert-dialog'),
  AlertDialogAction: element('alert-dialog-action'),
  AlertDialogCancel: element('alert-dialog-cancel'),
  AlertDialogContent: element('alert-dialog-content'),
  AlertDialogDescription: element('alert-dialog-description'),
  AlertDialogFooter: element('alert-dialog-footer'),
  AlertDialogHeader: element('alert-dialog-header'),
  AlertDialogTitle: element('alert-dialog-title'),
  AlertDialogTrigger: element('alert-dialog-trigger'),
}))
mock.module('lucide-react', () => ({
  Search: element('search-icon'),
  ZoomIn: element('zoom-in-icon'),
  ZoomOut: element('zoom-out-icon'),
  Maximize: element('maximize-icon'),
  MousePointer2: element('select-icon'),
  Trash2: element('trash-icon'),
}))

const { GraphToolbar } = await import('./graph-toolbar')

type Tree = { type: unknown; props: Record<string, unknown> }

function resolve(node: ReactNode): Tree | ReactNode {
  if (!node || typeof node !== 'object' || !('type' in node)) return node
  const tree = node as Tree
  return typeof tree.type === 'function'
    ? resolve((tree.type as (props: Record<string, unknown>) => ReactNode)(tree.props))
    : tree
}

function findAll(node: ReactNode, predicate: (tree: Tree) => boolean): Tree[] {
  const resolved = resolve(node)
  if (Array.isArray(resolved)) return resolved.flatMap((child) => findAll(child, predicate))
  if (!resolved || typeof resolved !== 'object' || !('type' in resolved)) return []
  const tree = resolved as Tree
  return [
    ...(predicate(tree) ? [tree] : []),
    ...findAll(tree.props.children as ReactNode, predicate),
  ]
}

function toolbar(overrides: Partial<React.ComponentProps<typeof GraphToolbar>> = {}) {
  return GraphToolbar({
    searchQuery: 'alice',
    onSearchChange: mock(),
    onZoomIn: mock(),
    onZoomOut: mock(),
    onFitView: mock(),
    entityCount: 4,
    relationCount: 7,
    selectMode: false,
    onToggleSelectMode: mock(),
    ...overrides,
  })
}

describe('GraphToolbar', () => {
  test('shows search, graph stats, and controls wired to their callbacks', () => {
    const onSearchChange = mock()
    const callbacks = [mock(), mock(), mock(), mock()]
    const tree = toolbar({
      onSearchChange,
      onZoomIn: callbacks[0],
      onZoomOut: callbacks[1],
      onFitView: callbacks[2],
      onToggleSelectMode: callbacks[3],
    })

    const input = findAll(tree, (node) => node.type === 'input')[0]
    expect(input.props).toMatchObject({ placeholder: 'searchPlaceholder', value: 'alice' })
    ;(input.props.onChange as (event: { target: { value: string } }) => void)({
      target: { value: 'bob' },
    })
    expect(onSearchChange).toHaveBeenCalledWith('bob')

    const triggers = findAll(tree, (node) => node.type === 'tooltip-trigger')
    expect(triggers).toHaveLength(4)
    triggers.forEach((trigger) => (trigger.props.onClick as () => void)())
    callbacks.forEach((callback) => expect(callback).toHaveBeenCalledTimes(1))
    const stats = findAll(tree, (node) => node.props.className === 'text-xs text-muted-foreground')[0]
    expect(stats.props.children).toEqual([4, ' ', 'entities', ' · ', 7, ' ', 'relations'])
    expect(JSON.stringify(tree)).not.toContain('deleteSelected')
  })

  test('marks select mode active and confirms deletion of selected entities', () => {
    const onDeleteSelected = mock()
    const tree = toolbar({ selectMode: true, selectedCount: 3, onDeleteSelected })

    const selectTrigger = findAll(tree, (node) => node.type === 'tooltip-trigger')[3]
    expect((selectTrigger.props.render as Tree).props.variant).toBe('default')
    const deleteTrigger = findAll(tree, (node) => node.type === 'alert-dialog-trigger')[0]
    expect((deleteTrigger.props.render as Tree).props.children).toEqual([
      expect.anything(),
      'deleteSelected',
      ' (',
      3,
      ')',
    ])
    expect(JSON.stringify(tree)).toContain('deleteSelectedConfirm:{\\"count\\":3}')

    const action = findAll(tree, (node) => node.type === 'alert-dialog-action')[0]
    ;(action.props.onClick as () => void)()
    expect(onDeleteSelected).toHaveBeenCalledTimes(1)
  })
})
