import { afterAll, beforeEach, describe, expect, mock, test } from 'bun:test'

const get = mock(() => Promise.resolve([]))
const post = mock(() => Promise.resolve({}))
const put = mock(() => Promise.resolve({}))
const del = mock(() => Promise.resolve({}))
const stopRun = mock(() => Promise.resolve({}))
const getAuthHeaders = mock(() => ({ Authorization: 'Bearer token' }))

mock.module('./client', () => ({
  api: { get, post, put, delete: del, getAuthHeaders },
}))
mock.module('./agents', () => ({ publicAgentsApi: { stopRun } }))

const { wechatKnowledgeApi } = await import('./wechat-knowledge')

type FetchCall = { url: string; headers: Record<string, string> | undefined }
const fetchCalls: FetchCall[] = []
let fetchOk = true
const fetchImpl = (url: string, init?: { headers?: Record<string, string> }) => {
  fetchCalls.push({ url, headers: init?.headers })
  return Promise.resolve(
    fetchOk ? { ok: true, blob: () => Promise.resolve(new Blob(['data'])) } : { ok: false },
  )
}

const created: string[] = []
const revoked: string[] = []
const scheduled: Array<() => void> = []
const clicked: string[] = []
const link = {
  href: '',
  download: '',
  click: () => clicked.push('clicked'),
}

const stubbed = {
  fetch: Object.getOwnPropertyDescriptor(globalThis, 'fetch'),
  document: Object.getOwnPropertyDescriptor(globalThis, 'document'),
  window: Object.getOwnPropertyDescriptor(globalThis, 'window'),
  createObjectURL: Object.getOwnPropertyDescriptor(URL, 'createObjectURL'),
  revokeObjectURL: Object.getOwnPropertyDescriptor(URL, 'revokeObjectURL'),
}

function defineGlobal(key: 'fetch' | 'document' | 'window', value: unknown) {
  Object.defineProperty(globalThis, key, { value, configurable: true, writable: true })
}

function restore(key: 'fetch' | 'document' | 'window', descriptor?: PropertyDescriptor) {
  if (descriptor) Object.defineProperty(globalThis, key, descriptor)
  else delete (globalThis as Partial<typeof globalThis>)[key]
}

defineGlobal('fetch', fetchImpl)
defineGlobal('document', { createElement: () => link })
defineGlobal('window', {
  setTimeout: (callback: () => void) => {
    scheduled.push(callback)
    return 0
  },
})
Object.defineProperty(URL, 'createObjectURL', {
  value: () => {
    created.push('blob:original')
    return 'blob:original'
  },
  configurable: true,
  writable: true,
})
Object.defineProperty(URL, 'revokeObjectURL', {
  value: (url: string) => revoked.push(url),
  configurable: true,
  writable: true,
})

beforeEach(() => {
  for (const spy of [get, post, put, del, stopRun, getAuthHeaders]) spy.mockClear()
  fetchCalls.length = 0
  created.length = 0
  revoked.length = 0
  scheduled.length = 0
  clicked.length = 0
  link.href = ''
  link.download = ''
  fetchOk = true
})

afterAll(() => {
  restore('fetch', stubbed.fetch)
  restore('document', stubbed.document)
  restore('window', stubbed.window)
  for (const [key, descriptor] of [
    ['createObjectURL', stubbed.createObjectURL],
    ['revokeObjectURL', stubbed.revokeObjectURL],
  ] as const) {
    if (descriptor) Object.defineProperty(URL, key, descriptor)
    else delete (URL as Partial<typeof URL>)[key]
  }
})

describe('wechatKnowledgeApi request composition', () => {
  test('lists connections and collection targets', async () => {
    await wechatKnowledgeApi.bindings()
    await wechatKnowledgeApi.targets()
    expect(get.mock.calls).toEqual([
      ['/wechat-knowledge/bindings'],
      ['/wechat-knowledge/targets'],
    ])
  })

  test('scopes model and agent-model lookups to their owner', async () => {
    await wechatKnowledgeApi.models('kb-1')
    await wechatKnowledgeApi.agentModels('agent-1')
    expect(get.mock.calls).toEqual([
      ['/wechat-knowledge/models', { params: { knowledge_base_id: 'kb-1' } }],
      ['/wechat-knowledge/agent-models', { params: { agent_id: 'agent-1' } }],
    ])
  })

  test('lists agents and saves the single active purpose', async () => {
    await wechatKnowledgeApi.agents()
    await wechatKnowledgeApi.purpose('binding-1', { purpose: 'agent', agent_id: 'agent-1' })
    expect(get.mock.calls[0]).toEqual(['/wechat-knowledge/agents'])
    expect(put.mock.calls[0]).toEqual([
      '/wechat-knowledge/bindings/binding-1/purpose',
      { purpose: 'agent', agent_id: 'agent-1' },
    ])
  })

  test('delegates stopping a run to the public agent API', async () => {
    await wechatKnowledgeApi.stopRun('agent-1', 'run-1')
    expect(stopRun.mock.calls[0]).toEqual(['agent-1', 'run-1'])
  })

  test('authorizes a new connection and polls it with the submission timeout', async () => {
    await wechatKnowledgeApi.login()
    await wechatKnowledgeApi.poll('login-1')
    await wechatKnowledgeApi.poll('login-1', '123456')
    expect(post.mock.calls).toEqual([
      ['/wechat-knowledge/logins'],
      ['/wechat-knowledge/logins/login-1/poll', { verify_code: undefined }, { timeout: 50000 }],
      ['/wechat-knowledge/logins/login-1/poll', { verify_code: '123456' }, { timeout: 50000 }],
    ])
  })

  test('disconnects a connection and lists both receipt kinds', async () => {
    await wechatKnowledgeApi.disconnect('binding-1')
    await wechatKnowledgeApi.receipts()
    await wechatKnowledgeApi.agentReceipts()
    await wechatKnowledgeApi.agentReceipts('binding-1')
    expect(del.mock.calls[0]).toEqual(['/wechat-knowledge/bindings/binding-1'])
    expect(get.mock.calls).toEqual([
      ['/wechat-knowledge/receipts'],
      ['/wechat-knowledge/agent-receipts', undefined],
      ['/wechat-knowledge/agent-receipts', { params: { binding_id: 'binding-1' } }],
    ])
  })
})

describe('wechatKnowledgeApi original download', () => {
  test('downloads with auth headers and releases the object URL', async () => {
    await wechatKnowledgeApi.original('item-1', 'report.pdf')

    expect(fetchCalls).toHaveLength(1)
    expect(fetchCalls[0].url.endsWith('/wechat-knowledge/items/item-1/original')).toBe(true)
    expect(fetchCalls[0].headers).toEqual({ Authorization: 'Bearer token' })
    expect(created).toEqual(['blob:original'])
    expect(link.download).toBe('report.pdf')
    expect(link.href).toBe('blob:original')
    expect(clicked).toEqual(['clicked'])
    // The URL survives the click and is released once the browser has used it.
    expect(revoked).toEqual([])
    scheduled.forEach((callback) => callback())
    expect(revoked).toEqual(['blob:original'])
  })

  test('reports a failed original download instead of clicking a dead link', async () => {
    fetchOk = false

    await expect(wechatKnowledgeApi.original('item-1', 'report.pdf')).rejects.toThrow(
      'Unable to download original',
    )
    expect(clicked).toEqual([])
  })
})
