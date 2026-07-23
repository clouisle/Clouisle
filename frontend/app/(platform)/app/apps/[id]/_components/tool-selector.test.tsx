import { beforeEach, describe, expect, mock, test } from 'bun:test'
import type { ReactNode } from 'react'
import type { Tool, ToolConfig } from '@/lib/api'

let state: unknown[] = []
let stateIndex = 0
const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })

mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react', () => ({
  useMemo: <T,>(factory: () => T) => factory(),
  useState: <T,>(initial: T) => {
    const index = stateIndex++
    state[index] ??= initial
    return [state[index] as T, (value: T) => { state[index] = value }] as const
  },
}))
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('@/lib/api', () => ({
  isPresetToolCategory: (category: string) => ['time', 'math', 'search', 'web', 'file', 'code', 'sandbox', 'api', 'data', 'other'].includes(category),
  toolsApi: {},
  skillsApi: {},
}))
mock.module('@/contexts/team-context', () => ({ useTeam: () => ({ currentTeam: null }) }))
mock.module('@/lib/utils', () => ({ cn: (...values: unknown[]) => values.flat().filter(Boolean).join(' ') }))

const element = (tag: string) => ({ children, ...props }: { children?: ReactNode }) => ({ type: tag, props: { ...props, children } })
mock.module('@/components/ui/button', () => ({ Button: element('button') }))
mock.module('@/components/ui/badge', () => ({ Badge: element('badge') }))
mock.module('@/components/ui/switch', () => ({ Switch: element('switch') }))
mock.module('@/components/ui/input', () => ({ Input: element('input') }))
mock.module('@/components/ui/dialog', () => ({
  Dialog: element('dialog'),
  DialogContent: element('dialog-content'),
  DialogHeader: element('dialog-header'),
  DialogTitle: element('dialog-title'),
}))
mock.module('@/components/ui/tabs', () => ({
  Tabs: element('tabs'),
  TabsList: element('tabs-list'),
  TabsTrigger: element('tabs-trigger'),
}))
mock.module('lucide-react', () => ({
  Plus: element('svg'),
  Wrench: element('svg'),
  Trash2: element('svg'),
  AlertCircle: element('svg'),
  Search: element('svg'),
  Check: element('svg'),
  Clock3: element('svg'),
  Calculator: element('svg'),
  Globe: element('svg'),
  FolderOpen: element('svg'),
  Code2: element('svg'),
  Link: element('svg'),
  ChartColumn: element('svg'),
}))

const { AddToolButton, ToolSelector } = await import('./tool-selector')

type Tree = { type: unknown; props: Record<string, unknown> }

function resolve(node: ReactNode): Tree | ReactNode {
  if (!node || typeof node !== 'object' || !('type' in node)) return node
  const tree = node as Tree
  return typeof tree.type === 'function'
    ? resolve((tree.type as (props: Record<string, unknown>) => ReactNode)(tree.props))
    : tree
}

function findAll(node: ReactNode, predicate: (tree: Tree) => boolean): Tree[] {
  const matches: Tree[] = []
  for (const child of Array.isArray(node) ? node : [node]) {
    const tree = resolve(child)
    if (Array.isArray(tree)) {
      matches.push(...findAll(tree, predicate))
    } else if (tree && typeof tree === 'object' && 'type' in tree) {
      if (predicate(tree as Tree)) matches.push(tree as Tree)
      matches.push(...findAll((tree as Tree).props.children as ReactNode, predicate))
    }
  }
  return matches
}

function find(node: ReactNode, predicate: (tree: Tree) => boolean): Tree {
  const match = findAll(node, predicate)[0]
  if (!match) throw new Error('Element not found')
  return match
}

function text(node: ReactNode): string {
  if (node == null || typeof node === 'boolean') return ''
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (Array.isArray(node)) return node.map(text).join(' ')
  const tree = resolve(node)
  return tree && typeof tree === 'object' && 'props' in tree ? text((tree as Tree).props.children as ReactNode) : ''
}

const tool = (values: Partial<Tool> & Pick<Tool, 'name' | 'display_name' | 'type' | 'category'>): Tool => ({
  description: `${values.display_name} description`,
  parameters: [],
  is_enabled: true,
  requires_config: false,
  config_fields: [],
  ...values,
})

const builtin = tool({ name: 'clock', display_name: 'Clock', type: 'builtin', category: 'time' })
const custom = tool({ id: 'custom-1', name: 'weather', display_name: 'Weather', type: 'custom', category: 'Operations' })

function renderAdd(overrides: Partial<React.ComponentProps<typeof AddToolButton>> = {}) {
  stateIndex = 0
  return AddToolButton({
    availableTools: [builtin, custom],
    selectedToolNames: [],
    selectedToolIds: [],
    selectedMcpServerIds: [],
    selectedSkillIds: [],
    onAdd: () => {},
    onRemove: () => {},
    ...overrides,
  })
}

beforeEach(() => { state = [] })

describe('AddToolButton', () => {
  test('groups tools, reports type counts, and filters by search and type', () => {
    let tree = renderAdd()
    expect(text(tree)).toContain('dialog.categories.time')
    expect(text(tree)).toContain('Operations')
    expect(text(tree)).toMatch(/dialog\.filters\.all\s+\(\s*2\s*\)/)
    expect(text(tree)).toMatch(/dialog\.filters\.custom\s+\(\s*1\s*\)/)

    const input = find(tree, (node) => node.type === 'input')
    ;(input.props.onChange as (event: { target: { value: string } }) => void)({ target: { value: 'missing' } })
    tree = renderAdd()
    expect(text(tree)).toContain('dialog.noSearchResults')

    ;(find(tree, (node) => node.type === 'input').props.onChange as (event: { target: { value: string } }) => void)({ target: { value: '' } })
    ;(find(tree, (node) => node.type === 'tabs').props.onValueChange as (value: string) => void)('custom')
    tree = renderAdd()
    expect(text(tree)).toContain('Weather')
    expect(text(tree)).not.toContain('Clock description')
  })

  test('removes selected tools and adds unselected tools', () => {
    const onAdd = mock()
    const onRemove = mock()
    const tree = renderAdd({ selectedToolNames: ['clock'], onAdd, onRemove })

    ;(find(tree, (node) => text(node).includes('Clock description') && typeof node.props.onClick === 'function').props.onClick as () => void)()
    ;(find(tree, (node) => text(node).includes('Weather description') && typeof node.props.onClick === 'function').props.onClick as () => void)()

    expect(onRemove).toHaveBeenCalledWith(builtin)
    expect(onAdd).toHaveBeenCalledWith(custom)
  })
})

describe('ToolSelector', () => {
  test('renders empty and missing states and removes the matching configuration', () => {
    const onChange = mock()
    expect(text(ToolSelector({ toolsConfig: [], availableTools: [], onChange }))).toContain('empty')

    const missing: ToolConfig = { type: 'skill', skill_id: 'missing-skill' }
    const selected: ToolConfig = { type: 'builtin', name: 'clock' }
    stateIndex = 0
    const tree = ToolSelector({ toolsConfig: [missing, selected], availableTools: [builtin], onChange })
    expect(text(tree)).toContain('unknownTool')
    expect(text(tree)).toContain('toolNotFound')

    const switches = findAll(tree, (node) => node.type === 'switch')
    ;(switches[1].props.onCheckedChange as () => void)()
    expect(onChange).toHaveBeenCalledWith([missing])
  })
})
