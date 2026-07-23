import { afterEach, beforeEach, describe, expect, it, mock, spyOn } from 'bun:test'
import { api, ApiError } from './client'
import { parsePromptSSEStream, promptsApi, type PromptSSEEvent } from './prompts'

const originalFetch = globalThis.fetch

async function collectEvents(response: Response): Promise<PromptSSEEvent[]> {
  const events: PromptSSEEvent[] = []
  for await (const event of parsePromptSSEStream(response)) events.push(event)
  return events
}

function chunkedResponse(...chunks: string[]): Response {
  const encoder = new TextEncoder()
  return new Response(new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk))
      controller.close()
    },
  }))
}

describe('parsePromptSSEStream', () => {
  it('parses SSE events split across arbitrary response chunks', async () => {
    const response = chunkedResponse(
      'event: start\n',
      'data: {"model":"cla',
      'ude"}\n\nevent: content_delta\ndata: {"delta":"Hi"}\n',
      '\nevent: complete\ndata: {"total_length":2}\n\n'
    )

    expect(await collectEvents(response)).toEqual([
      { type: 'start', data: { model: 'claude' } },
      { type: 'content_delta', data: { delta: 'Hi' } },
      { type: 'complete', data: { total_length: 2 } },
    ])
  })

  it('ignores malformed data and continues parsing later events', async () => {
    const response = chunkedResponse(
      'event: content_delta\ndata: not-json\n\n',
      'event: error\ndata: {"code":500,"msg":"stopped"}\n\n'
    )

    expect(await collectEvents(response)).toEqual([
      { type: 'error', data: { code: 500, msg: 'stopped' } },
    ])
  })

  it('rejects an unreadable response', async () => {
    await expect(collectEvents(new Response(null))).rejects.toThrow('Response body is not readable')
  })
})

describe('promptsApi', () => {
  beforeEach(() => {
    spyOn(api, 'getBaseUrl').mockReturnValue('https://api.example.test')
    spyOn(api, 'getAuthHeaders').mockReturnValue({ Authorization: 'Bearer token' })
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
    mock.restore()
  })

  it('posts a generate request and returns the streaming response', async () => {
    const response = new Response('stream')
    const fetchMock = mock(async () => response)
    globalThis.fetch = fetchMock as unknown as typeof fetch
    const request = { description: 'Write a support prompt', language: 'en' as const }

    expect(await promptsApi.generate(request)).toBe(response)
    expect(fetchMock).toHaveBeenCalledWith('https://api.example.test/prompts/generate', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: 'Bearer token',
      },
      body: JSON.stringify(request),
    })
  })

  it('turns a generate API response into ApiError', async () => {
    globalThis.fetch = mock(async () => new Response(JSON.stringify({
      code: 4102,
      msg: 'Model unavailable',
      data: { model: 'claude' },
    }), { status: 400 })) as unknown as typeof fetch

    const error = await promptsApi.generate({ description: 'Help' }).catch((value) => value)

    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({
      code: 4102,
      message: 'Model unavailable',
      data: { model: 'claude' },
    })
  })

  it('falls back to the generate HTTP status when no API error is present', async () => {
    globalThis.fetch = mock(async () => new Response('{}', { status: 503 })) as unknown as typeof fetch

    await expect(promptsApi.generate({ description: 'Help' }))
      .rejects.toThrow('Failed to generate prompt: 503')
  })

  it('posts URL-encoded optimize parameters and returns the response', async () => {
    const response = new Response('stream')
    const fetchMock = mock(async () => response)
    globalThis.fetch = fetchMock as unknown as typeof fetch

    expect(await promptsApi.optimize({ current_prompt: 'Be helpful & brief', feedback: 'More detail' }))
      .toBe(response)
    expect(fetchMock).toHaveBeenCalledWith(
      'https://api.example.test/prompts/optimize?current_prompt=Be+helpful+%26+brief&feedback=More+detail',
      {
        method: 'POST',
        headers: { Authorization: 'Bearer token' },
      }
    )
  })

  it('reports optimize HTTP errors', async () => {
    globalThis.fetch = mock(async () => new Response(null, { status: 422 })) as unknown as typeof fetch

    await expect(promptsApi.optimize({ current_prompt: 'Old', feedback: 'Fix it' }))
      .rejects.toThrow('Failed to optimize prompt: 422')
  })
})
