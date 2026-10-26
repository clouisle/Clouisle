import React from 'react'
import { afterEach, describe, expect, mock, test } from 'bun:test'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'

const getExecution = mock(async () => ({
  id: 'execution-1',
  status: 'awaiting_approval',
  operation: 'delete_event',
  connection_account_label: 'work@example.com',
  parameters_preview: { event_id: 'evt-1', token: '***REDACTED***' },
}))

mock.module('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}))
mock.module('next/link', () => ({
  default: ({ href, children }: React.PropsWithChildren<{ href: string }>) => <a href={href}>{children}</a>,
}))
mock.module('lucide-react', () => ({
  Loader2: () => <span data-icon="loader" />,
  RefreshCw: () => <span data-icon="refresh" />,
  ShieldCheck: () => <span data-icon="shield" />,
}))
mock.module('@/lib/utils', () => ({
  cn: (...values: unknown[]) => values.filter(Boolean).join(' '),
}))
mock.module('@/components/ui/card', () => ({
  Card: ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) => <div {...props}>{children}</div>,
  CardContent: ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) => <div {...props}>{children}</div>,
}))
mock.module('@/components/ui/badge', () => ({
  Badge: ({ children }: React.PropsWithChildren) => <span data-badge>{children}</span>,
}))
mock.module('@/components/ui/button', () => ({
  Button: ({ children, render, ...props }: React.PropsWithChildren<Record<string, unknown>>) => {
    if (render && React.isValidElement(render)) return React.cloneElement(render, props, children)
    return <button {...props}>{children}</button>
  },
}))
mock.module('@/lib/api', () => ({
  toolExecutionsApi: { get: getExecution },
}))

const { PendingToolApprovalCard } = await import('./pending-tool-approval-card')

globalThis.IS_REACT_ACT_ENVIRONMENT = true

const renderers: ReactTestRenderer[] = []

afterEach(() => {
  for (const renderer of renderers) act(() => renderer.unmount())
  renderers.length = 0
})

async function flush() {
  await act(async () => {
    await Promise.resolve()
    await Promise.resolve()
  })
}

describe('PendingToolApprovalCard', () => {
  test('reads secret-safe execution metadata and links to the approvals inbox', async () => {
    const onRefreshRun = mock(async () => undefined)
    let renderer!: ReactTestRenderer
    act(() => {
      renderer = create(
        <PendingToolApprovalCard
          executionId="execution-1"
          toolName="mcp_calendar_delete_event"
          onRefreshRun={onRefreshRun}
        />
      )
    })
    renderers.push(renderer)
    await flush()

    expect(getExecution).toHaveBeenCalledWith('execution-1', { silent: true })
    const text = JSON.stringify(renderer.toJSON())
    expect(text).toContain('delete_event')
    expect(text).toContain('work@example.com')
    expect(text).toContain('***REDACTED***')
    const link = renderer.root.findAllByType('a')[0]
    expect(link.props.href).toBe('/app/capabilities/approvals?execution=execution-1')

    const refresh = renderer.root.findAllByType('button')[0]
    act(() => refresh?.props.onClick())
    await flush()
    expect(onRefreshRun).toHaveBeenCalled()
  })

  test('shows the server execution status without offering an answer form', async () => {
    let renderer!: ReactTestRenderer
    act(() => {
      renderer = create(<PendingToolApprovalCard executionId="execution-1" />)
    })
    renderers.push(renderer)
    await flush()

    expect(JSON.stringify(renderer.toJSON())).toContain('executionStatuses.awaiting_approval')
    expect(JSON.stringify(renderer.toJSON())).not.toContain('askUser')
  })
})
