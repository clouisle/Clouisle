'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { toast } from 'sonner'
import {
  Crown,
  Shield,
  User,
  Eye,
  MoreHorizontal,
  Pencil,
  Trash2,
  UserPlus,
  LogOut,
  ArrowRightLeft,
  Search,
  Check,
  Users,
  Cpu,
} from 'lucide-react'
import { teamsApi as platformTeamsApi, type TeamWithMembers, type TeamMember } from '@/lib/api'
import { teamsApi as adminTeamsApi } from '@/lib/api/admin'
import { usersApi, type User as UserType } from '@/lib/api/admin/users'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
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
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Separator } from '@/components/ui/separator'
import { Skeleton } from '@/components/ui/skeleton'
import { TeamModelsTab } from './team-models-tab'
import { PermissionGuard, useCanPerform } from '@/components/permission-guard'

type TeamRole = 'owner' | 'admin' | 'member' | 'viewer'
type AddableRole = 'admin' | 'member' | 'viewer'

interface TeamDetailDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  teamId: string | null
  onEdit?: () => void
  onDeleted?: () => void
}

// 角色图标
const RoleIcon = ({ role }: { role: TeamRole }) => {
  switch (role) {
    case 'owner':
      return <Crown className="h-4 w-4 text-yellow-500" />
    case 'admin':
      return <Shield className="h-4 w-4 text-blue-500" />
    case 'member':
      return <User className="h-4 w-4 text-green-500" />
    case 'viewer':
      return <Eye className="h-4 w-4 text-gray-500" />
  }
}

export function TeamDetailDialog({
  open,
  onOpenChange,
  teamId,
  onEdit,
  onDeleted,
}: TeamDetailDialogProps) {
  const t = useTranslations('teams')
  const commonT = useTranslations('common')
  const { canPerform } = useCanPerform()
  const canManageTeam = canPerform('team:manage')
  
  // 数据状态
  const [team, setTeam] = React.useState<TeamWithMembers | null>(null)
  const [isLoading, setIsLoading] = React.useState(true)
  const [users, setUsers] = React.useState<UserType[]>([])
  
  // Dialog 状态
  const [addMemberOpen, setAddMemberOpen] = React.useState(false)
  const [selectedUserId, setSelectedUserId] = React.useState<string | null>(null)
  const [selectedRole, setSelectedRole] = React.useState<AddableRole>('member')
  const [isAddingMember, setIsAddingMember] = React.useState(false)
  const [userSearch, setUserSearch] = React.useState('')
  
  const [removeMemberDialogOpen, setRemoveMemberDialogOpen] = React.useState(false)
  const [memberToRemove, setMemberToRemove] = React.useState<TeamMember | null>(null)
  
  const [changeRoleDialogOpen, setChangeRoleDialogOpen] = React.useState(false)
  const [memberToChangeRole, setMemberToChangeRole] = React.useState<TeamMember | null>(null)
  const [newRole, setNewRole] = React.useState<AddableRole>('member')
  
  const [transferDialogOpen, setTransferDialogOpen] = React.useState(false)
  const [transferToMember, setTransferToMember] = React.useState<TeamMember | null>(null)
  
  const [leaveDialogOpen, setLeaveDialogOpen] = React.useState(false)
  const [deleteDialogOpen, setDeleteDialogOpen] = React.useState(false)

  // 加载团队详情
  const loadTeam = React.useCallback(async () => {
    if (!teamId) return
    setIsLoading(true)
    try {
      const data = await platformTeamsApi.getTeam(teamId)
      setTeam(data)
    } catch {
      // 错误已由 API 客户端处理
    } finally {
      setIsLoading(false)
    }
  }, [teamId])
  
  // 加载用户列表（用于添加成员）
  const loadUsers = React.useCallback(async () => {
    try {
      const data = await usersApi.getUsers({ page: 1, pageSize: 100 })
      setUsers(data.items)
    } catch {
      // 错误已由 API 客户端处理
    }
  }, [])
  
  React.useEffect(() => {
    if (open && teamId) {
      loadTeam()
      loadUsers()
    }
  }, [open, teamId, loadTeam, loadUsers])
  
  // 获取用户首字母
  const getUserInitials = (username: string) => {
    return username.slice(0, 2).toUpperCase()
  }
  
  // 获取团队首字母
  const getTeamInitials = (name: string) => {
    return name.slice(0, 2).toUpperCase()
  }
  
  // 可添加的用户（排除已是成员的用户）
  const availableUsers = React.useMemo(() => {
    if (!team) return users
    const memberIds = new Set(team.members.map(m => m.user_id))
    return users.filter(u => !memberIds.has(u.id))
  }, [users, team])
  
  // 过滤用户
  const filteredUsers = React.useMemo(() => {
    if (!userSearch) return availableUsers
    const query = userSearch.toLowerCase()
    return availableUsers.filter(u => 
      u.username.toLowerCase().includes(query) ||
      u.email.toLowerCase().includes(query)
    )
  }, [availableUsers, userSearch])
  
  // 添加成员
  const handleAddMember = async () => {
    if (!teamId || !selectedUserId) return
    setIsAddingMember(true)
    try {
      await platformTeamsApi.addMember(teamId, { user_id: selectedUserId, role: selectedRole })
      toast.success(t('memberAdded'))
      setAddMemberOpen(false)
      setSelectedUserId(null)
      setSelectedRole('member')
      setUserSearch('')
      loadTeam()
    } catch {
      // 错误已由 API 客户端处理
    } finally {
      setIsAddingMember(false)
    }
  }
  
  // 移除成员
  const handleRemoveMember = async () => {
    if (!teamId || !memberToRemove) return
    try {
      await platformTeamsApi.removeMember(teamId, memberToRemove.user_id)
      toast.success(t('memberRemoved'))
      setRemoveMemberDialogOpen(false)
      setMemberToRemove(null)
      loadTeam()
    } catch {
      // 错误已由 API 客户端处理
    }
  }
  
  // 修改成员角色
  const handleChangeRole = async () => {
    if (!teamId || !memberToChangeRole) return
    try {
      await platformTeamsApi.updateMember(teamId, memberToChangeRole.user_id, { role: newRole })
      toast.success(t('roleUpdated'))
      setChangeRoleDialogOpen(false)
      setMemberToChangeRole(null)
      loadTeam()
    } catch {
      // 错误已由 API 客户端处理
    }
  }
  
  // 转移所有权
  const handleTransferOwnership = async () => {
    if (!teamId || !transferToMember) return
    try {
      await platformTeamsApi.transferOwnership(teamId, transferToMember.user_id)
      toast.success(t('ownershipTransferred'))
      setTransferDialogOpen(false)
      setTransferToMember(null)
      loadTeam()
    } catch {
      // 错误已由 API 客户端处理
    }
  }
  
  // 离开团队
  const handleLeaveTeam = async () => {
    if (!teamId) return
    try {
      await platformTeamsApi.leaveTeam(teamId)
      toast.success(t('leftTeam'))
      setLeaveDialogOpen(false)
      onOpenChange(false)
      onDeleted?.()
    } catch {
      // 错误已由 API 客户端处理
    }
  }
  
  // 删除团队
  const handleDeleteTeam = async () => {
    if (!teamId) return
    try {
      await adminTeamsApi.deleteTeam(teamId)
      toast.success(t('teamDeleted'))
      setDeleteDialogOpen(false)
      onOpenChange(false)
      onDeleted?.()
    } catch {
      // 错误已由 API 客户端处理
    }
  }
  
  // 打开修改角色对话框
  const openChangeRoleDialog = (member: TeamMember) => {
    setMemberToChangeRole(member)
    setNewRole(member.role === 'owner' ? 'admin' : member.role as AddableRole)
    setChangeRoleDialogOpen(true)
  }
  
  // 打开转移所有权对话框
  const openTransferDialog = (member: TeamMember) => {
    setTransferToMember(member)
    setTransferDialogOpen(true)
  }
  
  // 打开移除成员对话框
  const openRemoveMemberDialog = (member: TeamMember) => {
    setMemberToRemove(member)
    setRemoveMemberDialogOpen(true)
  }
  
  const roles: AddableRole[] = ['admin', 'member', 'viewer']

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="sm:max-w-3xl max-h-[90vh]">
          {isLoading ? (
            <div className="space-y-4 py-4">
              <div className="flex items-center gap-4">
                <Skeleton className="h-16 w-16 rounded-full" />
                <div className="space-y-2">
                  <Skeleton className="h-6 w-32" />
                  <Skeleton className="h-4 w-48" />
                </div>
              </div>
              <Skeleton className="h-40 w-full" />
            </div>
          ) : team ? (
            <>
              <DialogHeader>
                <div className="flex items-start gap-4">
                  <Avatar className="h-16 w-16">
                    <AvatarImage src={team.avatar_url || undefined} />
                    <AvatarFallback className="text-xl bg-primary text-primary-foreground">
                      {getTeamInitials(team.name)}
                    </AvatarFallback>
                  </Avatar>
                  <div className="flex-1">
                    <DialogTitle className="text-xl flex items-center gap-2">
                      {team.name}
                      {team.is_default && (
                        <Badge variant="secondary">{t('defaultTeam')}</Badge>
                      )}
                    </DialogTitle>
                    <DialogDescription className="mt-1">
                      {team.description || t('noDescription')}
                    </DialogDescription>
                  </div>
                </div>
              </DialogHeader>
              
              <Tabs defaultValue="members" className="w-full">
                {canManageTeam ? (
                  <TabsList className="grid w-full grid-cols-2">
                    <TabsTrigger value="members" className="flex items-center gap-2">
                      <Users className="h-4 w-4" />
                      {t('members')}
                    </TabsTrigger>
                    <TabsTrigger value="models" className="flex items-center gap-2">
                      <Cpu className="h-4 w-4" />
                      {t('modelAuth')}
                    </TabsTrigger>
                  </TabsList>
                ) : (
                  <TabsList className="grid w-full grid-cols-1">
                    <TabsTrigger value="members" className="flex items-center gap-2">
                      <Users className="h-4 w-4" />
                      {t('members')}
                    </TabsTrigger>
                  </TabsList>
                )}
                
                <TabsContent value="members" className="mt-4 space-y-4">
                  {/* 成员列表 */}
                  <div>
                    <div className="flex items-center justify-between mb-3">
                      <h3 className="font-medium">{t('members')} ({team.members.length})</h3>
                      <PermissionGuard permission="team:manage">
                        <Popover open={addMemberOpen} onOpenChange={setAddMemberOpen}>
                          <PopoverTrigger
                            render={
                              <Button variant="outline" size="sm">
                                <UserPlus className="mr-2 h-4 w-4" />
                                {t('addMember')}
                              </Button>
                            }
                          />
                          <PopoverContent className="w-80 p-0" align="end">
                            <div className="p-3 border-b">
                              <div className="relative">
                                <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                                <Input
                                  placeholder={t('searchUsers')}
                                  value={userSearch}
                                  onChange={(e) => setUserSearch(e.target.value)}
                                  className="pl-8"
                                />
                              </div>
                            </div>
                            <ScrollArea className="h-48">
                              {filteredUsers.length === 0 ? (
                                <div className="p-4 text-center text-muted-foreground text-sm">
                                  {t('noUsersFound')}
                                </div>
                              ) : (
                                <div className="p-2">
                                  {filteredUsers.map((user) => (
                                    <button
                                      key={user.id}
                                      type="button"
                                      className="w-full flex items-center gap-2 px-2 py-1.5 rounded hover:bg-accent text-left"
                                      onClick={() => setSelectedUserId(user.id)}
                                    >
                                      <Avatar className="h-6 w-6">
                                        <AvatarImage src={user.avatar_url || undefined} />
                                        <AvatarFallback className="text-xs">
                                          {getUserInitials(user.username)}
                                        </AvatarFallback>
                                      </Avatar>
                                      <span className="text-sm flex-1">{user.username}</span>
                                      {selectedUserId === user.id && (
                                        <Check className="h-4 w-4 text-primary" />
                                      )}
                                    </button>
                                  ))}
                                </div>
                              )}
                            </ScrollArea>
                            {selectedUserId && (
                              <div className="border-t p-3 space-y-3">
                                <div className="flex items-center gap-2">
                                  <span className="text-sm">{t('role')}:</span>
                                  <Select value={selectedRole} onValueChange={(v) => setSelectedRole(v as AddableRole)}>
                                    <SelectTrigger size="sm" className="flex-1">
                                      <SelectValue>
                                        <div className="flex items-center gap-2">
                                          <RoleIcon role={selectedRole} />
                                          <span>{t(`roles.${selectedRole}`)}</span>
                                        </div>
                                      </SelectValue>
                                    </SelectTrigger>
                                    <SelectContent side="top" alignItemWithTrigger={false}>
                                      {roles.map((role) => (
                                        <SelectItem key={role} value={role}>
                                          <div className="flex items-center gap-2">
                                            <RoleIcon role={role} />
                                            <span>{t(`roles.${role}`)}</span>
                                          </div>
                                        </SelectItem>
                                      ))}
                                    </SelectContent>
                                  </Select>
                                </div>
                                <Button
                                  className="w-full"
                                  size="sm"
                                  disabled={isAddingMember}
                                  onClick={handleAddMember}
                                >
                                  {isAddingMember ? commonT('loading') : t('addMember')}
                                </Button>
                              </div>
                            )}
                          </PopoverContent>
                        </Popover>
                      </PermissionGuard>
                    </div>
                  
                  <ScrollArea className="h-64">
                    <div className="space-y-2">
                      {team.members.map((member) => (
                        <div
                          key={member.user_id}
                          className="flex items-center justify-between p-2 rounded-md hover:bg-accent"
                        >
                          <div className="flex items-center gap-3">
                            <Avatar className="h-8 w-8">
                              <AvatarImage src={member.avatar_url || undefined} />
                              <AvatarFallback className="text-xs">
                                {getUserInitials(member.username)}
                              </AvatarFallback>
                            </Avatar>
                            <div>
                              <div className="text-sm font-medium">
                                {member.username}
                              </div>
                              <div className="text-xs text-muted-foreground">
                                {member.email}
                              </div>
                            </div>
                          </div>
                          <div className="flex items-center gap-2">
                            <Badge variant="outline" className="flex items-center gap-1">
                              <RoleIcon role={member.role} />
                              <span>{t(`roles.${member.role}`)}</span>
                            </Badge>

                            {member.role !== 'owner' && canPerform('team:manage') && (
                              <DropdownMenu>
                                <DropdownMenuTrigger
                                  render={
                                    <Button variant="ghost" size="icon" className="h-8 w-8">
                                      <MoreHorizontal className="h-4 w-4" />
                                    </Button>
                                  }
                                />
                                <DropdownMenuContent align="end">
                                  <DropdownMenuItem onClick={() => openChangeRoleDialog(member)}>
                                    <Pencil className="mr-2 h-4 w-4" />
                                    {t('changeRole')}
                                  </DropdownMenuItem>
                                  <DropdownMenuItem onClick={() => openTransferDialog(member)}>
                                    <ArrowRightLeft className="mr-2 h-4 w-4" />
                                    {t('transferOwnership')}
                                  </DropdownMenuItem>
                                  <DropdownMenuSeparator />
                                  <DropdownMenuItem
                                    variant="destructive"
                                    onClick={() => openRemoveMemberDialog(member)}
                                  >
                                    <Trash2 className="mr-2 h-4 w-4" />
                                    {t('removeMember')}
                                  </DropdownMenuItem>
                                </DropdownMenuContent>
                              </DropdownMenu>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  </ScrollArea>
                </div>
                
                {/* 团队操作按钮 */}
                <Separator />
                <div className="flex items-center justify-between">
                  <div className="flex gap-2">
                    {!team.is_default && (
                      <>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => setLeaveDialogOpen(true)}
                        >
                          <LogOut className="mr-2 h-4 w-4" />
                          {t('leaveTeam')}
                        </Button>
                        <PermissionGuard permission="team:delete">
                          <Button
                            variant="destructive"
                            size="sm"
                            onClick={() => setDeleteDialogOpen(true)}
                          >
                            <Trash2 className="mr-2 h-4 w-4" />
                            {commonT('delete')}
                          </Button>
                        </PermissionGuard>
                      </>
                    )}
                  </div>
                  <PermissionGuard permission="team:update">
                    <Button variant="outline" size="sm" onClick={onEdit}>
                      <Pencil className="mr-2 h-4 w-4" />
                      {commonT('edit')}
                    </Button>
                  </PermissionGuard>
                </div>
              </TabsContent>

              {canManageTeam && (
                <TabsContent value="models" className="mt-4">
                  <TeamModelsTab teamId={teamId!} />
                </TabsContent>
              )}
            </Tabs>
            </>
          ) : (
            <div className="flex items-center justify-center h-48 text-muted-foreground">
              {t('teamNotFound')}
            </div>
          )}
        </DialogContent>
      </Dialog>
      
      {/* 移除成员确认 */}
      <AlertDialog open={removeMemberDialogOpen} onOpenChange={setRemoveMemberDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('removeMember')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('removeMemberConfirm', { name: memberToRemove?.username || '' })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{commonT('cancel')}</AlertDialogCancel>
            <AlertDialogAction variant="destructive" onClick={handleRemoveMember}>
              {t('removeMember')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
      
      {/* 修改角色确认 */}
      <AlertDialog open={changeRoleDialogOpen} onOpenChange={setChangeRoleDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('changeRole')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('changeRoleDescription', { name: memberToChangeRole?.username || '' })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <div className="py-4">
            <Select value={newRole} onValueChange={(v) => setNewRole(v as AddableRole)}>
              <SelectTrigger>
                <SelectValue>
                  <div className="flex items-center gap-2">
                    <RoleIcon role={newRole} />
                    <span>{t(`roles.${newRole}`)}</span>
                  </div>
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                {roles.map((role) => (
                  <SelectItem key={role} value={role}>
                    <div className="flex items-center gap-2">
                      <RoleIcon role={role} />
                      <span>{t(`roles.${role}`)}</span>
                    </div>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <AlertDialogFooter>
            <AlertDialogCancel>{commonT('cancel')}</AlertDialogCancel>
            <AlertDialogAction onClick={handleChangeRole}>
              {commonT('save')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
      
      {/* 转移所有权确认 */}
      <AlertDialog open={transferDialogOpen} onOpenChange={setTransferDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('transferOwnership')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('transferOwnershipConfirm', { name: transferToMember?.username || '' })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{commonT('cancel')}</AlertDialogCancel>
            <AlertDialogAction onClick={handleTransferOwnership}>
              {t('transfer')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
      
      {/* 离开团队确认 */}
      <AlertDialog open={leaveDialogOpen} onOpenChange={setLeaveDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('leaveTeam')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('leaveTeamConfirm', { name: team?.name || '' })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{commonT('cancel')}</AlertDialogCancel>
            <AlertDialogAction variant="destructive" onClick={handleLeaveTeam}>
              {t('leaveTeam')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
      
      {/* 删除团队确认 */}
      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('confirmDelete')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('deleteTeamConfirm', { name: team?.name || '' })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{commonT('cancel')}</AlertDialogCancel>
            <AlertDialogAction variant="destructive" onClick={handleDeleteTeam}>
              {commonT('delete')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}
