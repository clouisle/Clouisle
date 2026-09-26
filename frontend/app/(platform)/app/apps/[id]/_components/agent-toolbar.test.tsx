import { describe, expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })

mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('next/link', () => ({ default: 'Link' }))
mock.module('lucide-react', () => ({
  Settings: 'Settings', ChevronDown: 'ChevronDown', MessageSquare: 'MessageSquare',
  Save: 'Save', Loader2: 'Loader2', PanelLeftClose: 'PanelLeftClose',
  PanelLeft: 'PanelLeft', Code: 'Code', Eye: 'Eye', MoreHorizontal: 'MoreHorizontal',
}))
mock.module('@/components/ui/button', () => ({ Button: 'Button' }))
mock.module('@/components/ui/badge', () => ({ Badge: 'Badge' }))
mock.module('@/components/ui/dropdown-menu', () => ({
  DropdownMenu: 'DropdownMenu', DropdownMenuContent: 'DropdownMenuContent',
  DropdownMenuItem: 'DropdownMenuItem', DropdownMenuTrigger: 'DropdownMenuTrigger',
}))
mock.module('@/components/ui/tooltip', () => ({
  Tooltip: 'Tooltip', TooltipContent: 'TooltipContent', TooltipTrigger: 'TooltipTrigger',
}))

const { AgentToolbar } = await import('./agent-toolbar')

type ElementNode = { type?: unknown; props?: Record<string, unknown> }

function findAll(node: unknown, predicate: (element: ElementNode) => boolean): ElementNode[] {
  if (Array.isArray(node)) return node.flatMap((child) => findAll(child, predicate))
  if (!node || typeof node !== 'object') return []
  const element = node as ElementNode
  return [
    ...(predicate(element) ? [element] : []),
    ...findAll(element.props?.children, predicate),
  ]
}

const agent = { id: 'agent-1', status: 'draft', model: null } as never

function render(overrides: Record<string, unknown> = {}) {
  const callbacks = {
    onPublish: mock(() => undefined), onSave: mock(() => undefined),
    onPreviewClick: mock(() => undefined), onSettingsClick: mock(() => undefined),
    onEmbedClick: mock(() => undefined), onToggleSidebar: mock(() => undefined),
  }
  const tree = AgentToolbar({
    agent, isSaving: false, sidebarCollapsed: false, ...callbacks, ...overrides,
  })
  return { tree, ...callbacks }
}

const byTestId = (tree: unknown, id: string) =>
  findAll(tree, (element) => element.props?.['data-testid'] === id)

const text = (node: unknown): string => Array.isArray(node)
  ? node.map(text).join('')
  : node && typeof node === 'object'
    ? text((node as ElementNode).props?.children)
    : typeof node === 'string' ? node : ''

describe('AgentToolbar', () => {
  test('shows chat but hides mutation controls without permissions', () => {
    const { tree } = render()
    const mobileChatItem = byTestId(tree, 'agent-mobile-chat-link')[0]

    expect(mobileChatItem.props?.render).toMatchObject({ props: { href: '/chat/agent-1', target: '_blank' } })
    expect(byTestId(tree, 'agent-chat-button')).toHaveLength(1)
    expect(byTestId(tree, 'agent-embed-button')).toHaveLength(0)
    expect(byTestId(tree, 'agent-settings-button')).toHaveLength(0)
    expect(byTestId(tree, 'agent-save-button')).toHaveLength(0)
    expect(byTestId(tree, 'agent-mobile-preview-button')).toHaveLength(1)
    expect(byTestId(tree, 'agent-mobile-chat-link')).toHaveLength(1)
    expect(byTestId(tree, 'agent-publish-button')).toHaveLength(0)
  })

  test('exposes authorized actions and reflects saving and published state', () => {
    const current = render({
      agent: { id: 'agent-1', status: 'published', model: { name: 'Sonnet' } },
      canUpdate: true, canPublish: true, isSaving: true, sidebarCollapsed: true,
    })

    expect(text(current.tree)).toContain('Sonnet')
    expect(text(byTestId(current.tree, 'agent-save-button')[0])).toContain('toolbar.saving')
    expect(text(byTestId(current.tree, 'agent-publish-button')[0])).toContain('toolbar.published')
    expect(text(byTestId(current.tree, 'agent-publish-confirm')[0])).toContain('toolbar.confirmUnpublish')

    ;(byTestId(current.tree, 'agent-embed-button')[0].props?.onClick as () => void)()
    ;(byTestId(current.tree, 'agent-settings-button')[0].props?.onClick as () => void)()
    ;(byTestId(current.tree, 'agent-save-button')[0].props?.onClick as () => void)()
    ;(byTestId(current.tree, 'agent-mobile-preview-button')[0].props?.onClick as () => void)()
    ;(byTestId(current.tree, 'agent-mobile-embed-action')[0].props?.onClick as () => void)()
    ;(byTestId(current.tree, 'agent-mobile-settings-action')[0].props?.onClick as () => void)()
    ;(byTestId(current.tree, 'agent-mobile-save-action')[0].props?.onClick as () => void)()
    ;(byTestId(current.tree, 'agent-publish-confirm')[0].props?.onClick as () => void)()
    const trigger = findAll(current.tree, (element) => element.type === 'TooltipTrigger')[0]
    const sidebarButton = (trigger.props?.render as (props: object) => ElementNode)({})
    ;(sidebarButton.props?.onClick as () => void)()

    expect(current.onEmbedClick).toHaveBeenCalledTimes(2)
    expect(current.onSettingsClick).toHaveBeenCalledTimes(2)
    expect(current.onSave).toHaveBeenCalledTimes(2)
    expect(current.onToggleSidebar).toHaveBeenCalledTimes(1)
    expect(current.onPreviewClick).toHaveBeenCalledTimes(1)
  })
})
