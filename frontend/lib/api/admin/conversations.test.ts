import { describe, expect, test, spyOn } from 'bun:test'

import { api } from '../client'
import { conversationsApi } from './conversations'

describe('conversationsApi', () => {
  test('uses the public routes and forwards query parameters', async () => {
    const get = spyOn(api, 'get').mockResolvedValue({} as never)
    const listParams = { page: 2, page_size: 25, team_id: 'team-1' }
    const statsParams = { team_id: 'team-1' }
    const trendsParams = { team_id: 'team-1', period: '30d' as const }

    try {
      await conversationsApi.listAll(listParams)
      await conversationsApi.getStats(statsParams)
      await conversationsApi.getTrends(trendsParams)
      await conversationsApi.getDetail('conversation-1')

      expect(get.mock.calls).toEqual([
        ['/admin/conversations', { params: listParams }],
        ['/admin/conversations/stats', { params: statsParams }],
        ['/admin/conversations/stats/trends', { params: trendsParams }],
        ['/admin/conversations/conversation-1'],
      ])
    } finally {
      get.mockRestore()
    }
  })

  test('preserves optional parameter defaults', async () => {
    const get = spyOn(api, 'get').mockResolvedValue({} as never)

    try {
      await conversationsApi.getStats()
      await conversationsApi.getTrends()

      expect(get.mock.calls).toEqual([
        ['/admin/conversations/stats', { params: undefined }],
        ['/admin/conversations/stats/trends', { params: undefined }],
      ])
    } finally {
      get.mockRestore()
    }
  })

  test('builds single and repeated-id delete requests', async () => {
    const remove = spyOn(api, 'delete').mockResolvedValue({} as never)

    try {
      await conversationsApi.delete('conversation-1')
      await conversationsApi.batchDelete(['conversation-1', 'conversation 2'])
      await conversationsApi.batchDelete([])

      expect(remove.mock.calls).toEqual([
        ['/admin/conversations/conversation-1'],
        ['/admin/conversations?ids=conversation-1&ids=conversation+2'],
        ['/admin/conversations?'],
      ])
    } finally {
      remove.mockRestore()
    }
  })

  test('propagates request errors unchanged', async () => {
    const error = new Error('request failed')
    const remove = spyOn(api, 'delete').mockRejectedValue(error)

    try {
      await expect(conversationsApi.delete('conversation-1')).rejects.toBe(error)
    } finally {
      remove.mockRestore()
    }
  })
})
