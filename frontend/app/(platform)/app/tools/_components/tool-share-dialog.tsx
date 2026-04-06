'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { Loader2, Share2, Trash2, Users } from 'lucide-react'
import { toast } from 'sonner'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { toolsApi, type Tool, type ToolShare, type ToolSharePermission, type UserTeamInfo } from '@/lib/api'

interface ToolShareDialogProps {
  tool: Tool | null
  open: boolean
  onOpenChange: (open: boolean) => void
  currentTeamId: string
  availableTeams: UserTeamInfo[]
  onSuccess?: () => void
}

export function ToolShareDialog({
  tool,
  open,
  onOpenChange,
  currentTeamId,
  availableTeams,
  onSuccess,
}: ToolShareDialogProps) {
  const t = useTranslations('platform.tools.share')
  const tCommon = useTranslations('common')

  const [shares, setShares] = React.useState<ToolShare[]>([])
  const [isLoading, setIsLoading] = React.useState(false)
  const [isSharing, setIsSharing] = React.useState(false)
  const [selectedTeamId, setSelectedTeamId] = React.useState<string>('')
  const [selectedPermission, setSelectedPermission] = React.useState<ToolSharePermission>('read_only')
  const [deleteDialogOpen, setDeleteDialogOpen] = React.useState(false)
  const [deletingShare, setDeletingShare] = React.useState<ToolShare | null>(null)

  // 加载共享列表
  const loadShares = React.useCallback(async () => {
    if (!tool?.id) return

    setIsLoading(true)
    try {
      const response = await toolsApi.listToolShares(tool.id)
      setShares(response.shares)
    } catch (error) {
      console.error('Failed to load shares:', error)
    } finally {
      setIsLoading(false)
    }
  }, [tool?.id])

  React.useEffect(() => {
    if (open && tool?.id) {
      loadShares()
      setSelectedTeamId('')
      setSelectedPermission('read_only')
    }
  }, [open, tool?.id, loadShares])

  // 获取可共享的团队列表（排除当前团队和已共享的团队）
  const availableTeamsToShare = React.useMemo(() => {
    const sharedTeamIds = new Set(shares.map(s => s.shared_with_team_id))
    return availableTeams.filter(
      team => team.id !== currentTeamId && !sharedTeamIds.has(team.id)
    )
  }, [availableTeams, currentTeamId, shares])

  // 共享工具
  const handleShare = async () => {
    if (!tool?.id || !selectedTeamId) return

    setIsSharing(true)
    try {
      await toolsApi.shareTool(tool.id, {
        team_id: selectedTeamId,
        permission: selectedPermission,
      })
      toast.success(t('shareSuccess'))
      await loadShares()
      setSelectedTeamId('')
      setSelectedPermission('read_only')
      onSuccess?.()
    } catch (error) {
      console.error('Failed to share tool:', error)
    } finally {
      setIsSharing(false)
    }
  }

  // 打开删除确认对话框
  const handleDeleteClick = (share: ToolShare) => {
    setDeletingShare(share)
    setDeleteDialogOpen(true)
  }

  // 取消共享
  const handleUnshare = async () => {
    if (!tool?.id || !deletingShare) return

    try {
      await toolsApi.unshareTool(tool.id, deletingShare.shared_with_team_id)
      toast.success(t('unshareSuccess'))
      await loadShares()
      onSuccess?.()
    } catch (error) {
      console.error('Failed to unshare tool:', error)
    } finally {
      setDeleteDialogOpen(false)
      setDeletingShare(null)
    }
  }

  if (!tool) return null

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Share2 className="h-5 w-5" />
              {t('title')}
            </DialogTitle>
            <DialogDescription>
              {t('description', { toolName: tool.display_name })}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-6 py-4">
            {/* 共享表单 */}
            {availableTeamsToShare.length > 0 && (
              <div className="space-y-4 pb-4 border-b">
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-2">
                    <Label>{t('selectTeam')}</Label>
                    <Select
                      value={selectedTeamId || undefined}
                      onValueChange={(v) => v && setSelectedTeamId(v)}
                    >
                      <SelectTrigger className="w-full">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent alignItemWithTrigger={false}>
                        {availableTeamsToShare.map((team) => (
                          <SelectItem key={team.id} value={team.id}>
                            {team.name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="space-y-2">
                    <Label>{t('permission')}</Label>
                    <Select
                      value={selectedPermission}
                      onValueChange={(v) => setSelectedPermission(v as ToolSharePermission)}
                    >
                      <SelectTrigger className="w-full">
                        <SelectValue>
                          {selectedPermission === 'read_only'
                            ? t('permissions.readOnly')
                            : t('permissions.readExecute')}
                        </SelectValue>
                      </SelectTrigger>
                      <SelectContent alignItemWithTrigger={false}>
                        <SelectItem value="read_only">
                          {t('permissions.readOnly')}
                        </SelectItem>
                        <SelectItem value="read_execute">
                          {t('permissions.readExecute')}
                        </SelectItem>
                      </SelectContent>
                    </Select>
                    <p className="text-xs text-muted-foreground">
                      {selectedPermission === 'read_only'
                        ? t('permissions.readOnlyDesc')
                        : t('permissions.readExecuteDesc')}
                    </p>
                  </div>
                </div>

                <Button
                  onClick={handleShare}
                  disabled={!selectedTeamId || isSharing}
                  className="w-full"
                >
                  {isSharing && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                  <Share2 className="mr-2 h-4 w-4" />
                  {t('shareButton')}
                </Button>
              </div>
            )}

            {/* 已共享列表 */}
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <Label className="text-base">{t('sharedWith')}</Label>
                <Badge variant="secondary">{shares.length}</Badge>
              </div>

              {isLoading ? (
                <div className="flex items-center justify-center py-8">
                  <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                </div>
              ) : shares.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-8 text-center">
                  <Users className="h-12 w-12 text-muted-foreground/50 mb-3" />
                  <p className="text-sm text-muted-foreground">
                    {t('noShares')}
                  </p>
                </div>
              ) : (
                <ScrollArea className="h-[200px]">
                  <div className="space-y-2">
                    {shares.map((share) => (
                      <div
                        key={share.id}
                        className="flex items-center justify-between p-3 rounded-lg border bg-card"
                      >
                        <div className="flex-1 min-w-0">
                          <p className="font-medium truncate">
                            {share.shared_with_team_name}
                          </p>
                          <div className="flex items-center gap-2 mt-1">
                            <Badge variant="outline" className="text-xs">
                              {share.permission === 'read_only'
                                ? t('permissions.readOnly')
                                : t('permissions.readExecute')}
                            </Badge>
                            <span className="text-xs text-muted-foreground">
                              {t('sharedBy', { name: share.shared_by_name })}
                            </span>
                          </div>
                        </div>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="shrink-0 text-destructive hover:text-destructive hover:bg-destructive/10"
                          onClick={() => handleDeleteClick(share)}
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    ))}
                  </div>
                </ScrollArea>
              )}
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => onOpenChange(false)}>
              {tCommon('close')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* 删除确认对话框 */}
      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('confirmUnshare')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('confirmUnshareDesc', {
                teamName: deletingShare?.shared_with_team_name || '',
              })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{tCommon('cancel')}</AlertDialogCancel>
            <AlertDialogAction variant="destructive" onClick={handleUnshare}>
              {t('unshareButton')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}
