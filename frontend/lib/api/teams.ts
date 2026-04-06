import { api } from './client'

export interface TeamOwner {
  id: string
  username: string
  email: string
  avatar_url: string | null
}

export interface Team {
  id: string
  name: string
  description: string | null
  avatar_url: string | null
  is_default: boolean
  owner: TeamOwner | null
  created_at: string
  updated_at: string
}

export interface TeamMember {
  id: string
  user_id: string
  username: string
  email: string
  avatar_url: string | null
  role: 'owner' | 'admin' | 'member' | 'viewer'
  joined_at: string
}

export interface TeamWithMembers extends Team {
  members: TeamMember[]
}

export interface UserTeamInfo {
  id: string
  name: string
  description: string | null
  avatar_url: string | null
  role: 'owner' | 'admin' | 'member' | 'viewer'
  joined_at: string
}

export interface TeamCreateInput {
  name: string
  description?: string
  avatar_url?: string
}

export interface TeamUpdateInput {
  name?: string
  description?: string
  avatar_url?: string
}

export interface TeamMemberAddInput {
  user_id: string
  role?: 'admin' | 'member' | 'viewer'
}

export interface TeamMemberUpdateInput {
  role: 'admin' | 'member' | 'viewer'
}

export const teamsApi = {
  /**
   * 获取当前用户的团队
   */
  getMyTeams: async (options?: { skipAuthRedirect?: boolean }): Promise<UserTeamInfo[]> => {
    return api.get<UserTeamInfo[]>('/teams/my', { skipAuthRedirect: options?.skipAuthRedirect })
  },

  /**
   * 获取单个团队（含成员列表）
   */
  getTeam: async (id: string): Promise<TeamWithMembers> => {
    return api.get<TeamWithMembers>(`/teams/${id}`)
  },

  /**
   * 更新团队
   */
  updateTeam: async (id: string, data: TeamUpdateInput): Promise<Team> => {
    return api.put<Team>(`/teams/${id}`, data)
  },

  /**
   * 添加团队成员
   */
  addMember: async (teamId: string, data: TeamMemberAddInput): Promise<TeamMember> => {
    return api.post<TeamMember>(`/teams/${teamId}/members`, data)
  },

  /**
   * 更新成员角色
   */
  updateMember: async (teamId: string, userId: string, data: TeamMemberUpdateInput): Promise<TeamMember> => {
    return api.put<TeamMember>(`/teams/${teamId}/members/${userId}`, data)
  },

  /**
   * 移除团队成员
   */
  removeMember: async (teamId: string, userId: string): Promise<{ user_id: string }> => {
    return api.delete<{ user_id: string }>(`/teams/${teamId}/members/${userId}`)
  },

  /**
   * 离开团队
   */
  leaveTeam: async (teamId: string): Promise<{ team_id: string }> => {
    return api.post<{ team_id: string }>(`/teams/${teamId}/leave`, {})
  },

  /**
   * 转让团队所有权
   */
  transferOwnership: async (teamId: string, newOwnerId: string): Promise<Team> => {
    return api.post<Team>(`/teams/${teamId}/transfer-ownership?new_owner_id=${newOwnerId}`, {})
  },
}
