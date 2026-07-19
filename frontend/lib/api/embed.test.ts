import { afterEach, describe, expect, it, spyOn } from 'bun:test'
import { embedApi, resolveEmbedMessage } from './embed'

const originalDocument = globalThis.document
const fetchSpies: Array<{ mockRestore(): void }> = []

afterEach(() => {
  fetchSpies.splice(0).forEach(spy => spy.mockRestore())
  Object.defineProperty(globalThis, 'document', { configurable: true, value: originalDocument })
})

describe('embed API', () => {
  it('uses the API key and unwraps agent info', async () => {
    const agent = { id: 'agent-1', name: 'Agent' }
    const fetchSpy = spyOn(globalThis, 'fetch').mockResolvedValue(Response.json({ data: agent }))
    fetchSpies.push(fetchSpy)

    await expect(embedApi.getAgentInfo('agent-1', 'secret')).resolves.toEqual(agent)
    expect(fetchSpy).toHaveBeenCalledWith(
      'http://localhost:8000/api/v1/embed/agents/agent-1/info',
      { headers: { 'Content-Type': 'application/json', Authorization: 'Bearer secret' } }
    )
  })

  it('posts workflow inputs and unwraps the run response', async () => {
    const run = { run_id: 'run-1', stream_url: '/stream' }
    const fetchSpy = spyOn(globalThis, 'fetch').mockResolvedValue(Response.json({ data: run }))
    fetchSpies.push(fetchSpy)

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
    const fetchSpy = spyOn(globalThis, 'fetch').mockResolvedValue(Response.json(
      { msg: 'errors.resource_not_found' },
      { status: 404 }
    ))
    fetchSpies.push(fetchSpy)

    await expect(embedApi.getAgentInfo('missing', 'secret')).rejects.toThrow('The requested resource could not be found')
  })
})
