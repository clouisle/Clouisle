import { afterEach, beforeEach, describe, expect, mock, spyOn, test } from 'bun:test'
import { api } from './client'
import { imApi } from './im'

let get: ReturnType<typeof spyOn>
let post: ReturnType<typeof spyOn>

beforeEach(() => {
  get = spyOn(api, 'get').mockResolvedValue(undefined)
  post = spyOn(api, 'post').mockResolvedValue(undefined)
})

afterEach(() => {
  get.mockRestore()
  post.mockRestore()
})

describe('imApi', () => {
  test('constructs conversation, message, read and search requests', async () => {
    await imApi.listConversations('team-1')
    expect(get).toHaveBeenCalledWith('/im/conversations', { params: { team_id: 'team-1' } })

    await imApi.createDirectConversation('team-1', 'user-2')
    expect(post).toHaveBeenCalledWith('/im/conversations/direct', { team_id: 'team-1', target_user_id: 'user-2' })

    await imApi.getMessages('conv-1', { before_seq: 10, limit: 20 })
    expect(get).toHaveBeenCalledWith('/im/conversations/conv-1/messages', { params: { before_seq: 10, limit: 20 } })

    await imApi.sendMessage('conv-1', { content: 'hello', client_msg_id: 'c1' })
    expect(post).toHaveBeenCalledWith('/im/conversations/conv-1/messages', { content: 'hello', client_msg_id: 'c1' })

    await imApi.markRead('conv-1', 15)
    expect(post).toHaveBeenCalledWith('/im/conversations/conv-1/read', { up_to_seq: 15 })

    await imApi.getUnreadCount({ silent: true })
    expect(get).toHaveBeenCalledWith('/im/unread-count', { silent: true, skipAuthRedirect: undefined })

    await imApi.listTeamCandidates('team-1')
    expect(get).toHaveBeenCalledWith('/im/team-members', { params: { team_id: 'team-1' } })

    await imApi.searchMessages('team-1', 'keyword', 10)
    expect(get).toHaveBeenCalledWith('/im/search', { params: { team_id: 'team-1', q: 'keyword', limit: 10 } })
  })

  test('subscribeEvents handles SSE events and allows aborting', async () => {
    const encoder = new TextEncoder()
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode(':ping\n\nevent: new_message\ndata: {"id": "msg-1"}\n\nevent: conversation_read\ndata: {"conversation_id": "c1", "last_read_seq": 5}\n\n'))
        controller.close()
      },
    })

    const fetchMock = spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(stream, { headers: { 'Content-Type': 'text/event-stream' } })
    )

    const { promise, resolve } = Promise.withResolvers<void>()
    const onNewMessage = mock(() => {})
    const onConversationRead = mock(() => {
      resolve()
    })

    const unsubscribe = imApi.subscribeEvents({
      onNewMessage,
      onConversationRead,
    })

    await promise
    unsubscribe()
    expect(fetchMock).toHaveBeenCalled()
    fetchMock.mockRestore()
  })
})
