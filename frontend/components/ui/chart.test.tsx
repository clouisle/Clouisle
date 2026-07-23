import { expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
let chartContext: Record<string, unknown> | null = null

function Provider() {}
function ResponsiveContainer() {}
function Tooltip() {}
function Legend() {}

mock.module('react/jsx-runtime', () => ({
  jsx,
  jsxs: jsx,
  Fragment: Symbol.for('react.fragment'),
}))
mock.module('react/jsx-dev-runtime', () => ({
  jsxDEV: jsx,
  Fragment: Symbol.for('react.fragment'),
}))
mock.module('react', () => ({
  createContext: () => ({ Provider }),
  forwardRef: (render: (...args: unknown[]) => unknown) => render,
  useContext: () => chartContext,
  useId: () => ':chart:',
  useMemo: (factory: () => unknown) => factory(),
}))
mock.module('recharts', () => ({ ResponsiveContainer, Tooltip, Legend }))
mock.module('@/lib/utils', () => ({
  cn: (...values: unknown[]) => values.filter(Boolean).join(' '),
}))

const {
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartStyle,
  ChartTooltip,
  ChartTooltipContent,
} = await import('./chart')

test('creates themed chart styles and a named container', () => {
  const emptyStyle = ChartStyle({ id: 'chart-empty', config: { visitors: { label: 'Visitors' } } })
  const style = ChartStyle({
    id: 'chart-sales',
    config: {
      sales: { color: '#123456' },
      forecast: { theme: { light: '#abcdef', dark: '#fedcba' } },
    },
  }) as { props: Record<string, { __html: string }> }
  const container = ChartContainer({
    id: 'sales',
    config: { sales: { color: '#123456' } },
    className: 'report',
    children: 'chart',
  }) as { props: Record<string, unknown> }
  const content = container.props.children as { props: Record<string, unknown> }

  expect(emptyStyle).toBeNull()
  expect(style.props.dangerouslySetInnerHTML.__html).toContain('--color-sales: #123456;')
  expect(style.props.dangerouslySetInnerHTML.__html).toContain('.dark [data-chart=chart-sales]')
  expect((container.type as { name?: string }).name).toBe('Provider')
  expect(content.props['data-chart']).toBe('chart-sales')
  expect(content.props.className).toContain('report')
  expect(content.props.children).toHaveLength(2)
  expect(ChartTooltip).toBe(Tooltip)
  expect(ChartLegend).toBe(Legend)
})

test('renders tooltip and legend payload metadata', () => {
  chartContext = {
    config: {
      sales: { label: 'Sales', color: '#123456' },
      visits: { label: 'Visits', color: '#abcdef' },
    },
  }
  const payload = [{ dataKey: 'sales', name: 'sales', value: 1234, color: '#123456' }]
  const tooltip = ChartTooltipContent({ active: true, payload, label: 'sales' }, null)
  const legend = ChartLegendContent({ payload: [{ dataKey: 'visits', color: '#abcdef' }] }, null)

  expect(JSON.stringify(tooltip)).toContain('Sales')
  expect(JSON.stringify(tooltip)).toContain('1,234')
  expect(JSON.stringify(legend)).toContain('Visits')
  expect(JSON.stringify(legend)).toContain('#abcdef')
})

test('uses tooltip formatters and handles inactive or missing context states', () => {
  chartContext = { config: { sales: { label: 'Sales', color: '#123456' } } }
  const formatter = mock(() => 'formatted')
  const payload = [{ dataKey: 'sales', name: 'sales', value: 2, color: '#123456' }]
  const tooltip = ChartTooltipContent({ active: true, payload, formatter, indicator: 'line' }, null)

  expect(JSON.stringify(tooltip)).toContain('formatted')
  expect(formatter).toHaveBeenCalledWith(2, 'sales', payload[0], 0, undefined)
  expect(ChartTooltipContent({ active: false, payload: [] }, null)).toBeNull()
  expect(ChartLegendContent({ payload: [] }, null)).toBeNull()

  chartContext = null
  expect(() => ChartTooltipContent({ active: true, payload: [] }, null)).toThrow(
    'useChart must be used within a <ChartContainer />',
  )
})
