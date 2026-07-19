import { afterEach, describe, expect, it, spyOn } from 'bun:test'
import { API_BASE_URL } from '@/lib/constants'
import { agentsApi, publicAgentsApi } from './agents'
import { api, ApiError, getErrorMessage } from './client'

const restorers: Array<{ mockRestore(): void }> = []

function spyOnApi<T extends keyof typeof api>(method: T) {
  const spy = spyOn(api, method)
  restorers.push(spy)
  return spy
}

function spyOnFetch() {
  const spy = spyOn(globalThis, 'fetch')
  restorers.push(spy)
  return spy
}

afterEach(() => {
  restorers.splice(0).forEach((spy) => spy.mockRestore())
})

describe('agents API requests', () => {
  it('serializes agent list filters into the expected query', async () => {
    const get = spyOnApi('get').mockResolvedValue({})

    await agentsApi.getAgents({
      page: 2,
      pageSize: 5,
      search: 'sales agent',
      status: 'published',
      visibility: 'team',
      teamId: 'team-1',
      ownOnly: true,
    })

    expect(get).toHaveBeenCalledWith('/agents?page=2&page_size=5&keyword=sales+agent&status=published&visibility=team&team_id=team-1&own_only=true')
  })

  it('sends agent and message-version payloads to their scoped routes', async () => {
    const post = spyOnApi('post').mockResolvedValue({})
    const input = { team_id: 'team-1', name: 'Support' }

    await agentsApi.createAgent(input)
    await agentsApi.switchMessageVersion('agent-1', 'message-1', 'version-2')

    expect(post).toHaveBeenNthCalledWith(1, '/agents', input)
    expect(post).toHaveBeenNthCalledWith(2, '/agents/agent-1/messages/message-1/switch-version', { version_id: 'version-2' })
  })
})

describe('public agents API requests', () => {
  it('uses public conversation defaults and sends update payloads', async () => {
    const fetch = spyOnFetch()
      .mockResolvedValueOnce(new Response(JSON.stringify({ data: { items: [] } }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ data: { id: 'conversation-1' } }), { status: 200 }))

    await publicAgentsApi.getConversations('agent-1')
    await publicAgentsApi.updateConversation('conversation-1', { title: 'Renamed' })

    expect(fetch).toHaveBeenNthCalledWith(1, `${API_BASE_URL}/agents/agent-1/conversations?page=1&page_size=50`, {
      headers: { 'Content-Type': 'application/json' },
    })
    expect(fetch).toHaveBeenNthCalledWith(2, `${API_BASE_URL}/agents/conversations/conversation-1`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: 'Renamed' }),
    })
  })

  it('preserves safe public API messages and replaces technical failures with status messages', async () => {
    spyOnFetch()
      .mockResolvedValueOnce(new Response(JSON.stringify({ msg: 'This agent is not available' }), { status: 403 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ msg: 'Traceback: internal details' }), { status: 500 }))

    await expect(publicAgentsApi.getPublicAgent('agent-1')).rejects.toMatchObject<ApiError>({
      code: 403,
      message: 'This agent is not available',
    })
    await expect(publicAgentsApi.getPublicAgent('agent-1')).rejects.toMatchObject<ApiError>({
      code: 500,
      message: getErrorMessage('serverError'),
    })
  })
})
