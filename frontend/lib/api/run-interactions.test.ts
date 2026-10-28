import { afterEach, beforeEach, describe, expect, spyOn, test } from 'bun:test'

import { api } from './client'
import { getElicitationUrl, runInteractionsApi } from './run-interactions'

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

describe('runInteractionsApi', () => {
  test('defaults the durable list to pending interactions', async () => {
    await runInteractionsApi.list()
    await runInteractionsApi.list(
      { run_id: 'run-1', kind: 'sampling', status: 'responded', page: 2, page_size: 5 },
      { silent: true }
    )

    expect(get).toHaveBeenNthCalledWith(1, '/run-interactions', {
      params: { status: 'pending' },
      silent: undefined,
    })
    expect(get).toHaveBeenNthCalledWith(2, '/run-interactions', {
      params: {
        page: 2,
        page_size: 5,
        kind: 'sampling',
        run_id: 'run-1',
        status: 'responded',
      },
      silent: true,
    })
  })

  test('submits the authorized response unchanged', async () => {
    const interaction = { id: 'interaction-1', status: 'responded' }
    post.mockResolvedValueOnce(interaction)

    const result = await runInteractionsApi.respond('interaction-1', {
      action: 'accept',
      content: { answer: 'yes' },
      idempotency_key: 'response-1',
    })

    expect(result).toBe(interaction)
    expect(post).toHaveBeenCalledWith('/run-interactions/interaction-1/response', {
      action: 'accept',
      content: { answer: 'yes' },
      idempotency_key: 'response-1',
    })
  })

  test('rejects HTTP(S)-only URLs for URL elicitation', () => {
    expect(
      getElicitationUrl({ mode: 'url', message: 'Authorize', url: 'https://example.com/auth' })
    ).toBe('https://example.com/auth')
    expect(
      getElicitationUrl({ mode: 'url', message: 'Authorize', url: 'javascript:alert(1)' })
    ).toBeNull()
    expect(getElicitationUrl({ mode: 'sampling', system_prompt: null, messages: [], max_tokens: 1, model_preferences: null })).toBeNull()
  })
})
