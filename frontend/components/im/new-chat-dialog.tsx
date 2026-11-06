'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { Search, UserPlus } from 'lucide-react'
import { imApi, type ImTeamChatCandidate } from '@/lib/api'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { Skeleton } from '@/components/ui/skeleton'

interface NewChatDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  teamId: string
  onSelectUser: (userId: string) => void
}

export function NewChatDialog({ open, onOpenChange, teamId, onSelectUser }: NewChatDialogProps) {
  const t = useTranslations('notifications.im')
  const [candidates, setCandidates] = React.useState<ImTeamChatCandidate[]>([])
  const [loading, setLoading] = React.useState(false)
  const [search, setSearch] = React.useState('')

  React.useEffect(() => {
    if (!open || !teamId) return
    let active = true
    setLoading(true)
    // 换团队/重新打开时立刻清空上一轮候选，避免请求中或失败后残留旧成员
    setCandidates([])
    imApi
      .listTeamCandidates(teamId)
      .then((data) => {
        if (active) setCandidates(data)
      })
      .catch((err) => {
        console.error('Failed to load team candidates:', err)
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [open, teamId])

  const filtered = candidates.filter((c) => {
    const q = search.trim().toLowerCase()
    if (!q) return true
    return (
      c.username.toLowerCase().includes(q) ||
      (c.full_name && c.full_name.toLowerCase().includes(q))
    )
  })

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md p-6">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-lg font-semibold">
            <UserPlus className="size-5" />
            {t('newChatTitle')}
          </DialogTitle>
        </DialogHeader>

        <div className="relative mt-2">
          <Search className="text-muted-foreground pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={t('searchCandidatesPlaceholder')}
            className="pl-9"
          />
        </div>

        <div className="mt-4 max-h-[300px] overflow-y-auto space-y-1">
          {loading ? (
            <div className="space-y-3 py-2">
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
            </div>
          ) : filtered.length === 0 ? (
            <div className="text-muted-foreground py-8 text-center text-sm">
              {t('noCandidatesFound')}
            </div>
          ) : (
            filtered.map((user) => (
              <Button
                key={user.id}
                variant="ghost"
                className="w-full justify-start h-auto py-2 px-3 gap-3"
                onClick={() => {
                  onSelectUser(user.id)
                  onOpenChange(false)
                }}
              >
                <Avatar className="size-8">
                  {user.avatar_url && <AvatarImage src={user.avatar_url} />}
                  <AvatarFallback>
                    {(user.full_name || user.username).slice(0, 2).toUpperCase()}
                  </AvatarFallback>
                </Avatar>
                <div className="flex flex-col text-left overflow-hidden">
                  <span className="font-medium text-sm truncate">
                    {user.full_name || user.username}
                  </span>
                  <span className="text-muted-foreground text-xs truncate">
                    @{user.username}
                  </span>
                </div>
              </Button>
            ))
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}
