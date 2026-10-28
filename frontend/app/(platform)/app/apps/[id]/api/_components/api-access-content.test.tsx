import { afterEach, describe, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'

mock.module('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}))
mock.module('lucide-react', () => ({
  Copy: () => <span data-icon="copy" />,
  Check: () => <span data-icon="check" />,
  ExternalLink: () => null,
  Key: () => null,
  AlertCircle: () => null,
}))
mock.module('sonner', () => ({ toast: { success: mock(() => {}) } }))
mock.module('@/components/ui/button', () => ({
  Button: ({ children, ...props }: React.ComponentProps<'button'>) => <button {...props}>{children}</button>,
}))
mock.module('@/components/ui/badge', () => ({
  Badge: ({ children }: React.PropsWithChildren) => <span>{children}</span>,
}))
mock.module('@/components/ui/alert', () => ({
  Alert: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  AlertDescription: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  AlertTitle: ({ children }: React.PropsWithChildren) => <strong>{children}</strong>,
}))
mock.module('@/components/ui/tabs', () => ({
  Tabs: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  TabsContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  TabsList: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  TabsTrigger: ({ children }: React.PropsWithChildren) => <button>{children}</button>,
}))
mock.module('@/components/permission-guard', () => ({
  PermissionGuard: ({ children }: React.PropsWithChildren) => <>{children}</>,
}))

const { ApiAccessContent } = await import('./api-access-content')

globalThis.IS_REACT_ACT_ENVIRONMENT = true

const renderers: ReactTestRenderer[] = []
const originalApiUrl = process.env.NEXT_PUBLIC_API_URL

function render(agent: Record<string, unknown>) {
  let renderer: ReactTestRenderer
  act(() => {
    renderer = create(<ApiAccessContent agent={agent as never} />)
  })
  renderers.push(renderer!)
  return renderer!
}

function output(renderer: ReactTestRenderer) {
  return JSON.stringify(renderer.toJSON())
}

function codeText(renderer: ReactTestRenderer) {
  return renderer.root
    .findAllByType('code')
    .flatMap((node) => node.children.filter((child): child is string => typeof child === 'string'))
    .join('\n')
}

afterEach(() => {
  for (const renderer of renderers) act(() => renderer.unmount())
  renderers.length = 0
  if (originalApiUrl === undefined) delete process.env.NEXT_PUBLIC_API_URL
  else process.env.NEXT_PUBLIC_API_URL = originalApiUrl
})

describe('ApiAccessContent approvals', () => {
  test('documents the approval pause using the original tool arguments', () => {
    const renderer = render({ id: 'agent-1', name: 'Support', status: 'published', variables: [] })
    const rendered = output(renderer)
    const codes = codeText(renderer)

    expect(rendered).toContain('approval.title')
    expect(rendered).toContain('approval.pauseTitle')
    expect(rendered).toContain('approval.waitingPayload')
    expect(codes).toContain('tool_approval')
    expect(codes).toContain('execution_id')
    expect(codes).toContain('"task_id":"T-42"')
    expect(codes).not.toContain('"arguments":{"interaction_kind"')
  })

  test('documents both decision endpoints and the decision contract', () => {
    process.env.NEXT_PUBLIC_API_URL = 'https://api.example.test'
    const renderer = render({ id: 'agent-1', name: 'Support', status: 'published', variables: [] })
    const rendered = output(renderer)
    const codes = codeText(renderer)

    expect(rendered).toContain('https://api.example.test/api/v1/tool-executions/{execution_id}/decision')
    expect(rendered).toContain('https://api.example.test/api/v1/tool-approvals/{request_id}/decision')
    expect(rendered).toContain('approval.decisionBody')
    expect(rendered).toContain('approval.decisionResponse')
    expect(codes).toContain('"decision": "approve"')
    expect(codes).toContain('"idempotency_key": "decision-2026-10-28-0001"')
    expect(codes).toContain('"execution_status": "ready"')
    expect(codes).toContain('"remaining_approvals": 0')
    expect(rendered).toContain('approval.previewNote')
    expect(rendered).toContain('approval.resumeNote')
  })

  test('warns that API-key calls fail closed instead of waiting for approval', () => {
    const renderer = render({ id: 'agent-1', name: 'Support', status: 'published', variables: [] })
    const rendered = output(renderer)

    expect(rendered).toContain('approval.apiKeyTitle')
    expect(rendered).toContain('approval.apiKeyDescription')
  })

  test('keeps the ask_user answers endpoint distinct from approvals', () => {
    const renderer = render({ id: 'agent-1', name: 'Support', status: 'published', variables: [] })
    const rendered = output(renderer)

    expect(rendered).toContain('/chat/runs/{run_id}/answers')
    expect(rendered).toContain('answerNote')
    expect(rendered).not.toContain('/chat/runs/{run_id}/answers/decision')
  })
})
