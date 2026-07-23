import { expect, mock, test } from 'bun:test'
import type { ReactNode } from 'react'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })

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
  useTranslations: () => (key: string) => key,
}))
mock.module('@/components/ui/card', () => ({
  Card: ({ children }: { children: ReactNode }) => children,
  CardContent: ({ children }: { children: ReactNode }) => children,
  CardHeader: ({ children }: { children: ReactNode }) => children,
  CardTitle: ({ children }: { children: ReactNode }) => children,
}))
mock.module('@/components/ui/tooltip', () => ({
  Tooltip: ({ children }: { children: ReactNode }) => children,
  TooltipContent: ({ children }: { children: ReactNode }) => children,
  TooltipTrigger: ({ children }: { children: ReactNode }) => children,
}))
mock.module('lucide-react', () => ({ Cpu: () => null }))

const { ModelDetailsCard } = await import('./model-details-card')

test('renders loading and empty model states', () => {
  const loading = ModelDetailsCard({ data: [], isLoading: true })
  const empty = ModelDetailsCard({ data: [] })

  expect(JSON.stringify(loading)).toContain('common.loading')
  expect(JSON.stringify(empty)).toContain('common.noData')
  expect(JSON.stringify(loading)).toContain('models.modelDetails')
})

test('renders model usage, percentage, and unknown fallbacks', () => {
  const tree = ModelDetailsCard({
    data: [
      { model: 'Claude', count: 1234, percentage: 56.78 },
      { model: '', count: 0, percentage: 0 },
    ],
  })
  const content = JSON.stringify(tree)

  expect(content).toContain('Claude')
  expect(content).toContain('1,234')
  expect(content).toContain('"56.8","%"')
  expect(content).toContain('common.unknown')
  expect(content).toContain('common.usageCount')
})
