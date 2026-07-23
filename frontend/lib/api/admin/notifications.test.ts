import { afterEach, describe, expect, spyOn, test } from 'bun:test'

import { api } from '../client'
import { notificationsApi } from './notifications'

const spies: Array<ReturnType<typeof spyOn>> = []

afterEach(() => {
  for (const spy of spies) spy.mockRestore()
  spies.length = 0
})

describe('admin notificationsApi', () => {
  test('serializes list filters', async () => {
    const get = spyOn(api, 'get').mockResolvedValue(undefined)
    spies.push(get)

    await notificationsApi.adminList({
      scope: ['global', 'team'],
      team_id: 'team-1',
      user_id: 'user-1',
      type: 'announcement',
      level: ['high', 'low'],
      search: 'release notes',
      include_expired: false,
      page: 2,
      page_size: 25,
    })

    expect(get).toHaveBeenCalledWith(
      '/admin/notifications?scope=global&scope=team&team_id=team-1&user_id=user-1&type=announcement&level=high&level=low&search=release+notes&include_expired=false&page=2&page_size=25'
    )
  })

  test('creates a notification with request options', async () => {
    const post = spyOn(api, 'post').mockResolvedValue(undefined)
    spies.push(post)
    const payload = {
      scope: 'global' as const,
      type: 'announcement',
      title: 'Release',
      content: 'Available now',
    }

    await notificationsApi.adminCreate(payload, { silent: true })

    expect(post).toHaveBeenCalledWith('/admin/notifications', payload, { silent: true })
  })

  test('deletes a notification by id', async () => {
    const deleteRequest = spyOn(api, 'delete').mockResolvedValue(undefined)
    spies.push(deleteRequest)

    await notificationsApi.adminDelete('notification-1')

    expect(deleteRequest).toHaveBeenCalledWith('/admin/notifications/notification-1')
  })
})
