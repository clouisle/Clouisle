import React from 'react'
import { afterEach, describe, expect, mock, test } from 'bun:test'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'

const list = mock(async () => ({ items: [], total: 0, page: 1, page_size: 20 }))
const respond = mock(async () => ({ id: 'interaction-1', outcome: 'accept' }))
const toastSuccess = mock(() => undefined)

mock.module('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}))
mock.module('sonner', () => ({ toast: { success: toastSuccess, error: mock(() => undefined) } }))
mock.module('lucide-react', () => ({
  Loader2: () => <span data-icon="loader" />,
  RefreshCw: () => <span data-icon="refresh" />,
  ServerCog: () => <span data-icon="server" />,
}))
mock.module('@/components/ui/card', () => ({
  Card: ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) => <div {...props}>{children}</div>,
  CardContent: ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) => <div {...props}>{children}</div>,
}))
mock.module('@/components/ui/button', () => ({
  Button: ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) => <button {...props}>{children}</button>,
}))
mock.module('@/components/tool-interactions', () => ({
  InteractionRequestCard: ({
    interaction,
    onRespond,
  }: {
    interaction: { id: string }
    onRespond: (id: string, input: Record<string, unknown>) => Promise<unknown>
  }) => (
    <div data-testid={`stub-${interaction.id}`}>
      <button onClick={() => void onRespond(interaction.id, {
        action: 'accept',
        content: null,
        idempotency_key: 'stub-key',
      })}>
        accept
      </button>
    </div>
  ),
}))
mock.module('@/lib/api', () => ({
  runInteractionsApi: { list, respond },
}))

const { InteractionsInbox } = await import('./interactions-inbox')

globalThis.IS_REACT_ACT_ENVIRONMENT = true

const renderers: ReactTestRenderer[] = []

afterEach(() => {
  for (const renderer of renderers) act(() => renderer.unmount())
  renderers.length = 0
})

const interaction = {
  id: 'interaction-1',
  kind: 'sampling',
  status: 'pending',
  run_kind: 'agent',
  run_id: 'run-1',
  payload: { mode: 'sampling', system_prompt: null, messages: [], max_tokens: 12, model_preferences: null },
  created_at: '2026-10-26T00:00:00Z',
}

function textOfChildren(children: React.ReactNode): string {
  if (typeof children === 'string' || typeof children === 'number') return String(children)
  if (Array.isArray(children)) return children.map(textOfChildren).join('')
  if (React.isValidElement<{ children?: React.ReactNode }>(children)) {
    return textOfChildren(children.props.children)
  }
  return ''
}

async function flush() {
  await act(async () => {
    await Promise.resolve()
    await Promise.resolve()
  })
}

describe('InteractionsInbox', () => {
  test('lists durable pending interactions and refreshes after a response', async () => {
    list.mockClear()
    respond.mockClear()
    list.mockResolvedValue({ items: [interaction], total: 1, page: 1, page_size: 20 })
    let renderer!: ReactTestRenderer
    act(() => {
      renderer = create(<InteractionsInbox />)
    })
    renderers.push(renderer)
    await flush()

    expect(list).toHaveBeenCalledWith({ page: 1, page_size: 20, status: 'pending' })
    const accept = renderer.root.findAllByType('button').find((button) => textOfChildren(button.props.children) === 'accept')
    act(() => accept?.props.onClick())
    await flush()

    expect(respond).toHaveBeenCalledWith('interaction-1', {
      action: 'accept',
      content: null,
      idempotency_key: 'stub-key',
    })
    expect(list).toHaveBeenCalledTimes(2)
    expect(toastSuccess).toHaveBeenCalledWith('acceptedToast')
  })

  test('paginates when more pending requests exist', async () => {
    list.mockClear()
    list.mockResolvedValue({ items: [interaction], total: 45, page: 1, page_size: 20 })
    let renderer!: ReactTestRenderer
    act(() => {
      renderer = create(<InteractionsInbox />)
    })
    renderers.push(renderer)
    await flush()

    const next = renderer.root.findAllByType('button').find((button) => textOfChildren(button.props.children).includes('next'))
    act(() => next?.props.onClick())
    await flush()
    expect(list).toHaveBeenLastCalledWith({ page: 2, page_size: 20, status: 'pending' })
  })
})
