import { describe, expect, it, mock } from 'bun:test'

mock.module('next-intl', () => ({
  useTranslations: () => (key: string) => `range:${key}`,
}))

const { TimeRangeSelector } = await import('./time-range-selector')

describe('TimeRangeSelector', () => {
  it('renders every translated range and keeps an unknown selected value visible', () => {
    const tree = TimeRangeSelector({ value: 'custom' as never, onChange: () => {} })
    const select = tree.props.children
    const [trigger, content] = select.props.children

    expect(trigger.props.children[1].props.children).toBe('custom')
    expect(content.props.children.map((item: { props: { children: string } }) => item.props.children)).toEqual([
      'range:7d',
      'range:30d',
      'range:90d',
      'range:all',
    ])
  })

  it('reports valid selection changes and ignores empty values', () => {
    const changes: string[] = []
    const tree = TimeRangeSelector({ value: '7d', onChange: (value) => changes.push(value) })
    const onValueChange = tree.props.children.props.onValueChange as (value: string) => void

    onValueChange('30d')
    onValueChange('')

    expect(changes).toEqual(['30d'])
  })
})
