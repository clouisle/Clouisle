import { afterEach, describe, expect, it, spyOn } from 'bun:test'
import { API_BASE_URL } from '@/lib/constants'
import {
  agentsApi,
  agentStatsApi,
  conversationsApi,
  parseSSEStream,
  publicAgentsApi,
} from './agents'
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
  it('serializes default and complete agent list queries', async () => {
    const get = spyOnApi('get').mockResolvedValue({})

    await agentsApi.getAgents()
    await agentsApi.getAgents({
      page: 2,
      pageSize: 5,
      search: 'sales agent',
      status: 'published',
      visibility: 'team',
      teamId: 'team-1',
      ownOnly: true,
    })

    expect(get).toHaveBeenNthCalledWith(1, '/agents?page=1&page_size=20')
    expect(get).toHaveBeenNthCalledWith(2, '/agents?page=2&page_size=5&keyword=sales+agent&status=published&visibility=team&team_id=team-1&own_only=true')
  })

  it('uses exact agent CRUD and lifecycle routes and payloads', async () => {
    const get = spyOnApi('get').mockResolvedValue({})
    const post = spyOnApi('post').mockResolvedValue({})
    const put = spyOnApi('put').mockResolvedValue({})
    const del = spyOnApi('delete').mockResolvedValue(undefined)
    const create = { team_id: 'team-1', name: 'Support' }
    const update = { name: 'Support 2' }

    await agentsApi.getAgent('agent-1')
    await agentsApi.createAgent(create)
    await agentsApi.updateAgent('agent-1', update)
    await agentsApi.deleteAgent('agent-1')
    await agentsApi.publishAgent('agent-1')
    await agentsApi.unpublishAgent('agent-1')
    await agentsApi.duplicateAgent('agent-1')

    expect(get).toHaveBeenCalledWith('/agents/agent-1')
    expect(put).toHaveBeenCalledWith('/agents/agent-1', update)
    expect(del).toHaveBeenCalledWith('/agents/agent-1')
    expect(post).toHaveBeenNthCalledWith(1, '/agents', create)
    expect(post).toHaveBeenNthCalledWith(2, '/agents/agent-1/publish')
    expect(post).toHaveBeenNthCalledWith(3, '/agents/agent-1/unpublish')
    expect(post).toHaveBeenNthCalledWith(4, '/agents/agent-1/duplicate')
  })

  it('uses exact conversation and message routes and payloads', async () => {
    const get = spyOnApi('get').mockResolvedValue({})
    const patch = spyOnApi('patch').mockResolvedValue({})
    const post = spyOnApi('post').mockResolvedValue({})
    const del = spyOnApi('delete').mockResolvedValue(undefined)

    await agentsApi.getAgentConversations('agent-1')
    await agentsApi.getAgentConversations('agent-1', {
      page: 3,
      pageSize: 4,
      search: 'quarterly review',
      createdAfter: '2026-01-01',
      createdBefore: '2026-02-01',
      sortBy: 'message_count',
    })
    await agentsApi.getConversation('conversation-1')
    await agentsApi.updateConversation('conversation-1', { title: 'Renamed' })
    await agentsApi.deleteConversation('conversation-1')
    await agentsApi.deleteMessage('agent-1', 'conversation-1', 'message-1')
    await agentsApi.getMessageVersions('agent-1', 'message-1')
    await agentsApi.switchMessageVersion('agent-1', 'message-1', 'version-2')
    await agentsApi.chat('agent-1', { message: 'Hello' })
    await agentsApi.getVideoGenerationStatus('agent-1', 'task 1')

    expect(get).toHaveBeenNthCalledWith(1, '/agents/agent-1/conversations?page=1&page_size=20')
    expect(get).toHaveBeenNthCalledWith(2, '/agents/agent-1/conversations?page=3&page_size=4&search=quarterly+review&created_after=2026-01-01&created_before=2026-02-01&sort_by=message_count')
    expect(get).toHaveBeenNthCalledWith(3, '/agents/conversations/conversation-1')
    expect(get).toHaveBeenNthCalledWith(4, '/agents/agent-1/messages/message-1/versions')
    expect(get).toHaveBeenNthCalledWith(5, '/agents/agent-1/media/video-status?task_id=task+1')
    expect(patch).toHaveBeenCalledWith('/agents/conversations/conversation-1', { title: 'Renamed' })
    expect(del).toHaveBeenNthCalledWith(1, '/agents/conversations/conversation-1')
    expect(del).toHaveBeenNthCalledWith(2, '/agents/agent-1/conversations/conversation-1/messages/message-1')
    expect(post).toHaveBeenNthCalledWith(1, '/agents/agent-1/messages/message-1/switch-version', { version_id: 'version-2' })
    expect(post).toHaveBeenNthCalledWith(2, '/agents/agent-1/chat', { message: 'Hello' })
  })

  it('propagates API client failures unchanged', async () => {
    const failure = new Error('network unavailable')
    spyOnApi('get').mockRejectedValue(failure)

    await expect(agentsApi.getAgent('agent-1')).rejects.toBe(failure)
  })
})

describe('agent stats API requests', () => {
  it('uses defaults and explicit query values', async () => {
    const get = spyOnApi('get').mockResolvedValue({})

    await agentStatsApi.getStats('agent-1')
    await agentStatsApi.getTrends('agent-1', '30d')
    await agentStatsApi.getToolUsage('agent-1')
    await agentStatsApi.getRecentConversations('agent-1')
    await agentStatsApi.getRecentConversations('agent-1', 25)

    expect(get).toHaveBeenNthCalledWith(1, '/agents/agent-1/stats?period=7d')
    expect(get).toHaveBeenNthCalledWith(2, '/agents/agent-1/stats/trends?period=30d')
    expect(get).toHaveBeenNthCalledWith(3, '/agents/agent-1/stats/tool-usage?period=7d')
    expect(get).toHaveBeenNthCalledWith(4, '/agents/agent-1/stats/recent-conversations?limit=10')
    expect(get).toHaveBeenNthCalledWith(5, '/agents/agent-1/stats/recent-conversations?limit=25')
  })
})

describe('admin conversation API requests', () => {
  it('serializes default and repeated list filters', async () => {
    const get = spyOnApi('get').mockResolvedValue({})

    await conversationsApi.listAll()
    await conversationsApi.listAll({
      page: 2,
      pageSize: 5,
      team_id: ['team-1', 'team-2'],
      agent_id: ['agent-1'],
      user_id: ['user-1'],
      search: 'hello world',
      untitled_only: true,
    })

    expect(get).toHaveBeenNthCalledWith(1, '/conversations?page=1&page_size=20')
    expect(get).toHaveBeenNthCalledWith(2, '/conversations?page=2&page_size=5&team_id=team-1&team_id=team-2&agent_id=agent-1&user_id=user-1&search=hello+world&untitled_only=true')
  })

  it('uses exact stats, detail, and deletion routes', async () => {
    const get = spyOnApi('get').mockResolvedValue({})
    const del = spyOnApi('delete').mockResolvedValue({})

    await conversationsApi.getStats()
    await conversationsApi.getStats('team-1')
    await conversationsApi.getTrends()
    await conversationsApi.getTrends('team-1', '30d')
    await conversationsApi.getDetail('conversation-1')
    await conversationsApi.delete('conversation-1')
    await conversationsApi.batchDelete(['conversation-1', 'conversation 2'])

    expect(get).toHaveBeenNthCalledWith(1, '/conversations/stats')
    expect(get).toHaveBeenNthCalledWith(2, '/conversations/stats?team_id=team-1')
    expect(get).toHaveBeenNthCalledWith(3, '/conversations/stats/trends?period=7d')
    expect(get).toHaveBeenNthCalledWith(4, '/conversations/stats/trends?team_id=team-1&period=30d')
    expect(get).toHaveBeenNthCalledWith(5, '/conversations/conversation-1')
    expect(del).toHaveBeenNthCalledWith(1, '/conversations/conversation-1')
    expect(del).toHaveBeenNthCalledWith(2, '/conversations?ids=conversation-1&ids=conversation+2')
  })
})

describe('streaming agent API requests', () => {
  it('sends exact unauthenticated streaming requests and exposes abort', async () => {
    const fetch = spyOnFetch().mockResolvedValue(new Response())

    const regenerate = agentsApi.regenerateStream('agent-1', 'message-1', { locale: 'en' })
    const edit = agentsApi.editMessageStream('agent-1', 'message-1', 'Revised')
    const chat = agentsApi.chatStream('agent-1', { message: 'Hello' })
    regenerate.abort()
    edit.abort()
    chat.abort()

    expect(fetch).toHaveBeenNthCalledWith(1, 'http://localhost:8000/api/v1/agents/agent-1/messages/message-1/regenerate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ variables: { locale: 'en' } }),
      signal: expect.any(AbortSignal),
    })
    expect(fetch).toHaveBeenNthCalledWith(2, 'http://localhost:8000/api/v1/agents/agent-1/messages/message-1/edit/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content: 'Revised' }),
      signal: expect.any(AbortSignal),
    })
    expect(fetch).toHaveBeenNthCalledWith(3, 'http://localhost:8000/api/v1/agents/agent-1/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: 'Hello' }),
      signal: expect.any(AbortSignal),
    })
    expect(fetch.mock.calls.map((call) => (call[1]?.signal as AbortSignal).aborted)).toEqual([
      true,
      true,
      true,
    ])

    await Promise.all([regenerate.stream, edit.stream, chat.stream])
  })
  it('starts durable runs and opens replayable event streams', async () => {
    const post = spyOnApi('post').mockResolvedValue({
      run_id: 'run-1',
      conversation_id: 'conversation-1',
      user_message_id: 'message-1',
      status: 'queued',
      stream_url: '/agents/agent-1/chat/runs/run-1/stream',
    })
    const fetch = spyOnFetch().mockResolvedValue(new Response())

    const request = { message: 'Hello', conversation_id: 'conversation-1' }
    await agentsApi.startRun('agent-1', request)
    const stream = agentsApi.streamRun('agent-1', 'run-1', 7)
    stream.abort()

    expect(post).toHaveBeenCalledWith('/agents/agent-1/chat/runs', request)
    expect(fetch).toHaveBeenCalledWith(
      'http://localhost:8000/api/v1/agents/agent-1/chat/runs/run-1/stream?after_sequence=7',
      {
        headers: { Accept: 'text/event-stream' },
        signal: expect.any(AbortSignal),
      },
    )
    expect((fetch.mock.calls[0][1]?.signal as AbortSignal).aborted).toBe(true)
    await stream.stream
  })

  it('posts structured answers for a waiting ask_user run', async () => {
    const post = spyOnApi('post').mockResolvedValue({
      id: 'run-1',
      agent_id: 'agent-1',
      conversation_id: 'conversation-1',
      mode: 'send',
      status: 'queued',
    })
    const answers = { deploy_to: 'cloud', region: 'cn' }

    await agentsApi.postRunAnswer('agent-1', 'run-1', { tool_call_id: 'call-ask', answers })

    expect(post).toHaveBeenCalledWith('/agents/agent-1/chat/runs/run-1/answers', {
      tool_call_id: 'call-ask',
      answers,
    })
  })

  it('posts an explicit skipped result for a waiting ask_user run', async () => {
    const post = spyOnApi('post').mockResolvedValue({
      id: 'run-1',
      agent_id: 'agent-1',
      conversation_id: 'conversation-1',
      mode: 'send',
      status: 'queued',
    })

    await agentsApi.postRunAnswer('agent-1', 'run-1', {
      tool_call_id: 'call-ask',
      answers: {},
      skipped: true,
    })

    expect(post).toHaveBeenCalledWith('/agents/agent-1/chat/runs/run-1/answers', {
      tool_call_id: 'call-ask',
      answers: {},
      skipped: true,
    })
  })

  it('propagates streaming fetch failures unchanged', async () => {
    const failure = new Error('stream unavailable')
    spyOnFetch().mockRejectedValue(failure)

    await expect(agentsApi.regenerateStream('agent-1', 'message-1').stream).rejects.toBe(failure)
    await expect(agentsApi.editMessageStream('agent-1', 'message-1', 'Revised').stream).rejects.toBe(failure)
    await expect(agentsApi.chatStream('agent-1', { message: 'Hello' }).stream).rejects.toBe(failure)
  })
})

describe('public agents API requests', () => {
  it('uses exact public read routes and conversation defaults', async () => {
    const fetch = spyOnFetch().mockImplementation(async () => (
      new Response(JSON.stringify({ data: {} }), { status: 200 })
    ))

    await publicAgentsApi.getPublicAgent('agent-1')
    await publicAgentsApi.getConversations('agent-1')
    await publicAgentsApi.getConversations('agent-1', { page: 3, pageSize: 5 })
    await publicAgentsApi.getConversation('conversation-1')

    const headers = { 'Content-Type': 'application/json' }
    expect(fetch).toHaveBeenNthCalledWith(1, `${API_BASE_URL}/agents/agent-1/public`, { headers })
    expect(fetch).toHaveBeenNthCalledWith(2, `${API_BASE_URL}/agents/agent-1/conversations?page=1&page_size=50`, {
      headers,
      cache: 'no-store',
    })
    expect(fetch).toHaveBeenNthCalledWith(3, `${API_BASE_URL}/agents/agent-1/conversations?page=3&page_size=5`, {
      headers,
      cache: 'no-store',
    })
    expect(fetch).toHaveBeenNthCalledWith(4, `${API_BASE_URL}/agents/conversations/conversation-1`, {
      headers,
      cache: 'no-store',
    })
  })

  it('uses exact public mutation routes and payloads', async () => {
    const fetch = spyOnFetch().mockResolvedValue(new Response(JSON.stringify({ data: {} }), { status: 200 }))

    await publicAgentsApi.deleteConversation('conversation-1')
    await publicAgentsApi.updateConversation('conversation-1', { title: 'Renamed' })

    expect(fetch).toHaveBeenNthCalledWith(1, `${API_BASE_URL}/agents/conversations/conversation-1`, {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
    })
    expect(fetch).toHaveBeenNthCalledWith(2, `${API_BASE_URL}/agents/conversations/conversation-1`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: 'Renamed' }),
    })
  })

  it('sends the exact public streaming request and exposes abort', async () => {
    const fetch = spyOnFetch().mockResolvedValue(new Response())

    const request = publicAgentsApi.chatStream('agent-1', { message: 'Hello' })
    request.abort()

    expect(fetch).toHaveBeenCalledWith(`${API_BASE_URL}/agents/agent-1/chat/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: 'Hello' }),
      signal: expect.any(AbortSignal),
    })
    expect((fetch.mock.calls[0]?.[1]?.signal as AbortSignal).aborted).toBe(true)
    await request.stream
  })

  it('propagates public streaming fetch failures unchanged', async () => {
    const failure = new Error('stream unavailable')
    spyOnFetch().mockRejectedValue(failure)

    await expect(publicAgentsApi.chatStream('agent-1', { message: 'Hello' }).stream).rejects.toBe(failure)
  })

  it('preserves safe API errors with data across public request methods', async () => {
    const errorBody = { msg: 'This agent is not available', data: { reason: 'private' } }
    spyOnFetch().mockImplementation(async () => (
      new Response(JSON.stringify(errorBody), { status: 403 })
    ))

    for (const request of [
      () => publicAgentsApi.getPublicAgent('agent-1'),
      () => publicAgentsApi.getConversations('agent-1'),
      () => publicAgentsApi.getConversation('conversation-1'),
      () => publicAgentsApi.deleteConversation('conversation-1'),
      () => publicAgentsApi.updateConversation('conversation-1', { title: 'Renamed' }),
    ]) {
      await expect(request()).rejects.toMatchObject<ApiError>({
        code: 403,
        message: 'This agent is not available',
        data: { reason: 'private' },
      })
    }
  })

  it('replaces malformed errors across public request methods', async () => {
    spyOnFetch().mockResolvedValue(new Response('not json', { status: 404 }))

    for (const request of [
      () => publicAgentsApi.getPublicAgent('missing'),
      () => publicAgentsApi.getConversations('missing'),
      () => publicAgentsApi.getConversation('missing'),
      () => publicAgentsApi.deleteConversation('missing'),
      () => publicAgentsApi.updateConversation('missing', { title: 'Renamed' }),
    ]) {
      await expect(request()).rejects.toMatchObject<ApiError>({
        code: 404,
        message: getErrorMessage('resourceNotFound'),
      })
    }
  })

  it('replaces unsafe error messages with status-specific messages', async () => {
    const fetch = spyOnFetch()
    for (const msg of [
      null,
      'Traceback: internal details',
      'errors.agent.private',
      'Exception: internal details',
      'HTTP 400 internal details',
      'Failed to fetch private endpoint',
      'line one\nline two',
      'x'.repeat(201),
      '   ',
    ]) {
      fetch.mockResolvedValueOnce(new Response(JSON.stringify({ msg }), { status: 500 }))
    }

    for (let index = 0; index < 9; index += 1) {
      await expect(publicAgentsApi.getPublicAgent('broken')).rejects.toMatchObject<ApiError>({
        code: 500,
        message: getErrorMessage('serverError'),
      })
    }

    fetch.mockResolvedValueOnce(new Response(JSON.stringify({ msg: 'errors.agent.private' }), { status: 400 }))
    await expect(publicAgentsApi.getPublicAgent('private')).rejects.toMatchObject<ApiError>({
      code: 400,
      message: getErrorMessage('requestFailed'),
    })
  })
})

describe('parseSSEStream', () => {
  it('parses split CRLF and multiline events while skipping invalid events', async () => {
    const encoder = new TextEncoder()
    const body = new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode('event: content_delta\r\ndata: {"delta":'))
        controller.enqueue(encoder.encode('"Hello"}\r\n\r\nevent: error\ndata: not-json\n\nevent: message_end\ndata: {"usage":\n'))
        controller.enqueue(encoder.encode('data: {"total_tokens":1}}'))
        controller.close()
      },
    })
    const events = []

    for await (const event of parseSSEStream(new Response(body))) events.push(event)

    expect(events).toEqual([
      { event: 'content_delta', data: { delta: 'Hello' } },
      { event: 'message_end', data: { usage: { total_tokens: 1 } } },
    ])
  })

  it('drops incomplete, data-only, and empty events at boundaries', async () => {
    const events = []
    const body = new Response([
      'data: {"orphan":true}\n\n',
      'event: content_delta\n\n',
      'event: content_delta\ndata: {"delta":"discarded"}\nevent: message_end\ndata: {"usage":{}}\n\n',
      'ignored line',
    ].join('')).body

    for await (const event of parseSSEStream(new Response(body))) events.push(event)

    expect(events).toEqual([])
  })

  it('emits a valid event from the final unterminated buffer', async () => {
    const events = []

    for await (const event of parseSSEStream(new Response('event: content_delta\ndata: {"delta":"done"}'))) {
      events.push(event)
    }

    expect(events).toEqual([{ event: 'content_delta', data: { delta: 'done' } }])
  })

  it('returns without events when the response has no body', async () => {
    const events = []
    for await (const event of parseSSEStream(new Response(null))) events.push(event)
    expect(events).toEqual([])
  })
})
