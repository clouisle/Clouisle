import { afterEach, describe, expect, it, spyOn } from 'bun:test'
import { embedApi, resolveEmbedMessage } from './embed'

const originalDocument = globalThis.document
const originalXMLHttpRequest = globalThis.XMLHttpRequest
const fetchSpies: Array<{ mockRestore(): void }> = []

function mockFetch(response: Response | Promise<Response>) {
  const fetchSpy = spyOn(globalThis, 'fetch').mockResolvedValue(response)
  fetchSpies.push(fetchSpy)
  return fetchSpy
}

afterEach(() => {
  fetchSpies.splice(0).forEach(spy => spy.mockRestore())
  Object.defineProperty(globalThis, 'document', { configurable: true, value: originalDocument })
  Object.defineProperty(globalThis, 'XMLHttpRequest', { configurable: true, value: originalXMLHttpRequest })
})

describe('embed API', () => {
  it('uses the API key and unwraps agent info', async () => {
    const agent = { id: 'agent-1', name: 'Agent' }
    const fetchSpy = mockFetch(Response.json({ data: agent }))

    await expect(embedApi.getAgentInfo('agent-1', 'secret')).resolves.toEqual(agent)
    expect(fetchSpy).toHaveBeenCalledWith(
      'http://localhost:8000/api/v1/embed/agents/agent-1/info',
      { headers: { 'Content-Type': 'application/json', Authorization: 'Bearer secret' } }
    )
  })

  it('posts workflow inputs and unwraps the run response', async () => {
    const run = { run_id: 'run-1', stream_url: '/stream' }
    const fetchSpy = mockFetch(Response.json({ data: run }))

    await expect(embedApi.runWorkflow('workflow-1', { topic: 'Bun' }, 'secret')).resolves.toEqual(run)
    expect(fetchSpy).toHaveBeenCalledWith(
      'http://localhost:8000/api/v1/embed/workflows/workflow-1/run',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: 'Bearer secret' },
        body: JSON.stringify({ inputs: { topic: 'Bun' } }),
      }
    )
  })

  it('falls back for technical messages and preserves localized user messages', () => {
    Object.defineProperty(globalThis, 'document', {
      configurable: true,
      value: { cookie: 'locale=zh-CN' },
    })

    expect(resolveEmbedMessage('errors.resource_not_found', 'fallback')).toBe('fallback')
    expect(resolveEmbedMessage('  未找到资源  ', 'fallback')).toBe('未找到资源')
  })

  it('uses the localized status fallback when an error response is not user-facing', async () => {
    mockFetch(Response.json(
      { msg: 'errors.resource_not_found' },
      { status: 404 }
    ))

    await expect(embedApi.getAgentInfo('missing', 'secret')).rejects.toThrow('The requested resource could not be found')
  })

  it('filters unsafe backend messages for the active locale', () => {
    expect(resolveEmbedMessage(' A useful message ', 'fallback')).toBe('A useful message')
    expect(resolveEmbedMessage('', 'fallback')).toBe('fallback')
    expect(resolveEmbedMessage('x'.repeat(201), 'fallback')).toBe('fallback')
    expect(resolveEmbedMessage('Failed to fetch resource', 'fallback')).toBe('fallback')
    expect(resolveEmbedMessage({ msg: 'not a string' }, 'fallback')).toBe('fallback')

    Object.defineProperty(globalThis, 'document', {
      configurable: true,
      value: { cookie: 'locale=zh-CN' },
    })
    expect(resolveEmbedMessage('English only', 'fallback')).toBe('fallback')
  })

  it('posts chat streams and aborts them', () => {
    const response = Promise.resolve(new Response())
    const fetchSpy = mockFetch(response)
    const request = { message: 'hello' }
    const result = embedApi.chatStream('agent-1', request, 'secret')

    expect(result.stream).toBe(response)
    expect(fetchSpy).toHaveBeenCalledWith(
      'http://localhost:8000/api/v1/embed/agents/agent-1/chat/stream',
      expect.objectContaining({
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: 'Bearer secret' },
        body: JSON.stringify(request),
        signal: expect.any(AbortSignal),
      })
    )
    result.abort()
    expect(fetchSpy.mock.calls[0]?.[1]?.signal).toHaveProperty('aborted', true)
  })

  it('queues, streams, and controls durable agent runs with the API key', async () => {
    const start = { run_id: 'run-1', conversation_id: 'conversation-1', user_message_id: 'user-1', status: 'queued', stream_url: '/stream' }
    const fetchSpy = mockFetch(Response.json({ data: start }))

    await expect(embedApi.startRun('agent-1', { message: 'hello' }, 'secret')).resolves.toEqual(start)
    expect(fetchSpy).toHaveBeenCalledWith(
      'http://localhost:8000/api/v1/embed/agents/agent-1/chat/runs',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: 'Bearer secret' },
        body: JSON.stringify({ message: 'hello' }),
      },
    )

    const streamResponse = new Response()
    fetchSpy.mockResolvedValueOnce(streamResponse)
    const stream = embedApi.streamRun('agent-1', 'run-1', 'secret', 4)
    expect(stream.stream).toBeInstanceOf(Promise)
    expect(fetchSpy).toHaveBeenLastCalledWith(
      'http://localhost:8000/api/v1/embed/agents/agent-1/chat/runs/run-1/stream?after_sequence=4',
      expect.objectContaining({
        headers: { Accept: 'text/event-stream', Authorization: 'Bearer secret' },
        signal: expect.any(AbortSignal),
      }),
    )
    stream.abort()
    expect(fetchSpy.mock.calls.at(-1)?.[1]?.signal).toHaveProperty('aborted', true)

    const status = { id: 'run-1', agent_id: 'agent-1', conversation_id: 'conversation-1', mode: 'send', status: 'running' }
    fetchSpy.mockResolvedValueOnce(Response.json({ data: status }))
    await expect(embedApi.getRunStatus('agent-1', 'run-1', 'secret')).resolves.toEqual(status)

    const events = [{ run_id: 'run-1', sequence: 5, timestamp: 'now', type: 'message_end', payload: {} }]
    fetchSpy.mockResolvedValueOnce(Response.json({ data: events }))
    await expect(embedApi.getRunEvents('agent-1', 'run-1', 'secret', 4)).resolves.toEqual(events)
    expect(fetchSpy).toHaveBeenLastCalledWith(
      'http://localhost:8000/api/v1/embed/agents/agent-1/chat/runs/run-1/events?after_sequence=4',
      { headers: { 'Content-Type': 'application/json', Authorization: 'Bearer secret' } },
    )

    fetchSpy.mockResolvedValueOnce(Response.json({ data: status }))
    await expect(embedApi.postRunInput('agent-1', 'run-1', { delivery: 'steer', content: 'use JSON' }, 'secret')).resolves.toEqual(status)
    expect(fetchSpy).toHaveBeenLastCalledWith(
      'http://localhost:8000/api/v1/embed/agents/agent-1/chat/runs/run-1/inputs',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: 'Bearer secret' },
        body: JSON.stringify({ delivery: 'steer', content: 'use JSON' }),
      },
    )

    fetchSpy.mockResolvedValueOnce(Response.json({ data: { ...status, status: 'queued' } }))
    const answers = { deploy_to: 'cloud', region: 'cn' }
    await expect(embedApi.postRunAnswer('agent-1', 'run-1', { tool_call_id: 'call-ask', answers }, 'secret')).resolves.toMatchObject({ status: 'queued' })
    expect(fetchSpy).toHaveBeenLastCalledWith(
      'http://localhost:8000/api/v1/embed/agents/agent-1/chat/runs/run-1/answers',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: 'Bearer secret' },
        body: JSON.stringify({ tool_call_id: 'call-ask', answers }),
      },
    )

    fetchSpy.mockResolvedValueOnce(Response.json({ data: { ...status, status: 'queued' } }))
    await expect(embedApi.postRunAnswer('agent-1', 'run-1', {
      tool_call_id: 'call-ask', answers: {}, skipped: true,
    }, 'secret')).resolves.toMatchObject({ status: 'queued' })
    expect(fetchSpy).toHaveBeenLastCalledWith(
      'http://localhost:8000/api/v1/embed/agents/agent-1/chat/runs/run-1/answers',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: 'Bearer secret' },
        body: JSON.stringify({ tool_call_id: 'call-ask', answers: {}, skipped: true }),
      },
    )

    fetchSpy.mockResolvedValueOnce(Response.json({ data: { ...status, status: 'stopping' } }))
    await expect(embedApi.stopRun('agent-1', 'run-1', 'secret')).resolves.toMatchObject({ status: 'stopping' })
  })

  it('gets messages and workflow info', async () => {
    const messages = [{ id: 'message-1' }]
    const messageFetch = mockFetch(Response.json({ data: messages }))
    await expect(embedApi.getMessages('agent-1', 'conversation-1', 'secret')).resolves.toEqual(messages)
    expect(messageFetch).toHaveBeenCalledWith(
      'http://localhost:8000/api/v1/embed/agents/agent-1/conversations/conversation-1/messages',
      { headers: { 'Content-Type': 'application/json', Authorization: 'Bearer secret' } }
    )
    messageFetch.mockRestore()

    const workflow = { id: 'workflow-1', name: 'Workflow' }
    mockFetch(Response.json({ data: workflow }))
    await expect(embedApi.getWorkflowInfo('workflow-1', 'secret')).resolves.toEqual(workflow)
  })

  it('falls back when error bodies are invalid or servers fail', async () => {
    const invalidJson = new Response('invalid', { status: 400 })
    mockFetch(invalidJson)
    await expect(embedApi.getMessages('agent-1', 'conversation-1', 'secret')).rejects.toThrow('Request failed')

    fetchSpies.splice(0).forEach(spy => spy.mockRestore())
    mockFetch(Response.json({ msg: 'traceback: internal detail' }, { status: 503 }))
    await expect(embedApi.runWorkflow('workflow-1', {}, 'secret')).rejects.toThrow('Something went wrong. Please try again later.')

    fetchSpies.splice(0).forEach(spy => spy.mockRestore())
    mockFetch(Response.json({ msg: 'errors.not_found' }, { status: 400 }))
    await expect(embedApi.getWorkflowInfo('workflow-1', 'secret')).rejects.toThrow('Request failed')
  })

  it('uploads files and reports computable progress', async () => {
    const requests: MockXMLHttpRequest[] = []
    class MockXMLHttpRequest {
      static DONE = 4
      upload: { onprogress?: (event: ProgressEvent) => void } = {}
      status = 201
      responseText = JSON.stringify({ data: { url: '/file', filename: 'file.txt' } })
      onload?: () => void
      onerror?: () => void
      openArgs?: unknown[]
      headers: Record<string, string> = {}
      body?: FormData

      constructor() { requests.push(this) }
      open(...args: unknown[]) { this.openArgs = args }
      setRequestHeader(name: string, value: string) { this.headers[name] = value }
      send(body: FormData) { this.body = body }
    }
    Object.defineProperty(globalThis, 'XMLHttpRequest', { configurable: true, value: MockXMLHttpRequest })

    const progress: number[] = []
    const upload = embedApi.uploadFile('agent-1', new File(['data'], 'file.txt'), 'secret', value => progress.push(value))
    const xhr = requests[0]!
    xhr.upload.onprogress?.({ lengthComputable: true, loaded: 1, total: 3 } as ProgressEvent)
    xhr.upload.onprogress?.({ lengthComputable: false } as ProgressEvent)
    xhr.onload?.()

    await expect(upload).resolves.toEqual({ url: '/file', filename: 'file.txt' })
    expect(progress).toEqual([33])
    expect(xhr.openArgs).toEqual(['POST', 'http://localhost:8000/api/v1/embed/agents/agent-1/upload/file?category=documents'])
    expect(xhr.headers).toEqual({ Authorization: 'Bearer secret' })
    expect(xhr.body?.get('file')).toBeInstanceOf(File)
  })

  it('rejects failed uploads and network errors', async () => {
    const requests: Array<{ status: number; responseText: string; onload?: () => void; onerror?: () => void }> = []
    class MockXMLHttpRequest {
      upload = {}
      status = 404
      responseText = JSON.stringify({ msg: 'Not available' })
      onload?: () => void
      onerror?: () => void
      constructor() { requests.push(this) }
      open() {}
      setRequestHeader() {}
      send() {}
    }
    Object.defineProperty(globalThis, 'XMLHttpRequest', { configurable: true, value: MockXMLHttpRequest })

    const rejected = embedApi.uploadFile('agent-1', new File([], 'file.txt'), 'secret')
    requests[0]!.onload?.()
    await expect(rejected).rejects.toThrow('Not available')

    const networkError = embedApi.uploadFile('agent-1', new File([], 'file.txt'), 'secret')
    requests[1]!.onerror?.()
    await expect(networkError).rejects.toThrow('Request failed')
  })

  it('parses workflow stream events and completes', async () => {
    const chunks = [
      'event: node\ndata: {"data":{"value":1},"node_id":"node-1","sequence":2,"timestamp":"now"}\n\n',
      'data: invalid\n\ndata: {"data":{"value":2}}\n\n',
    ].map(chunk => new TextEncoder().encode(chunk))
    const body = new ReadableStream({
      pull(controller) {
        const chunk = chunks.shift()
        if (chunk) controller.enqueue(chunk)
        else controller.close()
      },
    })
    mockFetch(new Response(body))
    const events: unknown[] = []
    let completed = false
    embedApi.streamWorkflowRun('run-1', 'secret', {
      fromSequence: 4,
      onEvent: event => events.push(event),
      onComplete: () => { completed = true },
    })

    await Bun.sleep(0)
    expect(events).toHaveLength(2)
    expect(events[0]).toEqual({
      type: 'node',
      data: { value: 1, node_id: 'node-1' },
      sequence: 2,
      timestamp: 'now',
    })
    expect(events[1]).toEqual(expect.objectContaining({
      type: 'message',
      data: { value: 2, node_id: undefined },
      sequence: 0,
    }))
    expect(completed).toBe(true)
  })

  it('reports workflow stream failures and ignores abort errors', async () => {
    mockFetch(new Response(null, { status: 404 }))
    const errors: Error[] = []
    embedApi.streamWorkflowRun('run-1', 'secret', { onError: error => errors.push(error) })
    await Bun.sleep(0)
    expect(errors[0]?.message).toBe('The requested resource could not be found')

    fetchSpies.splice(0).forEach(spy => spy.mockRestore())
    mockFetch(new Response(null))
    embedApi.streamWorkflowRun('run-2', 'secret', { onError: error => errors.push(error) })
    await Bun.sleep(0)
    expect(errors.at(-1)?.message).toBe('Request failed')

    fetchSpies.splice(0).forEach(spy => spy.mockRestore())
    const abortError = new Error('aborted')
    abortError.name = 'AbortError'
    const fetchSpy = spyOn(globalThis, 'fetch').mockRejectedValue(abortError)
    fetchSpies.push(fetchSpy)
    const stop = embedApi.streamWorkflowRun('run-3', 'secret', { onError: error => errors.push(error) })
    stop()
    await Bun.sleep(0)
    expect(errors).toHaveLength(2)
  })
})
