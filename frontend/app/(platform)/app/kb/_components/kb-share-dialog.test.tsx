import React from 'react'
import { afterEach, beforeEach, describe, expect, mock, test } from 'bun:test'
import { renderToString } from 'react-dom/server'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'

const knowledgeBasesApi = {
  listKnowledgeBaseShares: mock(async () => ({ shares: [], total: 0 })),
  shareKnowledgeBase: mock(async () => ({})),
  unshareKnowledgeBase: mock(async () => undefined),
}

mock.module('next-intl', () => ({
  useTranslations: () => Object.assign(
    (key: string, values?: Record<string, unknown>) => `${key}${values ? `:${Object.values(values).join(',')}` : ''}`,
    { has: () => true }
  ),
}))

mock.module('sonner', () => ({ toast: { success: mock(), error: mock() } }))
mock.module('@/lib/api', () => ({ knowledgeBasesApi }))
mock.module('@/lib/api/knowledge-bases', () => ({ knowledgeBasesApi }))

const passthrough = (tag: keyof React.JSX.IntrinsicElements = 'div') => {
  const Component = ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) =>
    React.createElement(tag, props, children)
  return Component
}

mock.module('@/components/ui/dialog', () => ({
  Dialog: ({ open, children }: React.PropsWithChildren<{ open?: boolean }>) => open ? <div>{children}</div> : null,
  DialogContent: passthrough(),
  DialogDescription: passthrough('p'),
  DialogFooter: passthrough(),
  DialogHeader: passthrough(),
  DialogTitle: passthrough('h2'),
}))
mock.module('@/components/ui/alert-dialog', () => ({
  AlertDialog: ({ open, children }: React.PropsWithChildren<{ open?: boolean }>) => open ? <div>{children}</div> : null,
  AlertDialogAction: passthrough('button'),
  AlertDialogCancel: passthrough('button'),
  AlertDialogContent: passthrough(),
  AlertDialogDescription: passthrough('p'),
  AlertDialogFooter: passthrough(),
  AlertDialogHeader: passthrough(),
  AlertDialogTitle: passthrough('h2'),
}))
mock.module('@/components/ui/button', () => ({ Button: passthrough('button') }))
mock.module('@/components/ui/label', () => ({ Label: passthrough('label') }))
mock.module('@/components/ui/field', () => ({ FieldError: passthrough('p') }))
mock.module('@/components/ui/select', () => ({
  Select: passthrough(),
  SelectContent: passthrough(),
  SelectItem: passthrough(),
  SelectTrigger: passthrough(),
  SelectValue: passthrough('span'),
}))
mock.module('@/components/ui/scroll-area', () => ({
  ScrollArea: passthrough(),
}))

import { KnowledgeBaseShareDialog } from './kb-share-dialog'

const baseKb = {
  id: 'kb-1',
  name: 'Product Manual',
  description: 'Internal documentation',
  icon: 'book',
  team: { id: 'team-1', name: 'Core Team' },
  created_by: { id: 'user-1', username: 'Ada' },
  status: 'active',
  document_count: 5,
  total_chunks: 25,
  total_tokens: 12000,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-02T00:00:00Z',
}

const nodeText = (node: { children: unknown[] }): string =>
  node.children
    .map((child) => (typeof child === 'string' ? child : typeof child === 'object' && child && 'children' in child ? nodeText(child as { children: unknown[] }) : ''))
    .join('')

const click = async (node: { props: { onClick?: (e: unknown) => unknown } }) => {
  await act(async () => {
    node.props.onClick?.({ defaultPrevented: false, preventDefault: () => undefined })
  })
}

describe('KnowledgeBaseShareDialog', () => {
  const renderers: ReactTestRenderer[] = []

  beforeEach(() => {
    knowledgeBasesApi.listKnowledgeBaseShares.mockReset()
    knowledgeBasesApi.shareKnowledgeBase.mockReset()
    knowledgeBasesApi.unshareKnowledgeBase.mockReset()
    knowledgeBasesApi.listKnowledgeBaseShares.mockResolvedValue({ shares: [], total: 0 })
    knowledgeBasesApi.shareKnowledgeBase.mockResolvedValue({} as never)
    knowledgeBasesApi.unshareKnowledgeBase.mockResolvedValue(undefined)
  })

  afterEach(() => {
    while (renderers.length > 0) {
      renderers.pop()?.unmount()
    }
  })

  test('returns null when knowledgeBase is null', () => {
    const html = renderToString(
      <KnowledgeBaseShareDialog
        knowledgeBase={null}
        open
        onOpenChange={() => undefined}
        currentTeamId="team-1"
        availableTeams={[]}
      />
    )
    expect(html).toBe('')
  })

  test('renders share dialog and filters current team', () => {
    const html = renderToString(
      <KnowledgeBaseShareDialog
        knowledgeBase={baseKb as never}
        open
        onOpenChange={() => undefined}
        currentTeamId="team-1"
        availableTeams={[
          { id: 'team-1', name: 'Core Team', role: 'owner' },
          { id: 'team-2', name: 'Engineering', role: 'member' },
        ] as never}
      />
    )

    expect(html).toContain('title')
    expect(html).toContain('Engineering')
    expect(html).not.toContain('Core Team')
  })

  test('renders empty state when no other teams are available', () => {
    const html = renderToString(
      <KnowledgeBaseShareDialog
        knowledgeBase={baseKb as never}
        open
        onOpenChange={() => undefined}
        currentTeamId="team-1"
        availableTeams={[
          { id: 'team-1', name: 'Core Team', role: 'owner' },
        ] as never}
      />
    )

    expect(html).toContain('noAvailableTeams')
  })

  test('validates, shares, and unshares knowledge bases', async () => {
    const share = {
      id: 'share-1',
      knowledge_base_id: 'kb-1',
      knowledge_base_name: 'Product Manual',
      shared_with_team_id: 'team-2',
      shared_with_team_name: 'Engineering',
      permission: 'read_only' as const,
      shared_by_name: 'Ada',
      shared_at: '2026-01-01T00:00:00Z',
    }
    knowledgeBasesApi.listKnowledgeBaseShares.mockResolvedValue({ shares: [share], total: 1 })
    knowledgeBasesApi.shareKnowledgeBase.mockResolvedValue(share)
    knowledgeBasesApi.unshareKnowledgeBase.mockResolvedValue(undefined)
    const onSuccess = mock(() => undefined)

    let renderer: ReactTestRenderer
    await act(async () => {
      renderer = create(
        <KnowledgeBaseShareDialog
          knowledgeBase={baseKb as never}
          open
          onOpenChange={() => undefined}
          currentTeamId="team-1"
          availableTeams={[
            { id: 'team-1', name: 'Core Team', role: 'owner' },
            { id: 'team-2', name: 'Engineering', role: 'member' },
            { id: 'team-3', name: 'Support', role: 'member' },
          ] as never}
          onSuccess={onSuccess}
        />
      )
    })
    renderers.push(renderer!)

    await act(async () => Promise.resolve())

    const shareButton = () => renderer!.root.findAllByType('button').find((button) => nodeText(button).includes('shareButton'))!
    await click(shareButton())
    expect(renderer!.root.findAllByType('p').map((node) => node.children.join(''))).toContain('selectTeam')

    const teamSelect = renderer!.root.findAll((node) => node.props.onValueChange)[0]
    await act(async () => teamSelect.props.onValueChange('team-3'))
    await click(shareButton())

    expect(knowledgeBasesApi.shareKnowledgeBase).toHaveBeenCalledWith('kb-1', {
      team_id: 'team-3',
      permission: 'read_only',
    })
    expect(onSuccess).toHaveBeenCalled()
    // Find delete button to unshare
    const deleteButton = renderer!.root.findAllByType('button').find((button) =>
      button.props.className?.includes('text-destructive')
    )
    expect(deleteButton).toBeDefined()
    await click(deleteButton!)

    // Confirm unshare
    const confirmButton = renderer!.root.findAllByType('button').find((button) => nodeText(button).includes('unshareButton'))!
    await click(confirmButton)

    expect(knowledgeBasesApi.unshareKnowledgeBase).toHaveBeenCalledWith('kb-1', 'team-2')
  })
})
