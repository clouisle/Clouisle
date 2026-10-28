import { afterEach, beforeEach, describe, expect, it, spyOn } from 'bun:test'

import { api } from './client'
import { toolMcpApi } from './tool-mcp'

let getBaseUrl: ReturnType<typeof spyOn>
let getAuthHeaders: ReturnType<typeof spyOn>
let fetchSpy: ReturnType<typeof spyOn>

const originalFetch = globalThis.fetch

beforeEach(() => {
  getBaseUrl = spyOn(api, 'getBaseUrl').mockReturnValue('https://api.example.test/api/v1')
  getAuthHeaders = spyOn(api, 'getAuthHeaders').mockReturnValue({ Authorization: 'Bearer token' })
})

afterEach(() => {
  getBaseUrl.mockRestore()
  getAuthHeaders.mockRestore()
  fetchSpy?.mockRestore()
  globalThis.fetch = originalFetch
})

function mockFetch(response: Response | Promise<Response>) {
  fetchSpy = spyOn(globalThis, 'fetch').mockResolvedValue(response)
  return fetchSpy
}

function sseResponse(chunks: string[]): Response {
  const encoder = new TextEncoder()
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk))
      controller.close()
    },
  })
  return new Response(stream, { headers: { 'content-type': 'text/event-stream' } })
}

describe('toolMcpApi.subscribeResource', () => {
  it('streams resource subscription events to the callbacks', async () => {
    mockFetch(sseResponse([
      'event: subscription_opened\n',
      'data: {"subscription_id":"sub-1","uri":"file:///a.txt"}\n\n',
      'event: resource_updated\n',
      'data: {"subscription_id":"sub-1","uri":"file:///a.txt","sequence":2}\n\n',
      'event: subscription_closed\n',
      'data: {"reason":"ttl_expired"}\n\n',
    ]))
    const opened: unknown[] = []
    const updated: unknown[] = []
    const closed: string[] = []
    const streamFinished = Promise.withResolvers<void>()

    const unsubscribe = toolMcpApi.subscribeResource(
      'tool-1',
      { teamId: 'team-1', uri: 'file:///a.txt', connection_mode: 'personal', connection_id: 'connection-1' },
      {
        onOpened: (event) => opened.push(event),
        onUpdated: (event) => updated.push(event),
        onClosed: (reason) => {
          closed.push(reason)
          streamFinished.resolve()
        },
      },
    )

    await streamFinished.promise
    expect(opened).toEqual([{ subscription_id: 'sub-1', uri: 'file:///a.txt' }])
    expect(updated).toEqual([{ subscription_id: 'sub-1', uri: 'file:///a.txt', sequence: 2 }])
    expect(closed).toEqual(['ttl_expired'])

    const [url, init] = fetchSpy.mock.calls[0] as [string, RequestInit]
    expect(url).toBe(
      'https://api.example.test/api/v1/tools/tool-1/mcp/resources/subscribe?team_id=team-1&uri=file%3A%2F%2F%2Fa.txt&connection_mode=personal&connection_id=connection-1',
    )
    expect(init.headers).toEqual({ Authorization: 'Bearer token', Accept: 'text/event-stream' })

    unsubscribe()
    expect((init.signal as AbortSignal).aborted).toBe(true)
    expect(closed).toEqual(['ttl_expired'])
  })

  it('reports a pending approval instead of closing the subscription', async () => {
    mockFetch(Response.json({
      status: 'pending_approval',
      execution_id: 'execution-2',
      pending_approval: { execution_id: 'execution-2' },
    }))
    const approvals: string[] = []
    const closed: string[] = []
    const approvalReceived = Promise.withResolvers<void>()

    toolMcpApi.subscribeResource(
      'tool-1',
      { teamId: 'team-1', uri: 'file:///a.txt' },
      {
        onOpened: () => {},
        onUpdated: () => {},
        onClosed: (reason) => closed.push(reason),
        onPendingApproval: (executionId) => {
          approvals.push(executionId)
          approvalReceived.resolve()
        },
      },
    )

    await approvalReceived.promise
    expect(approvals).toEqual(['execution-2'])
    expect(closed).toEqual([])
  })

  it('falls back to the nested approval execution id', async () => {
    mockFetch(Response.json({
      status: 'pending_approval',
      execution_id: null,
      pending_approval: { execution_id: 'execution-3' },
    }))
    const approvals: string[] = []
    const approvalReceived = Promise.withResolvers<void>()

    toolMcpApi.subscribeResource(
      'tool-1',
      { teamId: 'team-1', uri: 'file:///a.txt' },
      {
        onOpened: () => {},
        onUpdated: () => {},
        onClosed: () => {},
        onPendingApproval: (executionId) => {
          approvals.push(executionId)
          approvalReceived.resolve()
        },
      },
    )

    await approvalReceived.promise
    expect(approvals).toEqual(['execution-3'])
  })

  it('closes a subscription when the server refuses the event stream', async () => {
    mockFetch(Response.json({ detail: 'unavailable' }, { status: 503 }))
    const closed: string[] = []
    const streamClosed = Promise.withResolvers<void>()

    toolMcpApi.subscribeResource(
      'tool-1',
      { teamId: 'team-1', uri: 'file:///a.txt' },
      {
        onOpened: () => {},
        onUpdated: () => {},
        onClosed: (reason) => {
          closed.push(reason)
          streamClosed.resolve()
        },
      },
    )

    await streamClosed.promise
    expect(closed).toEqual(['connection_lost'])
  })
})
