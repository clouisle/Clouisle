'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { Check, ChevronsUpDown, Users } from 'lucide-react'
import { useTeam } from '@/contexts/team-context'

import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'

export function TeamSwitcher() {
  const t = useTranslations('platform')
  const { teams, currentTeam, isLoading, setCurrentTeam } = useTeam()

  // 获取团队名称首字母
  const getInitials = (name: string) => {
    return name
      .split(' ')
      .map((n) => n[0])
      .join('')
      .toUpperCase()
      .slice(0, 2)
  }

  if (isLoading) {
    return (
      <Button variant="ghost" size="sm" className="gap-2 h-8 px-2" disabled>
        <div className="h-5 w-5 rounded bg-muted animate-pulse" />
        <span className="text-muted-foreground">...</span>
      </Button>
    )
  }

  if (!currentTeam) {
    return null
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={(props) => (
          <Button {...props} variant="ghost" size="sm" className="gap-2 h-8 px-2 cursor-pointer">
            <Avatar className="h-6 w-6 rounded">
              <AvatarImage src={currentTeam.avatar_url || undefined} alt={currentTeam.name} />
              <AvatarFallback className="rounded text-xs">
                {getInitials(currentTeam.name)}
              </AvatarFallback>
            </Avatar>
            <span className="max-w-30 truncate font-medium hidden sm:inline">
              {currentTeam.name}
            </span>
            <ChevronsUpDown className="h-3.5 w-3.5 opacity-50" />
          </Button>
        )}
      />
      <DropdownMenuContent align="start" className="w-[220px]">
        <div className="px-2 py-1.5 text-xs font-medium text-muted-foreground">
          {t('teams')}
        </div>
        {teams.map((team) => (
          <DropdownMenuItem
            key={team.id}
            onClick={() => setCurrentTeam(team)}
            className="gap-2 cursor-pointer"
          >
            <Avatar className="h-5 w-5 rounded">
              <AvatarImage src={team.avatar_url || undefined} alt={team.name} />
              <AvatarFallback className="rounded text-[10px]">
                {getInitials(team.name)}
              </AvatarFallback>
            </Avatar>
            <span className="flex-1 truncate">{team.name}</span>
            {team.id === currentTeam.id && (
              <Check className="h-4 w-4 text-primary" />
            )}
          </DropdownMenuItem>
        ))}
        <DropdownMenuSeparator />
        <a href="/teams">
          <DropdownMenuItem className="gap-2 cursor-pointer">
            <Users className="h-4 w-4" />
            {t('manageTeams')}
          </DropdownMenuItem>
        </a>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
