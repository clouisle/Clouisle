import { describe, expect, mock, test } from 'bun:test'
import type { ReactNode } from 'react'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
let locale = 'en'

mock.module('react/jsx-runtime', () => ({
  jsx,
  jsxs: jsx,
  Fragment: Symbol.for('react.fragment'),
}))
mock.module('react/jsx-dev-runtime', () => ({
  jsxDEV: jsx,
  Fragment: Symbol.for('react.fragment'),
}))
mock.module('next-intl', () => ({
  useLocale: () => locale,
  useTranslations: () => (key: string, values?: Record<string, unknown>) =>
    values ? `${key}:${JSON.stringify(values)}` : key,
}))
mock.module('lucide-react', () => ({
  Clock: () => null,
  User: () => null,
  Zap: () => null,
}))
mock.module('@/components/ui/badge', () => ({
  Badge: ({ children }: { children: ReactNode }) => children,
}))
mock.module('@/components/ui/sheet', () => ({
  SheetHeader: ({ children }: { children: ReactNode }) => children,
  SheetDescription: ({ children }: { children: ReactNode }) => children,
  SheetTitle: ({ children }: { children: ReactNode }) => children,
}))

const { ConversationDrawerHeader } = await import('./conversation-drawer-header')

type Tree = { props: Record<string, unknown> }

function render(props: React.ComponentProps<typeof ConversationDrawerHeader>) {
  return ConversationDrawerHeader(props) as Tree
}

describe('ConversationDrawerHeader', () => {
  test('renders English metadata, agent details, variables, and actions', () => {
    locale = 'en'
    const tree = render({
      title: 'Coverage review',
      createdAt: '2026-07-20T12:34:00Z',
      totalTokens: 12345,
      variables: { region: 'us', retries: 2 },
      agentName: 'Researcher',
      agentIcon: '/agent.png',
      userName: 'Taylor',
      action: 'actions',
    })

    const content = JSON.stringify(tree.props.children)
    expect(content).toContain('Coverage review')
    expect(content).toContain('drawer.tokenCount:{\\"count\\":\\"12,345\\"}')
    expect(content).toContain('Taylor')
    expect(content).toContain('Researcher')
    expect(content).toContain('/agent.png')
    expect(content).toContain('region')
    expect(content).toContain('us')
    expect(content).toContain('retries')
    expect(content).toContain('actions')
  })

  test('uses the translated title fallback and Chinese date formatting', () => {
    locale = 'zh'
    const tree = render({
      title: null,
      createdAt: '2026-07-20T12:34:00Z',
      totalTokens: 0,
    })

    const content = JSON.stringify(tree.props.children)
    expect(content).toContain('untitled')
    expect(content).toContain('drawer.tokenCount:{\\"count\\":\\"0\\"}')
    expect(content).toContain('2026')
    expect(content).not.toContain('Researcher')
  })
})
