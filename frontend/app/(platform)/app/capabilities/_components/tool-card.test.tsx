import { expect, mock, test } from 'bun:test'
import { isValidElement, type ReactElement, type ReactNode } from 'react'
import type { Tool } from '@/lib/api'

mock.module('next-intl', () => ({
  useTranslations: (namespace: string) =>
    (key: string, values?: Record<string, string>) =>
      `${namespace}.${key}${values?.teamName ? `:${values.teamName}` : ''}`,
}))

const { ToolCard } = await import('./tool-card')

type ElementProps = {
  children?: ReactNode
  disabled?: boolean
  onClick?: (event: { stopPropagation: () => void }) => void
}

function elements(node: ReactNode): ReactElement<ElementProps>[] {
  if (Array.isArray(node)) return node.flatMap(elements)
  if (!isValidElement<ElementProps>(node)) return []
  return [node, ...elements(node.props.children)]
}

const baseTool: Tool = {
  id: 'tool-1',
  name: 'weather',
  display_name: 'Weather',
  description: 'Current conditions',
  type: 'custom',
  category: 'web',
  parameters: [],
  is_enabled: true,
  requires_config: false,
  config_fields: [],
}

test('routes owned custom-tool actions without selecting the card', () => {
  const calls: string[] = []
  const tree = ToolCard({
    tool: baseTool,
    onSelect: () => calls.push('select'),
    onTest: () => calls.push('test'),
    onEdit: () => calls.push('edit'),
    onShare: () => calls.push('share'),
    onDelete: () => calls.push('delete'),
    canEdit: true,
    canShare: true,
    canDelete: true,
  })
  const clickable = elements(tree).filter((element) => element.props.onClick)
  let stopped = 0

  clickable[0].props.onClick?.({ stopPropagation: () => stopped++ })
  for (const element of clickable.slice(1)) {
    element.props.onClick?.({ stopPropagation: () => stopped++ })
  }

  expect(calls).toEqual(['select', 'test', 'edit', 'share', 'delete'])
  expect(stopped).toBe(4)
})

test('shows sharing context and withholds owner actions for a shared tool', () => {
  const restrictedCalls: string[] = []
  const tree = ToolCard({
    tool: {
      ...baseTool,
      is_owned: false,
      owner_team_name: 'Platform Team',
    },
    onEdit: () => restrictedCalls.push('edit'),
    onShare: () => restrictedCalls.push('share'),
    onDelete: () => restrictedCalls.push('delete'),
    canEdit: true,
    canShare: true,
    canDelete: true,
  })
  const nodes = elements(tree)
  const text = nodes.flatMap((element) => element.props.children).filter((child) => typeof child === 'string')

  for (const element of nodes.filter((node) => node.props.onClick)) {
    element.props.onClick?.({ stopPropagation() {} })
  }

  expect(text).toContain('platform.tools.share.sharedBadge')
  expect(text).toContain('platform.tools.share.sharedFrom:Platform Team')
  expect(nodes.some((element) => element.props.disabled)).toBe(true)
  expect(restrictedCalls).toEqual([])
})
