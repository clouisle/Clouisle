import { afterEach, beforeEach, describe, expect, spyOn, test } from 'bun:test'

import { api } from './client'
import { notificationsApi } from './notifications'

let get: ReturnType<typeof spyOn>
let post: ReturnType<typeof spyOn>
let remove: ReturnType<typeof spyOn>

beforeEach(() => {
  get = spyOn(api, 'get').mockResolvedValue(undefined)
  post = spyOn(api, 'post').mockResolvedValue(undefined)
  remove = spyOn(api, 'delete').mockResolvedValue(undefined)
})

afterEach(() => {
  get.mockRestore()
  post.mockRestore()
  remove.mockRestore()
})

describe('notificationsApi', () => {
  test('constructs list requests with empty and populated query parameters', async () => {
    const params = {
      scope: 'team' as const,
      type: 'billing',
      level: 'high' as const,
      search: 'invoice overdue',
      unread_only: true,
      created_from: '2026-07-01T00:00:00Z',
      created_to: '2026-07-19T23:59:59Z',
      page: 2,
      page_size: 50,
    }

    await notificationsApi.list({})
    await notificationsApi.list(params)

    expect(get).toHaveBeenNthCalledWith(1, '/notifications', { params: {} })
    expect(get).toHaveBeenNthCalledWith(2, '/notifications', { params })
  })

  test('constructs unread-count and mark-read requests', async () => {
    const unreadCount = { total: 3 }
    const readResult = { updated: 2 }
    get.mockResolvedValueOnce(unreadCount)
    post.mockResolvedValueOnce(readResult)

    expect(await notificationsApi.unreadCount()).toBe(unreadCount)
    await notificationsApi.unreadCount({ silent: true, skipAuthRedirect: true })
    expect(await notificationsApi.markRead({ notification_ids: ['notification-1', 'notification-2'] })).toBe(readResult)
    await notificationsApi.markRead({ mark_all: true })

    expect(get).toHaveBeenNthCalledWith(1, '/notifications/unread-count', {
      silent: undefined,
      skipAuthRedirect: undefined,
    })
    expect(get).toHaveBeenNthCalledWith(2, '/notifications/unread-count', {
      silent: true,
      skipAuthRedirect: true,
    })
    expect(post).toHaveBeenNthCalledWith(1, '/notifications/read', {
      notification_ids: ['notification-1', 'notification-2'],
    })
    expect(post).toHaveBeenNthCalledWith(2, '/notifications/read', { mark_all: true })
  })

  test('constructs admin list, create, and delete requests', async () => {
    const params = {
      scope: ['global', 'user'] as const,
      team_id: 'team-1',
      user_id: 'user-1',
      type: 'system',
      level: ['medium', 'high'] as const,
      search: 'maintenance',
      include_expired: true,
      page: 3,
      page_size: 25,
    }
    const payload = {
      scope: 'user' as const,
      user_id: 'user-1',
      type: 'system',
      title: 'Maintenance',
      content: 'Scheduled maintenance',
      level: 'medium' as const,
      notify_channels: ['email', 'slack'] as const,
    }

    await notificationsApi.adminList(params)
    await notificationsApi.adminCreate(payload)
    await notificationsApi.adminDelete('notification-1')

    expect(get).toHaveBeenCalledWith('/admin/notifications', { params })
    expect(post).toHaveBeenCalledWith('/admin/notifications', payload)
    expect(remove).toHaveBeenCalledWith('/admin/notifications/notification-1')
  })

  test('forwards client errors without masking them', async () => {
    const error = new Error('network unavailable')
    get.mockRejectedValueOnce(error)

    await expect(notificationsApi.list({ page: 1 })).rejects.toBe(error)
    expect(get).toHaveBeenCalledWith('/notifications', { params: { page: 1 } })
  })
})
