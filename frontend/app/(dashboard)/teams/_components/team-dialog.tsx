'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { toast } from 'sonner'
import { teamsApi, type Team } from '@/lib/api/admin'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { ImageUpload } from '@/components/ui/image-upload'

interface TeamDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  team?: Team | null
  onSuccess?: () => void
}

export function TeamDialog({
  open,
  onOpenChange,
  team,
  onSuccess,
}: TeamDialogProps) {
  const t = useTranslations('teams')
  const commonT = useTranslations('common')
  const isEditing = !!team

  const [name, setName] = React.useState('')
  const [description, setDescription] = React.useState('')
  const [avatarUrl, setAvatarUrl] = React.useState('')
  const [isLoading, setIsLoading] = React.useState(false)

  // 重置表单
  React.useEffect(() => {
    if (open) {
      if (team) {
        setName(team.name)
        setDescription(team.description || '')
        setAvatarUrl(team.avatar_url || '')
      } else {
        setName('')
        setDescription('')
        setAvatarUrl('')
      }
    }
  }, [open, team])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!name.trim()) return

    setIsLoading(true)
    try {
      const payload = {
        name: name.trim(),
        description: description.trim() || undefined,
        avatar_url: avatarUrl.trim() || undefined,
      }

      if (isEditing) {
        await teamsApi.updateTeam(team.id, payload)
        toast.success(t('teamUpdated'))
      } else {
        await teamsApi.createTeam(payload)
        toast.success(t('teamCreated'))
      }

      onOpenChange(false)
      onSuccess?.()
    } catch {
      // 错误已由 API 客户端处理
    } finally {
      setIsLoading(false)
    }
  }

  const getTeamInitials = (teamName: string) => {
    if (!teamName) return '?'
    return teamName.slice(0, 2).toUpperCase()
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>
            {isEditing ? t('editTeam') : t('createTeam')}
          </DialogTitle>
          <DialogDescription>
            {isEditing ? t('editTeamDescription') : t('createTeamDescription')}
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* 头像上传 */}
          <div className="flex flex-col items-center gap-2">
            <Label>{t('avatar')}</Label>
            <ImageUpload
              value={avatarUrl}
              onChange={setAvatarUrl}
              previewSize="lg"
              category="avatars"
              placeholder={
                <span className="text-xl font-semibold text-muted-foreground">
                  {getTeamInitials(name)}
                </span>
              }
            />
            <p className="text-xs text-muted-foreground">{t('avatarHint')}</p>
          </div>

          <div className="space-y-2">
            <Label htmlFor="name">{t('teamName')} *</Label>
            <Input
              id="name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={t('teamNamePlaceholder')}
              required
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="description">{t('teamDescription')}</Label>
            <Textarea
              id="description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder={t('teamDescriptionPlaceholder')}
              className="resize-none"
              rows={3}
            />
          </div>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={isLoading}
            >
              {commonT('cancel')}
            </Button>
            <Button type="submit" disabled={isLoading || !name.trim()}>
              {isLoading ? commonT('loading') : commonT('save')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
