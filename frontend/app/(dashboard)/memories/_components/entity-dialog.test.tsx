import { afterEach, beforeAll, describe, expect, mock, spyOn, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'

const canPerform = mock(() => true)

mock.module('next-intl', () => ({
  useTranslations: () => Object.assign((key: string) => key, { has: () => true }),
}))

mock.module('sonner', () => ({ toast: { success: mock(() => {}) } }))
mock.module('@/components/permission-guard', () => ({ useCanPerform: () => ({ canPerform }) }))

mock.module('@/components/ui/button', () => ({
  Button: ({ children, ...props }: React.ComponentProps<'button'>) => <button {...props}>{children}</button>,
}))
mock.module('@/components/ui/textarea', () => ({
  Textarea: (props: React.ComponentProps<'textarea'>) => <textarea {...props} />,
}))
mock.module('@/components/ui/label', () => ({ Label: ({ children }: { children: React.ReactNode }) => <label>{children}</label> }))
mock.module('@/components/ui/badge', () => ({ Badge: ({ children }: { children: React.ReactNode }) => <span>{children}</span> }))
mock.module('@/components/ui/avatar', () => ({
  Avatar: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AvatarImage: () => null,
  AvatarFallback: ({ children }: { children: React.ReactNode }) => <span>{children}</span>,
}))
mock.module('@/components/ui/separator', () => ({ Separator: () => <hr /> }))
mock.module('@/components/ui/field', () => ({ FieldError: ({ children }: { children?: React.ReactNode }) => <p>{children}</p> }))
mock.module('@/components/ui/dialog', () => ({
  Dialog: ({ children }: { children: React.ReactNode }) => <section role="dialog">{children}</section>,
  DialogContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogDescription: ({ children }: { children: React.ReactNode }) => <p>{children}</p>,
  DialogFooter: ({ children }: { children: React.ReactNode }) => <footer>{children}</footer>,
  DialogHeader: ({ children }: { children: React.ReactNode }) => <header>{children}</header>,
  DialogTitle: ({ children }: { children: React.ReactNode }) => <h2>{children}</h2>,
}))
mock.module('@/components/ui/alert-dialog', () => ({
  AlertDialog: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogAction: ({ children, onClick }: { children: React.ReactNode; onClick?: () => void }) => <button onClick={onClick}>{children}</button>,
  AlertDialogCancel: ({ children }: { children: React.ReactNode }) => <button>{children}</button>,
  AlertDialogContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogDescription: ({ children }: { children: React.ReactNode }) => <p>{children}</p>,
  AlertDialogFooter: ({ children }: { children: React.ReactNode }) => <footer>{children}</footer>,
  AlertDialogHeader: ({ children }: { children: React.ReactNode }) => <header>{children}</header>,
  AlertDialogTitle: ({ children }: { children: React.ReactNode }) => <h3>{children}</h3>,
}))

let EntityDialog: typeof import('./entity-dialog').EntityDialog
let memoriesApi: typeof import('@/lib/api/admin/memories').memoriesApi

beforeAll(async () => {
  ;({ EntityDialog } = await import('./entity-dialog'))
  ;({ memoriesApi } = await import('@/lib/api/admin/memories'))
})

globalThis.IS_REACT_ACT_ENVIRONMENT = true

const entity = {
  id: 'entity-1', user_id: 'user-1', user_name: 'Ada Lovelace', user_avatar_url: null,
  name: 'Prefers tests', entity_type: 'preference', description: 'Old description', properties: { color: 'blue' },
  access_count: 2, last_accessed_at: null, created_at: '2026-01-01', updated_at: '2026-01-02',
  outgoing_relations: [{ id: 'relation-1', user_id: 'user-1', source_entity_id: 'entity-1', source_entity_name: 'Prefers tests', target_entity_id: 'entity-2', target_entity_name: 'Bun', relation_type: 'uses', description: 'Fast tests', properties: {}, created_at: '2026-01-01' }],
  incoming_relations: [],
}

const renderers: ReactTestRenderer[] = []
afterEach(() => {
  for (const renderer of renderers) act(() => renderer.unmount())
  renderers.length = 0
  mock.restore()
  canPerform.mockReset()
  canPerform.mockReturnValue(true)
})

async function render(onSuccess = mock(() => {})) {
  spyOn(memoriesApi, 'getEntity').mockResolvedValue(entity)
  let renderer: ReactTestRenderer
  await act(async () => {
    renderer = create(<EntityDialog entity={entity} open onOpenChange={mock(() => {})} onSuccess={onSuccess} />)
    await Promise.resolve()
  })
  renderers.push(renderer!)
  return renderer!
}

describe('EntityDialog', () => {
  test('shows editable entity details and saves the changed API payload', async () => {
    const update = spyOn(memoriesApi, 'updateEntity').mockResolvedValue(entity)
    const onSuccess = mock(() => {})
    const renderer = await render(onSuccess)

    expect(JSON.stringify(renderer.toJSON())).toContain('Ada Lovelace')
    expect(JSON.stringify(renderer.toJSON())).toContain('Bun')
    expect(renderer.root.findAllByType('textarea')).toHaveLength(2)

    act(() => renderer.root.findAllByType('textarea')[0].props.onChange({ target: { value: 'New description' } }))
    await act(async () => renderer.root.findByType('form').props.onSubmit({ preventDefault: mock(() => {}) }))

    expect(update).toHaveBeenCalledWith('entity-1', { description: 'New description', properties: { color: 'blue' } })
    expect(onSuccess).toHaveBeenCalled()
  })

  test('rejects invalid JSON without submitting and hides relation deletion when read-only', async () => {
    canPerform.mockReturnValue(false)
    const update = spyOn(memoriesApi, 'updateEntity').mockResolvedValue(entity)
    const renderer = await render()

    act(() => renderer.root.findAllByType('textarea')[1].props.onChange({ target: { value: '{bad' } }))
    await act(async () => renderer.root.findByType('form').props.onSubmit({ preventDefault: mock(() => {}) }))

    expect(update).not.toHaveBeenCalled()
    expect(JSON.stringify(renderer.toJSON())).toContain('invalidJSON')
    expect(renderer.root.findAllByType('button')).toHaveLength(4)
  })
})
