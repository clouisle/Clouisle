import { describe, expect, it } from 'bun:test'
import { getNotificationDisplayMeta } from './display'
import type { NotificationItem } from '@/lib/api'

function notification(overrides: Partial<NotificationItem>): Pick<NotificationItem, 'type' | 'source' | 'scope' | 'level'> {
  return {
    type: 'user_mention',
    source: 'user',
    scope: 'user',
    level: 'medium',
    ...overrides,
  }
}

describe('getNotificationDisplayMeta', () => {
  it('promotes system announcements above ordinary notifications', () => {
    const meta = getNotificationDisplayMeta(notification({ type: 'system_announcement', source: 'system', level: 'medium' }))

    expect(meta.kind).toBe('announcement')
    expect(meta.isAnnouncement).toBe(true)
    expect(meta.isProminent).toBe(true)
    expect(meta.priorityScore).toBe(4)
  })

  it('classifies dot-separated security notifications as prominent without treating them as announcements', () => {
    const meta = getNotificationDisplayMeta(notification({ type: 'security.login_anomaly', source: 'system', level: 'medium' }))

    expect(meta.kind).toBe('security')
    expect(meta.isAnnouncement).toBe(false)
    expect(meta.isProminent).toBe(true)
    expect(meta.priorityScore).toBe(3)
  })

  it('classifies dot-separated delivery notifications', () => {
    const meta = getNotificationDisplayMeta(notification({ type: 'workflow.run_failed', source: 'biz', level: 'medium' }))

    expect(meta.kind).toBe('delivery')
    expect(meta.isAnnouncement).toBe(false)
    expect(meta.isProminent).toBe(false)
    expect(meta.priorityScore).toBe(2)
  })

  it('treats forced password changes as action-needed before password security fallback', () => {
    const meta = getNotificationDisplayMeta(notification({ type: 'password.force_change', source: 'system', level: 'medium' }))

    expect(meta.kind).toBe('action')
    expect(meta.isAnnouncement).toBe(false)
    expect(meta.isProminent).toBe(false)
    expect(meta.priorityScore).toBe(2)
  })

  it('keeps ordinary low-priority notifications non-prominent', () => {
    const meta = getNotificationDisplayMeta(notification({ type: 'user_mention', source: 'user', level: 'low' }))

    expect(meta.kind).toBe('action')
    expect(meta.isAnnouncement).toBe(false)
    expect(meta.isProminent).toBe(false)
    expect(meta.priorityScore).toBe(1)
  })
})
