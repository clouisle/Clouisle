import { afterEach, describe, expect, mock, spyOn, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from 'react-test-renderer'

import { teamsApi, type UserTeamInfo } from '@/lib/api'
import { TeamProvider, useTeam } from './team-context'

globalThis.IS_REACT_ACT_ENVIRONMENT = true

const STORAGE_KEY = 'clouisle-current-team-id'
const team = (id: string): UserTeamInfo => ({
  id,
  name: `Team ${id}`,
  description: null,
  avatar_url: null,
  role: 'member',
  joined_at: '2026-01-01T00:00:00Z',
})

const captured = { current: undefined as ReturnType<typeof useTeam> | undefined }
function Consumer() {
  const value = useTeam()
  React.useEffect(() => {
    captured.current = value
  }, [value])
  return null
}

const latest = () => captured.current!

const flush = async () => {
  await act(async () => {
    await Promise.resolve()
  })
}

afterEach(() => {
  mock.restore()
  delete (globalThis as { localStorage?: Storage }).localStorage
})

describe('TeamProvider', () => {
  test('loads teams and restores only a matching stored selection', async () => {
    const storage = new Map([[STORAGE_KEY, 'two']])
    globalThis.localStorage = {
      getItem: key => storage.get(key) ?? null,
      setItem: (key, value) => storage.set(key, value),
    } as Storage
    const request = Promise.withResolvers<UserTeamInfo[]>()
    spyOn(teamsApi, 'getMyTeams').mockReturnValue(request.promise)

    let renderer: ReactTestRenderer
    await act(() => {
      renderer = create(<TeamProvider><Consumer /></TeamProvider>)
    })
    expect(latest().isLoading).toBe(true)

    request.resolve([team('one'), team('two')])
    await flush()
    expect(latest().teams.map(({ id }) => id)).toEqual(['one', 'two'])
    expect(latest().currentTeam?.id).toBe('two')
    expect(storage.get(STORAGE_KEY)).toBe('two')
    act(() => renderer!.unmount())
  })

  test('defaults to the first team, persists explicit selection, and refreshes', async () => {
    const storage = new Map<string, string>()
    globalThis.localStorage = {
      getItem: key => storage.get(key) ?? null,
      setItem: (key, value) => storage.set(key, value),
    } as Storage
    const getTeams = spyOn(teamsApi, 'getMyTeams')
      .mockResolvedValueOnce([team('one'), team('two')])
      .mockResolvedValueOnce([team('two')])

    let renderer: ReactTestRenderer
    await act(async () => {
      renderer = create(<TeamProvider><Consumer /></TeamProvider>)
    })
    expect(latest().currentTeam?.id).toBe('one')
    expect(storage.get(STORAGE_KEY)).toBe('one')

    act(() => latest().setCurrentTeam(latest().teams[1]))
    expect(latest().currentTeam?.id).toBe('two')
    expect(storage.get(STORAGE_KEY)).toBe('two')

    await act(() => latest().refreshTeams())
    expect(latest().teams.map(({ id }) => id)).toEqual(['two'])
    expect(latest().currentTeam?.id).toBe('two')
    expect(getTeams).toHaveBeenCalledTimes(2)
    expect(getTeams).toHaveBeenCalledWith({ skipAuthRedirect: true })
    act(() => renderer!.unmount())
  })

  test('finishes loading without replacing state when refresh fails', async () => {
    const storage = new Map<string, string>()
    globalThis.localStorage = {
      getItem: key => storage.get(key) ?? null,
      setItem: (key, value) => storage.set(key, value),
    } as Storage
    const error = new Error('offline')
    spyOn(teamsApi, 'getMyTeams')
      .mockResolvedValueOnce([team('one')])
      .mockRejectedValueOnce(error)
    const consoleError = spyOn(console, 'error').mockImplementation(() => {})

    let renderer: ReactTestRenderer
    await act(async () => {
      renderer = create(<TeamProvider><Consumer /></TeamProvider>)
    })
    await act(() => latest().refreshTeams())

    expect(latest().isLoading).toBe(false)
    expect(latest().teams.map(({ id }) => id)).toEqual(['one'])
    expect(latest().currentTeam?.id).toBe('one')
    expect(consoleError).toHaveBeenCalledWith('Failed to fetch teams:', error)
    act(() => renderer!.unmount())
  })
})
