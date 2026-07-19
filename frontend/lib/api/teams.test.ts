import { afterEach, describe, expect, it, mock, spyOn } from 'bun:test'
import { api } from './client'
import { teamsApi } from './teams'

afterEach(() => {
  mock.restore()
})

describe('teamsApi', () => {
  it('gets current teams with the default and requested auth redirect options', async () => {
    const get = spyOn(api, 'get').mockResolvedValue([])

    await teamsApi.getMyTeams()
    await teamsApi.getMyTeams({ skipAuthRedirect: true })

    expect(get).toHaveBeenNthCalledWith(1, '/teams/my', { skipAuthRedirect: undefined })
    expect(get).toHaveBeenNthCalledWith(2, '/teams/my', { skipAuthRedirect: true })
  })

  it('gets a team by ID', async () => {
    const get = spyOn(api, 'get').mockResolvedValue({})

    await teamsApi.getTeam('team-1')

    expect(get).toHaveBeenCalledWith('/teams/team-1')
  })

  it('updates a team with its payload', async () => {
    const put = spyOn(api, 'put').mockResolvedValue({})
    const payload = { name: 'Renamed team', description: 'Updated description' }

    await teamsApi.updateTeam('team-1', payload)

    expect(put).toHaveBeenCalledWith('/teams/team-1', payload)
  })

  it('adds and updates members with their payloads', async () => {
    const post = spyOn(api, 'post').mockResolvedValue({})
    const put = spyOn(api, 'put').mockResolvedValue({})
    const addPayload = { user_id: 'user-1', role: 'admin' as const }
    const updatePayload = { role: 'viewer' as const }

    await teamsApi.addMember('team-1', addPayload)
    await teamsApi.updateMember('team-1', 'user-1', updatePayload)

    expect(post).toHaveBeenCalledWith('/teams/team-1/members', addPayload)
    expect(put).toHaveBeenCalledWith('/teams/team-1/members/user-1', updatePayload)
  })

  it('removes a member by its team and user IDs', async () => {
    const remove = spyOn(api, 'delete').mockResolvedValue({ user_id: 'user-1' })

    await teamsApi.removeMember('team-1', 'user-1')

    expect(remove).toHaveBeenCalledWith('/teams/team-1/members/user-1')
  })

  it('uses empty payloads for leaving and transferring ownership', async () => {
    const post = spyOn(api, 'post').mockResolvedValue({})

    await teamsApi.leaveTeam('team-1')
    await teamsApi.transferOwnership('team-1', 'user-2')

    expect(post).toHaveBeenNthCalledWith(1, '/teams/team-1/leave', {})
    expect(post).toHaveBeenNthCalledWith(2, '/teams/team-1/transfer-ownership?new_owner_id=user-2', {})
  })
})
