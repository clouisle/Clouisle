import { api } from '../client'
import type { PageData } from '../users'
import type { Team, TeamCreateInput, TeamUpdateInput } from '../teams'

export const teamsApi = {
  /**
   * 获取所有团队（管理员）
   */
  getTeams: async (page: number = 1, pageSize: number = 50): Promise<PageData<Team>> => {
    return api.get<PageData<Team>>(`/admin/teams?page=${page}&page_size=${pageSize}`)
  },

  /**
   * 创建团队（管理员）
   */
  createTeam: async (data: TeamCreateInput): Promise<Team> => {
    return api.post<Team>('/admin/teams', data)
  },

  /**
   * 更新团队（管理员）
   * 注意：管理员更新团队使用平台侧接口，因为 admin 侧没有提供 update 接口
   */
  updateTeam: async (id: string, data: TeamUpdateInput): Promise<Team> => {
    return api.put<Team>(`/teams/${id}`, data)
  },

  /**
   * 删除团队（管理员）
   */
  deleteTeam: async (id: string): Promise<Team> => {
    return api.delete<Team>(`/admin/teams/${id}`)
  },
}
