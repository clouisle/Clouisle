'use client'

import * as React from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { toast } from 'sonner'
import {
  Users,
  Cpu,
  Settings as SettingsIcon,
  ShieldAlert,
  UserPlus,
  Trash2,
  ArrowRightLeft,
  Pencil,
  Crown,
  Shield,
  User,
  Eye,
  Search,
  MoreHorizontal,
  LogOut,
  AlertTriangle,
} from 'lucide-react'

import {
  teamsApi as platformTeamsApi,
  type TeamWithMembers,
  type TeamMember,
  teamModelsApi,
  type TeamModel,
} from '@/lib/api'
import { useTeam } from '@/contexts/team-context'
import { usePermissions } from '@/hooks/use-permissions'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { ImageUpload } from '@/components/ui/image-upload'
import { Badge } from '@/components/ui/badge'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
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
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

type TeamRole = 'owner' | 'admin' | 'member' | 'viewer'
type TeamTab = 'members' | 'models' | 'settings'

const isTeamTab = (value: string | null): value is TeamTab =>
  value === 'members' || value === 'models' || value === 'settings'

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
const getTeamInitials = (teamName: string) => {
  if (!teamName) return '?'
  return teamName.slice(0, 2).toUpperCase()
}

export default function PlatformTeamPage() {
  const t = useTranslations('teams')
  const commonT = useTranslations('common')
  const router = useRouter()
  const searchParams = useSearchParams()
  const { currentTeam, refreshTeams, isLoading: isContextLoading } = useTeam()
  const { user: currentUser, hasPermission, loading: isPermissionsLoading } = usePermissions()

  const tabParam = searchParams.get('tab')
  const activeTab: TeamTab = isTeamTab(tabParam) ? tabParam : 'members'

  const handleTabChange = (value: string | null) => {
    if (!isTeamTab(value)) return
    const params = new URLSearchParams(searchParams.toString())
    params.set('tab', value)
    router.push(`?${params.toString()}`, { scroll: false })
  }

  const [teamDetail, setTeamDetail] = React.useState<TeamWithMembers | null>(null)
  const [isLoadingDetail, setIsLoadingDetail] = React.useState(true)

  // 基础信息编辑
  const [name, setName] = React.useState('')
  const [description, setDescription] = React.useState('')
  const [avatarUrl, setAvatarUrl] = React.useState('')
  const [isSavingBasic, setIsSavingBasic] = React.useState(false)

  // 成员操作状态
  const [memberSearch, setMemberSearch] = React.useState('')
  const [addMemberDialogOpen, setAddMemberDialogOpen] = React.useState(false)
  const [candidateIdentifier, setCandidateIdentifier] = React.useState('')
  const [teamModels, setTeamModels] = React.useState<TeamModel[]>([])
  const [isLoadingModels, setIsLoadingModels] = React.useState(true)
  const [modelSearch, setModelSearch] = React.useState('')
  const [selectedRole, setSelectedRole] = React.useState<AddableRole>('member')
  const [isAddingMember, setIsAddingMember] = React.useState(false)

  // 对话框
  const [changeRoleMember, setChangeRoleMember] = React.useState<TeamMember | null>(null)
  const [newRole, setNewRole] = React.useState<AddableRole>('member')
  const [removeMember, setRemoveMember] = React.useState<TeamMember | null>(null)
  const [transferMember, setTransferMember] = React.useState<TeamMember | null>(null)
  const [leaveDialogOpen, setLeaveDialogOpen] = React.useState(false)

  const currentMembership = teamDetail?.members.find((m) => m.user_id === currentUser?.id)
  const isOwner = currentUser?.is_superuser || currentMembership?.role === 'owner'
  const isTeamAdmin = isOwner || currentMembership?.role === 'admin'
  const canManageTeam = !isPermissionsLoading && (currentUser?.is_superuser || (isTeamAdmin && hasPermission('team:manage')))
  const canUpdateTeam = !isPermissionsLoading && (currentUser?.is_superuser || (isTeamAdmin && hasPermission('team:update')))

  const loadTeamDetail = React.useCallback(async () => {
    if (!currentTeam?.id) return
    try {
      setIsLoadingDetail(true)
      const data = await platformTeamsApi.getTeam(currentTeam.id)
      setTeamDetail(data)
      setName(data.name || '')
      setDescription(data.description || '')
      setAvatarUrl(data.avatar_url || '')
    } catch {
      // 错误已由 API 客户端处理
    } finally {
      setIsLoadingDetail(false)
    }
  }, [currentTeam?.id])

  React.useEffect(() => {
    loadTeamDetail()
  }, [loadTeamDetail])

  const loadTeamModels = React.useCallback(async () => {
    if (!currentTeam?.id) return
    try {
      setIsLoadingModels(true)
      const models = await teamModelsApi.getTeamModels(currentTeam.id)
      setTeamModels(models)
    } catch {
      // API error handled
    } finally {
      setIsLoadingModels(false)
    }
  }, [currentTeam?.id])

  React.useEffect(() => {
    loadTeamModels()
  }, [loadTeamModels])


  const handleSaveBasic = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!currentTeam?.id || !canUpdateTeam) return
    setIsSavingBasic(true)
    try {
      await platformTeamsApi.updateTeam(currentTeam.id, {
        name,
        description: description || undefined,
        avatar_url: avatarUrl || undefined,
      })
      toast.success(t('teamUpdated'))
      await refreshTeams()
      await loadTeamDetail()
    } catch {
      // API error handled
    } finally {
      setIsSavingBasic(false)
    }
  }

  const handleAddMember = async (e?: React.FormEvent) => {
    if (e) e.preventDefault()
    if (!currentTeam?.id || !candidateIdentifier.trim() || !canManageTeam) return
    setIsAddingMember(true)
    try {
      await platformTeamsApi.addMember(currentTeam.id, {
        identifier: candidateIdentifier.trim(),
        role: selectedRole,
      })
      toast.success(t('memberAdded'))
      setAddMemberDialogOpen(false)
      setCandidateIdentifier('')
      setSelectedRole('member')
      await loadTeamDetail()
    } catch {
      // API error handled
    } finally {
      setIsAddingMember(false)
    }
  }

  const handleChangeRole = async () => {
    if (!currentTeam?.id || !changeRoleMember || !canManageTeam) return
    try {
      await platformTeamsApi.updateMember(currentTeam.id, changeRoleMember.user_id, {
        role: newRole,
      })
      toast.success(t('roleUpdated'))
      setChangeRoleMember(null)
      await loadTeamDetail()
    } catch {
      // API error handled
    }
  }

  const handleRemoveMember = async () => {
    if (!currentTeam?.id || !removeMember || !canManageTeam) return
    try {
      await platformTeamsApi.removeMember(currentTeam.id, removeMember.user_id)
      toast.success(t('memberRemoved'))
      setRemoveMember(null)
      await loadTeamDetail()
    } catch {
      // API error handled
    }
  }

  const handleTransferOwnership = async () => {
    if (!currentTeam?.id || !transferMember || !isOwner) return
    try {
      await platformTeamsApi.transferOwnership(currentTeam.id, transferMember.user_id)
      toast.success(t('ownershipTransferred'))
      setTransferMember(null)
      await refreshTeams()
      await loadTeamDetail()
    } catch {
      // API error handled
    }
  }

  const handleLeaveTeam = async () => {
    if (!currentTeam?.id) return
    try {
      await platformTeamsApi.leaveTeam(currentTeam.id)
      toast.success(t('leftTeam'))
      setLeaveDialogOpen(false)
      await refreshTeams()
      router.push('/app')
    } catch {
      // API error handled
    }
  }
  if (isContextLoading || isPermissionsLoading || isLoadingDetail) {
    return (
      <div className="py-6 px-8 space-y-6">
        <Skeleton className="h-10 w-48" />
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-96 w-full" />
      </div>
    )
  }

  if (!currentTeam) {
    return (
      <div className="py-16 px-8 text-center space-y-4">
        <AlertTriangle className="h-12 w-12 text-yellow-500 mx-auto" />
        <h2 className="text-xl font-semibold">{t('teamNotFound')}</h2>
        <Button onClick={() => router.push('/app')}>{commonT('back')}</Button>
      </div>
    )
  }

  const filteredMembers = (teamDetail?.members || []).filter(
    (m) =>
      m.username.toLowerCase().includes(memberSearch.toLowerCase()) ||
      m.email.toLowerCase().includes(memberSearch.toLowerCase())
  )

  const roles: AddableRole[] = ['admin', 'member', 'viewer']

  return (
    <div className="py-6 px-8 space-y-6">
      {/* 头部摘要 */}
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-4">
          <Avatar className="h-16 w-16 rounded-lg">
            <AvatarImage src={teamDetail?.avatar_url || undefined} />
            <AvatarFallback className="text-xl rounded-lg bg-primary text-primary-foreground">
              {teamDetail?.name?.slice(0, 2).toUpperCase()}
            </AvatarFallback>
          </Avatar>
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-bold tracking-tight">{teamDetail?.name}</h1>
              {teamDetail?.is_default && <Badge variant="secondary">{t('defaultTeam')}</Badge>}
              <Badge variant="outline" className="flex items-center gap-1.5">
                <RoleIcon role={(currentMembership?.role as TeamRole) || 'member'} />
                <span>{t(`roles.${currentMembership?.role || 'member'}`)}</span>
              </Badge>
            </div>
            <p className="text-sm text-muted-foreground mt-1">
              {teamDetail?.description || t('noDescription')}
            </p>
          </div>
        </div>
      </div>

      {/* 标签页面板 */}
      <Tabs value={activeTab} onValueChange={handleTabChange} className="space-y-6">
        <TabsList className="grid w-full grid-cols-3 max-w-md">
          <TabsTrigger value="members" className="gap-2">
            <Users className="h-4 w-4" />
            {t('members')}
          </TabsTrigger>
          <TabsTrigger value="models" className="gap-2">
            <Cpu className="h-4 w-4" />
            {t('modelAuth')}
          </TabsTrigger>
          <TabsTrigger value="settings" className="gap-2">
            <SettingsIcon className="h-4 w-4" />
            {t('settings')}
          </TabsTrigger>
        </TabsList>

        {/* Tab 1: 成员管理 */}
        <TabsContent value="members" className="space-y-4">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between pb-4">
              <div>
                <CardTitle className="text-lg">
                  {t('members')} ({teamDetail?.members.length || 0})
                </CardTitle>
              </div>
              {canManageTeam && (
                <Button size="sm" onClick={() => setAddMemberDialogOpen(true)}>
                  <UserPlus className="h-4 w-4 mr-2" />
                  {t('addMember')}
                </Button>
              )}
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="relative max-w-sm">
                <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  placeholder={t('searchUsers')}
                  value={memberSearch}
                  onChange={(e) => setMemberSearch(e.target.value)}
                  className="pl-8 h-9"
                />
              </div>

              <div className="border rounded-md divide-y">
                {filteredMembers.map((member) => {
                  const isMemberOwner = member.role === 'owner'
                  const isMemberSelf = member.user_id === currentUser?.id
                  const canActOnMember =
                    canManageTeam &&
                    !isMemberOwner &&
                    (!isMemberSelf || false) &&
                    (isOwner || member.role !== 'admin')

                  return (
                    <div
                      key={member.user_id}
                      className="flex items-center justify-between p-4 hover:bg-muted/40 transition-colors"
                    >
                      <div className="flex items-center gap-3">
                        <Avatar className="h-9 w-9">
                          <AvatarImage src={member.avatar_url || undefined} />
                          <AvatarFallback>
                            {member.username.slice(0, 2).toUpperCase()}
                          </AvatarFallback>
                        </Avatar>
                        <div>
                          <div className="font-medium text-sm">
                            {member.username}
                          </div>
                          <div className="text-xs text-muted-foreground">{member.email}</div>
                        </div>
                      </div>

                      <div className="flex items-center gap-3">
                        <Badge variant="outline" className="flex items-center gap-1">
                          <RoleIcon role={member.role as TeamRole} />
                          <span>{t(`roles.${member.role}`)}</span>
                        </Badge>

                        {canActOnMember && (
                          <DropdownMenu>
                            <DropdownMenuTrigger
                              render={(props) => (
                                <Button {...props} variant="ghost" size="icon" className="h-8 w-8">
                                  <MoreHorizontal className="h-4 w-4" />
                                </Button>
                              )}
                            />
                            <DropdownMenuContent align="end">
                              <DropdownMenuItem
                                onClick={() => {
                                  setChangeRoleMember(member)
                                  setNewRole(
                                    member.role === 'owner' ? 'admin' : (member.role as AddableRole)
                                  )
                                }}
                              >
                                <Pencil className="h-4 w-4 mr-2" />
                                {t('changeRole')}
                              </DropdownMenuItem>

                              {isOwner && (
                                <DropdownMenuItem onClick={() => setTransferMember(member)}>
                                  <ArrowRightLeft className="h-4 w-4 mr-2" />
                                  {t('transferOwnership')}
                                </DropdownMenuItem>
                              )}

                              <DropdownMenuSeparator />
                              <DropdownMenuItem
                                variant="destructive"
                                onClick={() => setRemoveMember(member)}
                              >
                                <Trash2 className="h-4 w-4 mr-2" />
                                {t('removeMember')}
                              </DropdownMenuItem>
                            </DropdownMenuContent>
                          </DropdownMenu>
                        )}
                      </div>
                    </div>
                  )
                })}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Tab 2: 已授权模型与配额（只读） */}
        <TabsContent value="models">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between pb-4">
              <div>
                <CardTitle className="text-lg">{t('authorizedModels') || '已授权模型'}</CardTitle>
                <CardDescription>
                  {t('modelAuthDescription') || '当前团队可使用的模型及其额度限制（由系统管理员分配）'}
                </CardDescription>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="relative max-w-sm">
                <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  placeholder={t('searchModels') || '搜索模型...'}
                  value={modelSearch}
                  onChange={(e) => setModelSearch(e.target.value)}
                  className="pl-8 h-9"
                />
              </div>

              {isLoadingModels ? (
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                  {[1, 2, 3].map((i) => (
                    <div key={i} className="border rounded-lg p-4 space-y-3">
                      <Skeleton className="h-5 w-32" />
                      <Skeleton className="h-4 w-48" />
                      <Skeleton className="h-2 w-full mt-2" />
                    </div>
                  ))}
                </div>
              ) : teamModels.length === 0 ? (
                <div className="border rounded-md p-8 text-center text-muted-foreground text-sm">
                  {t('noModelsAuthorized') || '暂无已授权模型，请联系系统管理员下发模型授权。'}
                </div>
              ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                  {teamModels
                    .filter(
                      (tm) =>
                        tm.model.name.toLowerCase().includes(modelSearch.toLowerCase()) ||
                        tm.model.model_id.toLowerCase().includes(modelSearch.toLowerCase()) ||
                        tm.model.provider.toLowerCase().includes(modelSearch.toLowerCase())
                    )
                    .map((tm) => {
                      const dailyLimit = tm.daily_token_limit
                      const dailyUsed = tm.daily_tokens_used || 0
                      const hasLimit = dailyLimit !== null && dailyLimit > 0
                      const percent = hasLimit ? Math.min(100, Math.round((dailyUsed / dailyLimit) * 100)) : null

                      return (
                        <div
                          key={tm.id}
                          className="border rounded-lg p-4 bg-card hover:border-primary/40 transition-colors space-y-3"
                        >
                          <div className="flex items-start justify-between">
                            <div>
                              <div className="font-semibold text-sm flex items-center gap-2">
                                {tm.model.name}
                                <Badge variant="secondary" className="text-[10px] px-1.5 py-0 capitalize">
                                  {tm.model.model_type}
                                </Badge>
                              </div>
                              <div className="text-xs text-muted-foreground mt-0.5">
                                {tm.model.provider_display_name || tm.model.provider} · {tm.model.model_id}
                              </div>
                            </div>
                            <Badge variant={tm.is_enabled ? 'default' : 'outline'} className="text-[10px]">
                              {tm.is_enabled ? '已启用' : '已停用'}
                            </Badge>
                          </div>

                          <div className="space-y-1.5 pt-1 text-xs border-t">
                            <div className="flex justify-between text-muted-foreground">
                              <span>今日用量 / 限额</span>
                              <span className="font-mono">
                                {dailyUsed.toLocaleString()} / {hasLimit ? dailyLimit.toLocaleString() : '无限制'}
                              </span>
                            </div>
                            {hasLimit && percent !== null && (
                              <div className="h-1.5 bg-muted rounded-full overflow-hidden">
                                <div
                                  className={`h-full ${
                                    percent >= 90 ? 'bg-destructive' : percent >= 70 ? 'bg-yellow-500' : 'bg-primary'
                                  }`}
                                  style={{ width: `${percent}%` }}
                                />
                              </div>
                            )}
                          </div>
                        </div>
                      )
                    })}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
        {/* Tab 3: 基本设置与安全 */}
        <TabsContent value="settings" className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">{t('basicSettings') || '基本信息'}</CardTitle>
              <CardDescription>
                {t('basicSettingsDesc') || '查看并修改团队的公开基础信息'}
              </CardDescription>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleSaveBasic} className="grid gap-6 md:grid-cols-[auto_minmax(0,1fr)]">
                <div className="flex flex-col items-center gap-2">
                  <Label>{t('avatar')}</Label>
                  <ImageUpload
                    value={avatarUrl}
                    onChange={setAvatarUrl}
                    previewSize="lg"
                    category="avatars"
                    accept="image/jpeg,image/png,image/gif,image/webp,image/svg+xml,image/x-icon"
                    disabled={!canUpdateTeam}
                    placeholder={
                      <span className="text-xl font-semibold text-muted-foreground">
                        {getTeamInitials(name)}
                      </span>
                    }
                  />
                  <p className="text-xs text-muted-foreground text-center">{t('avatarHint')}</p>
                </div>

                <div className="grid gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="team-name">{t('teamName')}</Label>
                    <Input
                      id="team-name"
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      disabled={!canUpdateTeam}
                      required
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="team-desc">{t('teamDescription')}</Label>
                    <Textarea
                      id="team-desc"
                      value={description}
                      onChange={(e) => setDescription(e.target.value)}
                      disabled={!canUpdateTeam}
                      rows={3}
                    />
                  </div>
                </div>

                {canUpdateTeam && (
                  <div className="md:col-span-2">
                    <Button type="submit" disabled={isSavingBasic}>
                      {isSavingBasic ? commonT('loading') : commonT('save')}
                    </Button>
                  </div>
                )}
              </form>
            </CardContent>
          </Card>

          {/* 危险操作区 */}
          <Card className="border-destructive/40 bg-destructive/5">
            <CardHeader>
              <CardTitle className="text-lg text-destructive flex items-center gap-2">
                <ShieldAlert className="h-5 w-5" />
                {t('dangerZone') || '危险区域'}
              </CardTitle>
              <CardDescription>
                {t('dangerZoneDesc') || '涉及退出或解散团队的高风险操作'}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {!teamDetail?.is_default && !isOwner && (
                <div className="flex items-center justify-between py-2">
                  <div>
                    <div className="font-medium text-sm">{t('leaveTeam')}</div>
                    <div className="text-xs text-muted-foreground">
                      {t('leaveTeamDesc') || '退出后将失去该团队内所有资源访问权'}
                    </div>
                  </div>
                  <Button
                    variant="outline"
                    size="sm"
                    className="text-destructive border-destructive hover:bg-destructive/10"
                    onClick={() => setLeaveDialogOpen(true)}
                  >
                    <LogOut className="h-4 w-4 mr-2" />
                    {t('leaveTeam')}
                  </Button>
                </div>
              )}

              {isOwner && (
                <div className="text-xs text-muted-foreground">
                  {t('ownerCannotLeaveWarning') ||
                    '作为团队所有者，你无法直接退出团队。如需离开或转交团队，请先在成员列表中转移所有权。'}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* 弹窗：添加成员 */}
      <Dialog open={addMemberDialogOpen} onOpenChange={setAddMemberDialogOpen}>
        <DialogContent className="sm:max-w-md">
          <form onSubmit={handleAddMember}>
            <DialogHeader>
              <DialogTitle>{t('addMember')}</DialogTitle>
              <DialogDescription>
                {t('addMemberExactHint') || '输入目标用户的完整用户名或邮箱直接添加'}
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-4 py-4">
              <div className="space-y-2">
                <Label htmlFor="member-identifier">{t('userIdentifier') || '用户名或邮箱'}</Label>
                <Input
                  id="member-identifier"
                  placeholder={t('userIdentifierPlaceholder') || '输入用户名或邮箱，如：john 或 john@example.com'}
                  value={candidateIdentifier}
                  onChange={(e) => setCandidateIdentifier(e.target.value)}
                  required
                  autoFocus
                />
              </div>

              <div className="space-y-2">
                <Label>{t('role')}</Label>
                <Select
                  value={selectedRole}
                  onValueChange={(v) => setSelectedRole(v as AddableRole)}
                >
                  <SelectTrigger>
                    <SelectValue>
                      <div className="flex items-center gap-2">
                        <RoleIcon role={selectedRole} />
                        <span>{t(`roles.${selectedRole}`)}</span>
                      </div>
                    </SelectValue>
                  </SelectTrigger>
                  <SelectContent>
                    {roles.map((r) => (
                      <SelectItem key={r} value={r}>
                        <div className="flex items-center gap-2">
                          <RoleIcon role={r} />
                          <span>{t(`roles.${r}`)}</span>
                        </div>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setAddMemberDialogOpen(false)}>
                {commonT('cancel')}
              </Button>
              <Button type="submit" disabled={!candidateIdentifier.trim() || isAddingMember}>
                {isAddingMember ? commonT('loading') : commonT('confirm')}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* 修改成员角色 */}
      <Dialog open={!!changeRoleMember} onOpenChange={(open) => !open && setChangeRoleMember(null)}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>{t('changeRole')}</DialogTitle>
            <DialogDescription>
              {t('changeRoleDescription', { name: changeRoleMember?.username || '' })}
            </DialogDescription>
          </DialogHeader>
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
                {roles.map((r) => (
                  <SelectItem key={r} value={r}>
                    <div className="flex items-center gap-2">
                      <RoleIcon role={r} />
                      <span>{t(`roles.${r}`)}</span>
                    </div>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setChangeRoleMember(null)}>
              {commonT('cancel')}
            </Button>
            <Button onClick={handleChangeRole}>{commonT('save')}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* 确认移除成员 */}
      <AlertDialog open={!!removeMember} onOpenChange={(open) => !open && setRemoveMember(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('removeMember')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('removeMemberConfirm', { name: removeMember?.username || '' })}
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

      {/* 确认转移所有权 */}
      <AlertDialog
        open={!!transferMember}
        onOpenChange={(open) => !open && setTransferMember(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('transferOwnership')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('transferOwnershipConfirm', { name: transferMember?.username || '' })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{commonT('cancel')}</AlertDialogCancel>
            <AlertDialogAction onClick={handleTransferOwnership}>
              {commonT('confirm')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* 确认退出团队 */}
      <AlertDialog open={leaveDialogOpen} onOpenChange={setLeaveDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('leaveTeam')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('leaveTeamConfirm', { name: teamDetail?.name || currentTeam?.name || '' })}
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
    </div>
  )
}
