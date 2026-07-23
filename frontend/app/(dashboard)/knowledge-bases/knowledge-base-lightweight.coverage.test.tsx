import { afterEach, describe, expect, mock, test } from 'bun:test'
import React, { type ComponentProps, type ReactNode } from 'react'
import { act, create, type ReactTestRenderer } from 'react-test-renderer'

import type { KnowledgeBase } from '@/lib/api'

globalThis.IS_REACT_ACT_ENVIRONMENT = true

const deleteKnowledgeBase = mock(async (id: string) => { void id })
const toastSuccess = mock((message: string) => { void message })

mock.module('@/lib/api', () => ({
  adminKnowledgeBasesApi: { deleteKnowledgeBase },
}))

mock.module('sonner', () => ({
  toast: { success: toastSuccess },
}))

mock.module('next-intl', () => ({
  useTranslations: (namespace: string) => (key: string, values?: { name?: string }) => {
    const messages: Record<string, string> = {
      'knowledgeBases.confirmDelete': 'Delete knowledge base?',
      'knowledgeBases.deleteKbConfirm': `Delete ${values?.name ?? ''} permanently?`,
      'knowledgeBases.kbDeleted': 'Knowledge base deleted',
      'common.cancel': 'Cancel',
      'common.delete': 'Delete',
    }
    return messages[`${namespace}.${key}`] ?? key
  },
}))

function AlertDialog({ children, open }: { children: ReactNode; open?: boolean }) {
  return open ? <div role="alertdialog">{children}</div> : null
}

mock.module('@/components/ui/alert-dialog', () => ({
  AlertDialog,
  AlertDialogAction: (props: ComponentProps<'button'>) => <button {...props} />,
  AlertDialogCancel: (props: ComponentProps<'button'>) => <button {...props} />,
  AlertDialogContent: ({ children }: { children: ReactNode }) => <section>{children}</section>,
  AlertDialogDescription: ({ children }: { children: ReactNode }) => <p>{children}</p>,
  AlertDialogFooter: ({ children }: { children: ReactNode }) => <footer>{children}</footer>,
  AlertDialogHeader: ({ children }: { children: ReactNode }) => <header>{children}</header>,
  AlertDialogTitle: ({ children }: { children: ReactNode }) => <h2>{children}</h2>,
}))

mock.module('@/components/layout/header', () => ({
  Header: () => <header data-testid="dashboard-header" />,
}))

mock.module('./_components', () => ({
  KnowledgeBasesClient: () => <main data-testid="knowledge-bases-client" />,
}))

mock.module('./[id]/search/_components/search-test-client', () => ({
  SearchTestClient: ({ knowledgeBaseId }: { knowledgeBaseId: string }) => (
    <main data-knowledge-base-id={knowledgeBaseId} />
  ),
}))

const { DeleteKnowledgeBaseDialog } = await import('./_components/delete-knowledge-base-dialog')
const { default: KnowledgeBasesPage } = await import('./page')
const { default: SearchTestPage } = await import('./[id]/search/page')

const renderers: ReactTestRenderer[] = []

function renderDialog(knowledgeBase: KnowledgeBase | null = { id: 'kb-42', name: 'Runbooks' } as KnowledgeBase) {
  const onOpenChange = mock((open: boolean) => { void open })
  const onSuccess = mock(() => {})
  let renderer!: ReactTestRenderer

  act(() => {
    renderer = create(
      <DeleteKnowledgeBaseDialog
        open
        onOpenChange={onOpenChange}
        knowledgeBase={knowledgeBase}
        onSuccess={onSuccess}
      />,
    )
  })
  renderers.push(renderer)
  return { renderer, onOpenChange, onSuccess }
}

afterEach(() => {
  for (const renderer of renderers) act(() => renderer.unmount())
  renderers.length = 0
  deleteKnowledgeBase.mockClear()
  deleteKnowledgeBase.mockImplementation(async () => {})
  toastSuccess.mockClear()
})

describe('lightweight knowledge-base UI', () => {
  test('presents a named destructive confirmation with semantic actions', () => {
    const { renderer } = renderDialog()

    expect(renderer.root.findByProps({ role: 'alertdialog' })).toBeDefined()
    expect(renderer.root.findByType('h2').children).toEqual(['Delete knowledge base?'])
    expect(renderer.root.findByType('p').children).toEqual(['Delete Runbooks permanently?'])
    expect(renderer.root.findAllByType('button').map((button) => button.children[0])).toEqual(['Cancel', 'Delete'])
  })

  test('deletes the selected knowledge base then closes and refreshes', async () => {
    const { renderer, onOpenChange, onSuccess } = renderDialog()

    await act(async () => renderer.root.findAllByType('button')[1].props.onClick())

    expect(deleteKnowledgeBase).toHaveBeenCalledWith('kb-42')
    expect(toastSuccess).toHaveBeenCalledWith('Knowledge base deleted')
    expect(onOpenChange).toHaveBeenCalledWith(false)
    expect(onSuccess).toHaveBeenCalledTimes(1)
  })

  test('leaves the dialog unchanged when deletion fails', async () => {
    deleteKnowledgeBase.mockImplementationOnce(async () => { throw new Error('delete failed') })
    const { renderer, onOpenChange, onSuccess } = renderDialog()

    await act(async () => renderer.root.findAllByType('button')[1].props.onClick())

    expect(toastSuccess).not.toHaveBeenCalled()
    expect(onOpenChange).not.toHaveBeenCalled()
    expect(onSuccess).not.toHaveBeenCalled()
  })

  test('does nothing when no knowledge base is selected', async () => {
    const { renderer, onOpenChange, onSuccess } = renderDialog(null)

    expect(renderer.root.findByType('p').children).toEqual(['Delete  permanently?'])
    await act(async () => renderer.root.findAllByType('button')[1].props.onClick())

    expect(deleteKnowledgeBase).not.toHaveBeenCalled()
    expect(onOpenChange).not.toHaveBeenCalled()
    expect(onSuccess).not.toHaveBeenCalled()
  })

  test('composes the list page from its header and client', () => {
    let renderer!: ReactTestRenderer
    act(() => { renderer = create(<KnowledgeBasesPage />) })
    renderers.push(renderer)

    expect(renderer.root.findByProps({ 'data-testid': 'dashboard-header' })).toBeDefined()
    expect(renderer.root.findByProps({ 'data-testid': 'knowledge-bases-client' })).toBeDefined()
  })

  test('forwards the resolved route id to the search client', async () => {
    const page = await SearchTestPage({ params: Promise.resolve({ id: 'kb-search' }) })
    let renderer!: ReactTestRenderer
    act(() => { renderer = create(page) })
    renderers.push(renderer)

    expect(renderer.root.findByProps({ 'data-knowledge-base-id': 'kb-search' })).toBeDefined()
  })
})
