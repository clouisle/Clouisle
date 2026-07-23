import { afterEach, describe, expect, it, mock, spyOn } from 'bun:test'

import { api } from '../client'
import { teamsApi } from './teams'

afterEach(() => mock.restore())

describe('teamsApi requests', () => {
  it('gets teams with defaults and an encoded search', async () => {
    const get = spyOn(api, 'get').mockResolvedValue({ items: [], total: 0, page: 2, page_size: 25, total_pages: 0 })

    await teamsApi.getTeams(2, 25, 'R&D / 核心')

    expect(get).toHaveBeenCalledTimes(1)
    expect(get).toHaveBeenCalledWith('/admin/teams?page=2&page_size=25&search=R%26D%20%2F%20%E6%A0%B8%E5%BF%83')
  })

  it('omits an empty search from the default teams request', async () => {
    const get = spyOn(api, 'get').mockResolvedValue({ items: [], total: 0, page: 1, page_size: 50, total_pages: 0 })

    await teamsApi.getTeams()

    expect(get).toHaveBeenCalledTimes(1)
    expect(get).toHaveBeenCalledWith('/admin/teams?page=1&page_size=50')
  })

  it('creates a team with the exact payload', async () => {
    const post = spyOn(api, 'post').mockResolvedValue({})
    const input = { name: 'Platform', description: 'Core services', avatar_url: '/team.png' }

    await teamsApi.createTeam(input)

    expect(post).toHaveBeenCalledTimes(1)
    expect(post).toHaveBeenCalledWith('/admin/teams', input)
  })

  it('updates through the platform team endpoint with the exact payload', async () => {
    const put = spyOn(api, 'put').mockResolvedValue({})
    const input = { name: 'Renamed' }

    await teamsApi.updateTeam('team-42', input)

    expect(put).toHaveBeenCalledTimes(1)
    expect(put).toHaveBeenCalledWith('/teams/team-42', input)
  })

  it('deletes the exact admin team resource', async () => {
    const deleteRequest = spyOn(api, 'delete').mockResolvedValue({})

    await teamsApi.deleteTeam('team-42')

    expect(deleteRequest).toHaveBeenCalledTimes(1)
    expect(deleteRequest).toHaveBeenCalledWith('/admin/teams/team-42')
  })

  it('preserves a meaningful request failure', async () => {
    const failure = new Error('team list request failed')
    spyOn(api, 'get').mockRejectedValue(failure)

    expect(teamsApi.getTeams()).rejects.toBe(failure)
  })
})
