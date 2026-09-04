import { afterEach, describe, expect, mock, spyOn, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'

mock.module('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}))

mock.module('./audit-logs-table', () => ({
  AuditLogsTable: () => <section aria-label="audit log table" />,
}))

import { auditLogsApi } from '@/lib/api/admin/audit-logs'
import { AuditLogsClient } from './audit-logs-client'

globalThis.IS_REACT_ACT_ENVIRONMENT = true

const renderers: ReactTestRenderer[] = []

function text(renderer: ReactTestRenderer) {
  return JSON.stringify(renderer.toJSON())
}

async function render() {
  let renderer: ReactTestRenderer
  await act(async () => {
    renderer = create(<AuditLogsClient />)
    await Promise.resolve()
  })
  renderers.push(renderer!)
  return renderer!
}

afterEach(() => {
  for (const renderer of renderers) act(() => renderer.unmount())
  renderers.length = 0
  mock.restore()
})

describe('AuditLogsClient', () => {
  test('exposes its heading, activity-table landmark, and loading metrics', async () => {
    let resolveStats!: (value: { total_logs: number; today_logs: number; failed_logs: number; active_users: number }) => void
    spyOn(auditLogsApi, 'getStats').mockReturnValue(new Promise((resolve) => { resolveStats = resolve }))

    const renderer = await render()

    expect(renderer.root.findByType('h1').children).toEqual(['title'])
    expect(renderer.root.findByProps({ 'aria-label': 'audit log table' })).toBeDefined()
    expect(text(renderer)).toContain('...')

    await act(async () => resolveStats({ total_logs: 0, today_logs: 0, failed_logs: 0, active_users: 0 }))
  })

  test('renders formatted activity statistics after loading', async () => {
    spyOn(auditLogsApi, 'getStats').mockResolvedValue({
      total_logs: 1234,
      today_logs: 56,
      failed_logs: 7,
      active_users: 8,
    })

    const renderer = await render()

    expect(text(renderer)).toContain('1,234')
    expect(text(renderer)).toContain('56')
    expect(text(renderer)).toContain('7')
    expect(text(renderer)).toContain('8')
  })

  test('falls back to zero metrics when the activity request fails', async () => {
    spyOn(console, 'error').mockImplementation(() => {})
    spyOn(auditLogsApi, 'getStats').mockRejectedValue(new Error('unavailable'))

    const renderer = await render()

    expect(text(renderer)).not.toContain('...')
    expect(renderer.root.findAllByType('div').filter((node) => node.children.length === 1 && node.children[0] === '0')).toHaveLength(4)
  })
})
