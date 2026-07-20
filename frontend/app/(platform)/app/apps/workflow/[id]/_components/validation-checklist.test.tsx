import { describe, expect, mock, test } from 'bun:test'
import type { ReactNode } from 'react'
import type { ValidationIssue } from './workflow-validator'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx }))
mock.module('react', () => ({ useMemo: <T,>(factory: () => T) => factory() }))
mock.module('next-intl', () => ({
  useTranslations: () => (key: string, params?: Record<string, unknown>) =>
    params ? `${key}:${JSON.stringify(params)}` : key,
}))
mock.module('@/lib/utils', () => ({
  cn: (...classes: Array<string | false | undefined>) => classes.filter(Boolean).join(' '),
}))
mock.module('./workflow-validator', () => ({
  getNodeTypeColor: (nodeType: string) => `color-${nodeType}`,
}))

const icon = (name: string) => (props: Record<string, unknown>) => jsx('svg', { ...props, name })
mock.module('lucide-react', () => ({
  AlertTriangle: icon('AlertTriangle'),
  Bot: icon('Bot'),
  ChevronRight: icon('ChevronRight'),
  Code2: icon('Code2'),
  FileInput: icon('FileInput'),
  FileText: icon('FileText'),
  GitBranch: icon('GitBranch'),
  GitFork: icon('GitFork'),
  LayoutList: icon('LayoutList'),
  ListFilter: icon('ListFilter'),
  MessageSquareText: icon('MessageSquareText'),
  Repeat: icon('Repeat'),
  RotateCcw: icon('RotateCcw'),
  Tags: icon('Tags'),
  Variable: icon('Variable'),
  Wrench: icon('Wrench'),
  X: icon('X'),
  XCircle: icon('XCircle'),
  Zap: icon('Zap'),
}))

const { ValidationChecklist } = await import('./validation-checklist')

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
  if (!resolved || typeof resolved !== 'object' || !('type' in resolved)) return []
  const tree = resolved as Tree
  const children = tree.props.children
  return [
    ...(predicate(tree) ? [tree] : []),
    ...(Array.isArray(children) ? children : [children]).flatMap((child) =>
      findAll(child as ReactNode, predicate)
    ),
  ]
}

function text(node: ReactNode): string {
  const resolved = resolve(node)
  if (typeof resolved === 'string' || typeof resolved === 'number') return String(resolved)
  if (!resolved || typeof resolved !== 'object' || !('type' in resolved)) return ''
  const children = (resolved as Tree).props.children
  return (Array.isArray(children) ? children : [children]).map((child) => text(child as ReactNode)).join('')
}

function issue(overrides: Partial<ValidationIssue>): ValidationIssue {
  return {
    id: 'issue-1',
    nodeId: 'node-1',
    nodeLabel: 'LLM step',
    nodeLabelKey: 'nodeLabels.llm',
    nodeType: 'llm',
    severity: 'error',
    message: 'modelNotSelected',
    messageKey: 'validation.modelNotSelected',
    ...overrides,
  }
}

describe('ValidationChecklist', () => {
  test('renders the publishable empty state and closes from the header', () => {
    const onClose = mock()
    const tree = ValidationChecklist({ issues: [], onClose, onSelectNode: mock() })

    expect(text(tree)).toContain('checklist.title(0)')
    expect(text(tree)).toContain('checklist.description')
    expect(text(tree)).toContain('checklist.allPassed')
    expect(text(tree)).toContain('checklist.readyToPublish')
    expect(text(tree)).not.toContain('checklist.errorCount')

    const [closeButton] = findAll(tree, (element) => element.type === 'button')
    ;(closeButton.props.onClick as () => void)()
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  test('groups issues, reports severity totals, and only selects node-level groups', () => {
    const onSelectNode = mock()
    const issues = [
      issue({ id: 'error-1' }),
      issue({
        id: 'warning-1',
        severity: 'warning',
        messageKey: 'validation.suggestPrompt',
        messageParams: { name: 'prompt' },
      }),
      issue({
        id: 'workflow-error',
        nodeId: 'workflow',
        nodeLabel: 'workflow',
        nodeLabelKey: 'validation.workflow',
        nodeType: 'workflow',
        messageKey: 'validation.disconnectedNode',
      }),
    ]
    const tree = ValidationChecklist({ issues, onClose: mock(), onSelectNode })

    expect(text(tree)).toContain('checklist.title(3)')
    expect(text(tree)).toContain('LLM step')
    expect(text(tree)).toContain('validation.workflow')
    expect(text(tree)).toContain('validation.modelNotSelected')
    expect(text(tree)).toContain('validation.suggestPrompt:{"name":"prompt"}')
    expect(text(tree)).toContain('checklist.errorCount:{"count":2}')
    expect(text(tree)).toContain('checklist.warningCount:{"count":1}')

    const groupButtons = findAll(tree, (element) =>
      element.type === 'button' && text(element).length > 0
    )
    expect(groupButtons).toHaveLength(2)

    ;(groupButtons[0].props.onClick as () => void)()
    ;(groupButtons[1].props.onClick as () => void)()
    expect(onSelectNode).toHaveBeenCalledTimes(1)
    expect(onSelectNode).toHaveBeenCalledWith('node-1')
    expect(groupButtons[0].props.className).toContain('cursor-pointer')
    expect(groupButtons[1].props.className).not.toContain('cursor-pointer')
  })
})
