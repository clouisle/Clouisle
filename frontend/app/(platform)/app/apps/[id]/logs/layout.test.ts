import { expect, test } from 'bun:test'

const { default: LogsLayout } = await import('./layout')

test('passes log-page content through without an additional wrapper', () => {
  expect(LogsLayout({ children: 'log details' })).toBe('log details')
})
