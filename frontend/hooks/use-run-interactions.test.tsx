import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, mock, spyOn, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'
import {
  runInteractionsApi,
  type PageData,
  type RunInteraction,
  type RunInteractionResponseInput,
} from '@/lib/api'
import { useRunInteractions, type UseRunInteractionsOptions, type UseRunInteractionsReturn } from './use-run-interactions'

function interaction(id: string, overrides: Partial<RunInteraction> = {}): RunInteraction {
  return {
    id,
    kind: 'elicitation',
    status: 'pending',
    run_kind: 'agent',
    run_id: 'run-1',
    execution_id: null,
    tool_id: null,
    tool_call_id: null,
    tool_name: null,
    team_id: 'team-1',
    payload: { mode: 'form', message: 'Confirm', requested_schema: {} },
    audience: { user_ids: [], roles: [] },
    expires_at: null,
    responded_at: null,
    responded_by_id: null,
    outcome: null,
    response: null,
    created_at: '2026-10-01T00:00:00Z',
    ...overrides,
  }
}

function page(items: RunInteraction[]): PageData<RunInteraction> {
  return { items, total: items.length, page: 1, page_size: 50 }
}

function deferred<T>() {
  return Promise.withResolvers<T>()
}

let latest: UseRunInteractionsReturn | null = null

function Probe(options: UseRunInteractionsOptions) {
  const result = useRunInteractions(options)
  React.useEffect(() => {
    latest = result
  })
  return <div data-testid="probe">{result.interactions.length}</div>
}

function hook(): UseRunInteractionsReturn {
  if (!latest) throw new Error('hook has not rendered yet')
  return latest
}

async function settle() {
  await act(async () => {
    await Promise.resolve()
    await Promise.resolve()
  })
}

let renderer: ReactTestRenderer | null = null

beforeAll(() => {
  // Installing the test DOM also installs the `window` global used to read
  // the access token.
  act(() => {
    create(<div />).unmount()
  })
})

beforeEach(() => {
  latest = null
  renderer = null
  window.localStorage.setItem('access_token', 'test-token')
})

afterEach(() => {
  act(() => renderer?.unmount())
  renderer = null
  window.localStorage.clear()
  mock.restore()
})

afterAll(() => {
  mock.restore()
})

describe('useRunInteractions', () => {
  test('loads the pending list for the run and clears the loading flag', async () => {
    const list = spyOn(runInteractionsApi, 'list').mockResolvedValue(page([interaction('interaction-1')]))

    act(() => {
      renderer = create(<Probe runId="run-1" />)
    })

    expect(hook().isLoading).toBe(true)
    await settle()

    expect(list).toHaveBeenCalledWith(
      { run_id: 'run-1', status: 'pending', page: 1, page_size: 50 },
      { silent: true }
    )
    expect(hook().interactions.map((item) => item.id)).toEqual(['interaction-1'])
    expect(hook().isLoading).toBe(false)
    expect(hook().error).toBeNull()
  })

  test('forwards the configured page size', async () => {
    const list = spyOn(runInteractionsApi, 'list').mockResolvedValue(page([]))

    act(() => {
      renderer = create(<Probe runId="run-1" pageSize={5} />)
    })
    await settle()

    expect(list).toHaveBeenCalledWith(
      { run_id: 'run-1', status: 'pending', page: 1, page_size: 5 },
      { silent: true }
    )
  })

  test('does not query without an access token, an enabled run, or a run id', async () => {
    const list = spyOn(runInteractionsApi, 'list').mockResolvedValue(page([interaction('interaction-1')]))

    window.localStorage.removeItem('access_token')
    act(() => {
      renderer = create(<Probe runId="run-1" />)
    })
    await settle()
    expect(list).not.toHaveBeenCalled()
    expect(hook().interactions).toEqual([])
    expect(hook().isLoading).toBe(false)
    expect(hook().error).toBeNull()

    window.localStorage.setItem('access_token', 'test-token')
    act(() => renderer?.update(<Probe runId="run-1" enabled={false} />))
    act(() => renderer?.update(<Probe runId={null} />))
    await settle()
    expect(list).not.toHaveBeenCalled()
    expect(hook().interactions).toEqual([])
  })

  test('surfaces thrown errors as Error instances and empties the list', async () => {
    const list = spyOn(runInteractionsApi, 'list')
      .mockResolvedValueOnce(page([interaction('interaction-1')]))
      .mockRejectedValueOnce(new Error('network down'))
      .mockRejectedValueOnce('plain failure')

    act(() => {
      renderer = create(<Probe runId="run-1" />)
    })
    await settle()
    expect(hook().interactions).toHaveLength(1)

    await act(async () => {
      await hook().refresh()
    })
    expect(hook().error?.message).toBe('network down')
    expect(hook().interactions).toEqual([])
    expect(hook().isLoading).toBe(false)

    await act(async () => {
      await hook().refresh()
    })
    expect(hook().error).toBeInstanceOf(Error)
    expect(hook().error?.message).toBe('plain failure')
    expect(list).toHaveBeenCalledTimes(3)
  })

  test('ignores a stale response that resolves after a newer refresh', async () => {
    const first = deferred<PageData<RunInteraction>>()
    const second = deferred<PageData<RunInteraction>>()
    spyOn(runInteractionsApi, 'list')
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise)

    act(() => {
      renderer = create(<Probe runId="run-1" />)
    })
    await settle()

    let pending!: Promise<void>
    act(() => {
      pending = hook().refresh()
    })

    await act(async () => {
      second.resolve(page([interaction('newest')]))
      await pending
    })
    expect(hook().interactions.map((item) => item.id)).toEqual(['newest'])
    expect(hook().isLoading).toBe(false)

    await act(async () => {
      first.resolve(page([interaction('stale')]))
      await Promise.resolve()
      await Promise.resolve()
    })
    expect(hook().interactions.map((item) => item.id)).toEqual(['newest'])
  })

  test('polls while enabled, then stops when disabled or unmounted', async () => {
    const list = spyOn(runInteractionsApi, 'list').mockResolvedValue(page([]))

    act(() => {
      renderer = create(<Probe runId="run-1" pollIntervalMs={5} />)
    })
    await settle()
    expect(list).toHaveBeenCalledTimes(1)

    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 30))
    })
    const polledCalls = list.mock.calls.length
    expect(polledCalls).toBeGreaterThan(1)

    act(() => renderer?.update(<Probe runId="run-1" enabled={false} pollIntervalMs={5} />))
    await settle()
    const callsAfterDisable = list.mock.calls.length
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 30))
    })
    expect(list.mock.calls.length).toBe(callsAfterDisable)

    act(() => renderer?.update(<Probe runId="run-1" pollIntervalMs={5} />))
    await settle()
    act(() => renderer?.unmount())
    renderer = null
    const callsAfterUnmount = list.mock.calls.length
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 30))
    })
    expect(list.mock.calls.length).toBe(callsAfterUnmount)
  })

  test('refetches when the run id changes', async () => {
    const list = spyOn(runInteractionsApi, 'list')
      .mockResolvedValueOnce(page([interaction('interaction-1')]))
      .mockResolvedValueOnce(page([interaction('interaction-2', { run_id: 'run-2' })]))

    act(() => {
      renderer = create(<Probe runId="run-1" />)
    })
    await settle()
    expect(hook().interactions.map((item) => item.id)).toEqual(['interaction-1'])

    act(() => renderer?.update(<Probe runId="run-2" />))
    await settle()

    expect(list).toHaveBeenLastCalledWith(
      { run_id: 'run-2', status: 'pending', page: 1, page_size: 50 },
      { silent: true }
    )
    expect(hook().interactions.map((item) => item.id)).toEqual(['interaction-2'])
  })

  test('respond submits the answer and then reloads the pending list', async () => {
    const input: RunInteractionResponseInput = {
      action: 'accept',
      content: { confirmed: true },
      idempotency_key: 'key-1',
    }
    const responded = interaction('interaction-1', { status: 'responded', outcome: 'accept' })
    const list = spyOn(runInteractionsApi, 'list').mockResolvedValue(page([]))
    const respond = spyOn(runInteractionsApi, 'respond').mockResolvedValue(responded)

    act(() => {
      renderer = create(<Probe runId="run-1" />)
    })
    await settle()

    let result: RunInteraction | undefined
    await act(async () => {
      result = await hook().respond('interaction-1', input)
    })

    expect(respond).toHaveBeenCalledWith('interaction-1', input)
    expect(result).toBe(responded)
    expect(list).toHaveBeenCalledTimes(2)
  })

  test('respond propagates the API failure without reloading', async () => {
    const list = spyOn(runInteractionsApi, 'list').mockResolvedValue(page([]))
    const failure = new Error('interaction expired')
    const respond = spyOn(runInteractionsApi, 'respond').mockRejectedValue(failure)

    act(() => {
      renderer = create(<Probe runId="run-1" />)
    })
    await settle()

    let thrown: unknown
    await act(async () => {
      try {
        await hook().respond('interaction-1', { action: 'decline', content: null, idempotency_key: 'key-1' })
      } catch (error) {
        thrown = error
      }
    })

    expect(thrown).toBe(failure)
    expect(respond).toHaveBeenCalledTimes(1)
    expect(list).toHaveBeenCalledTimes(1)
  })
})
