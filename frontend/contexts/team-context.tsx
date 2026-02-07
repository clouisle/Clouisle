'use client'

import * as React from 'react'
import { teamsApi, type UserTeamInfo } from '@/lib/api'

interface TeamContextType {
  teams: UserTeamInfo[]
  currentTeam: UserTeamInfo | null
  isLoading: boolean
  setCurrentTeam: (team: UserTeamInfo) => void
  refreshTeams: () => Promise<void>
}

const TeamContext = React.createContext<TeamContextType | undefined>(undefined)

const STORAGE_KEY = 'clouisle-current-team-id'

export function TeamProvider({ children }: { children: React.ReactNode }) {
  const [teams, setTeams] = React.useState<UserTeamInfo[]>([])
  const [currentTeam, setCurrentTeamState] = React.useState<UserTeamInfo | null>(null)
  const [isLoading, setIsLoading] = React.useState(true)

  const fetchTeams = React.useCallback(async () => {
    try {
      setIsLoading(true)
      const data = await teamsApi.getMyTeams({ skipAuthRedirect: true })
      setTeams(data)

      // 从 localStorage 恢复选中的团队
      const savedTeamId = localStorage.getItem(STORAGE_KEY)
      const savedTeam = data.find(t => t.id === savedTeamId)
      
      if (savedTeam) {
        setCurrentTeamState(savedTeam)
      } else if (data.length > 0) {
        // 默认选中第一个团队
        setCurrentTeamState(data[0])
        localStorage.setItem(STORAGE_KEY, data[0].id)
      }
    } catch (error) {
      console.error('Failed to fetch teams:', error)
    } finally {
      setIsLoading(false)
    }
  }, [])

  React.useEffect(() => {
    fetchTeams()
  }, [fetchTeams])

  const setCurrentTeam = React.useCallback((team: UserTeamInfo) => {
    setCurrentTeamState(team)
    localStorage.setItem(STORAGE_KEY, team.id)
  }, [])

  const value = React.useMemo(
    () => ({
      teams,
      currentTeam,
      isLoading,
      setCurrentTeam,
      refreshTeams: fetchTeams,
    }),
    [teams, currentTeam, isLoading, setCurrentTeam, fetchTeams]
  )

  return (
    <TeamContext.Provider value={value}>
      {children}
    </TeamContext.Provider>
  )
}

export function useTeam() {
  const context = React.useContext(TeamContext)
  if (context === undefined) {
    throw new Error('useTeam must be used within a TeamProvider')
  }
  return context
}
