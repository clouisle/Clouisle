'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { toast } from 'sonner'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { Badge } from '@/components/ui/badge'
import { ImageUpload } from '@/components/ui/image-upload'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { Loader2, Users, Crown, Shield, UserIcon, Eye, Lock } from 'lucide-react'
import { usersApi, authApi, teamsApi, type UserTeamInfo } from '@/lib/api'
import type { User } from '@/lib/api/auth'

// 角色图标映射
const roleIcons: Record<string, React.ElementType> = {
  owner: Crown,
  admin: Shield,
  member: UserIcon,
  viewer: Eye,
}

// 角色颜色映射
const roleColors: Record<string, string> = {
  owner: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200',
  admin: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200',
  member: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200',
  viewer: 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200',
}

export default function ProfilePage() {
  const t = useTranslations('settings')
  const tTeams = useTranslations('teams')
  const tPlatform = useTranslations('platform')
  
  const [loading, setLoading] = React.useState(true)
  const [saving, setSaving] = React.useState(false)
  const [savingPassword, setSavingPassword] = React.useState(false)
  const [passwordDialogOpen, setPasswordDialogOpen] = React.useState(false)
  const [user, setUser] = React.useState<User | null>(null)
  const [teams, setTeams] = React.useState<UserTeamInfo[]>([])
  const [formData, setFormData] = React.useState({
    username: '',
    email: '',
    avatar_url: '',
  })
  const [originalData, setOriginalData] = React.useState({
    username: '',
    email: '',
    avatar_url: '',
  })
  const [passwordData, setPasswordData] = React.useState({
    currentPassword: '',
    newPassword: '',
    confirmPassword: '',
  })

  // 检查是否有修改
  const hasChanges = React.useMemo(() => {
    return (
      formData.username !== originalData.username ||
      formData.email !== originalData.email ||
      formData.avatar_url !== originalData.avatar_url
    )
  }, [formData, originalData])

  React.useEffect(() => {
    loadData()
  }, [])

  const loadData = async () => {
    try {
      setLoading(true)
      const [userData, teamsData] = await Promise.all([
        authApi.getCurrentUser(),
        teamsApi.getMyTeams(),
      ])
      setUser(userData)
      setTeams(teamsData)
      const data = {
        username: userData.username,
        email: userData.email,
        avatar_url: userData.avatar_url || '',
      }
      setFormData(data)
      setOriginalData(data)
    } catch (error) {
      console.error('Failed to load data:', error)
    } finally {
      setLoading(false)
    }
  }

  const handleSave = async () => {
    if (!user) return
    
    try {
      setSaving(true)
      const updateData: Record<string, string | null> = {}
      
      if (formData.username !== originalData.username) {
        updateData.username = formData.username
      }
      if (formData.email !== originalData.email) {
        updateData.email = formData.email
      }
      if (formData.avatar_url !== originalData.avatar_url) {
        updateData.avatar_url = formData.avatar_url || null
      }
      
      const updatedUser = await usersApi.updateProfile(updateData)
      setUser(updatedUser)
      const newData = {
        username: updatedUser.username,
        email: updatedUser.email,
        avatar_url: updatedUser.avatar_url || '',
      }
      setFormData(newData)
      setOriginalData(newData)
      toast.success(t('profileUpdated'))
    } catch {
      // 错误已由 API 客户端处理
    } finally {
      setSaving(false)
    }
  }

  const handleChangePassword = async () => {
    if (!passwordData.currentPassword) {
      toast.error(t('currentPasswordRequired'))
      return
    }
    if (!passwordData.newPassword) {
      toast.error(t('newPasswordRequired'))
      return
    }
    if (passwordData.newPassword.length < 6) {
      toast.error(t('newPasswordTooShort'))
      return
    }
    if (passwordData.newPassword !== passwordData.confirmPassword) {
      toast.error(t('passwordMismatch'))
      return
    }

    try {
      setSavingPassword(true)
      await usersApi.changePassword({
        current_password: passwordData.currentPassword,
        new_password: passwordData.newPassword,
      })
      toast.success(t('passwordUpdated'))
      setPasswordData({
        currentPassword: '',
        newPassword: '',
        confirmPassword: '',
      })
      setPasswordDialogOpen(false)
    } catch {
      // 错误已由 API 客户端处理
    } finally {
      setSavingPassword(false)
    }
  }

  // 获取团队名首字母
  const getTeamInitials = (name: string) => {
    return name.slice(0, 2).toUpperCase()
  }

  if (loading) {
    return (
      <div className="py-6 px-8 space-y-6">
        <div className="mb-6">
          <Skeleton className="h-9 w-32" />
          <Skeleton className="h-5 w-64 mt-1" />
        </div>
        <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
          <div className="xl:col-span-2">
            <Card>
              <CardHeader>
                <Skeleton className="h-5 w-32" />
                <Skeleton className="h-4 w-48" />
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex gap-6">
                  <Skeleton className="h-24 w-24 rounded-full shrink-0" />
                  <div className="flex-1 space-y-4">
                    <Skeleton className="h-10 w-full max-w-sm" />
                    <Skeleton className="h-10 w-full max-w-sm" />
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
          <div>
            <Card>
              <CardHeader>
                <Skeleton className="h-5 w-24" />
                <Skeleton className="h-4 w-32" />
              </CardHeader>
              <CardContent className="space-y-3">
                {[1, 2, 3].map((i) => (
                  <Skeleton key={i} className="h-16 w-full" />
                ))}
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="py-6 px-8 space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">{t('profile')}</h1>
        <p className="text-muted-foreground mt-1">{t('profileDescription')}</p>
      </div>
      
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        {/* 左侧：个人信息 */}
        <div className="xl:col-span-2">
          <Card>
            <CardHeader>
              <CardTitle>{t('profileInfo')}</CardTitle>
              <CardDescription>{t('profileInfoDescription')}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="flex items-start gap-6">
                <div className="shrink-0">
                  <ImageUpload
                    value={formData.avatar_url}
                    onChange={(url) => setFormData(prev => ({ ...prev, avatar_url: url }))}
                    previewSize="lg"
                    category="avatars"
                  />
                </div>
                <div className="flex-1 space-y-4">
                  <div className="space-y-2">
                    <Label htmlFor="username">{t('username')}</Label>
                    <Input 
                      id="username" 
                      placeholder={t('usernamePlaceholder')}
                      value={formData.username}
                      onChange={(e) => setFormData(prev => ({ ...prev, username: e.target.value }))}
                      className="max-w-sm"
                    />
                  </div>
                  
                  <div className="space-y-2">
                    <Label htmlFor="email">{t('email')}</Label>
                    <Input 
                      id="email" 
                      type="email" 
                      placeholder={t('emailPlaceholder')}
                      value={formData.email}
                      onChange={(e) => setFormData(prev => ({ ...prev, email: e.target.value }))}
                      className="max-w-sm"
                    />
                  </div>
                </div>
              </div>
              
              <div className="flex items-center gap-3">
                {hasChanges && (
                  <Button onClick={handleSave} disabled={saving}>
                    {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                    {t('saveChanges')}
                  </Button>
                )}
                
                <Dialog open={passwordDialogOpen} onOpenChange={setPasswordDialogOpen}>
                  <DialogTrigger
                    render={
                      <Button variant="outline">
                        <Lock className="mr-2 h-4 w-4" />
                        {t('changePassword')}
                      </Button>
                    }
                  />
                  <DialogContent>
                    <DialogHeader>
                      <DialogTitle>{t('changePassword')}</DialogTitle>
                      <DialogDescription>{t('changePasswordDescription')}</DialogDescription>
                    </DialogHeader>
                    <div className="space-y-4 py-4">
                      <div className="space-y-2">
                        <Label htmlFor="current">{t('currentPassword')}</Label>
                        <Input 
                          id="current" 
                          type="password"
                          placeholder={t('currentPasswordPlaceholder')}
                          value={passwordData.currentPassword}
                          onChange={(e) => setPasswordData(prev => ({ ...prev, currentPassword: e.target.value }))}
                        />
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="new">{t('newPassword')}</Label>
                        <Input 
                          id="new" 
                          type="password"
                          placeholder={t('newPasswordPlaceholder')}
                          value={passwordData.newPassword}
                          onChange={(e) => setPasswordData(prev => ({ ...prev, newPassword: e.target.value }))}
                        />
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="confirm">{t('confirmNewPassword')}</Label>
                        <Input 
                          id="confirm" 
                          type="password"
                          placeholder={t('confirmNewPasswordPlaceholder')}
                          value={passwordData.confirmPassword}
                          onChange={(e) => setPasswordData(prev => ({ ...prev, confirmPassword: e.target.value }))}
                        />
                      </div>
                    </div>
                    <DialogFooter>
                      <Button variant="outline" onClick={() => setPasswordDialogOpen(false)}>
                        {t('cancel') || '取消'}
                      </Button>
                      <Button onClick={handleChangePassword} disabled={savingPassword}>
                        {savingPassword && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                        {t('updatePassword')}
                      </Button>
                    </DialogFooter>
                  </DialogContent>
                </Dialog>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* 右侧：团队信息 */}
        <div>
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Users className="h-5 w-5" />
                {tPlatform('teams')}
              </CardTitle>
              <CardDescription>
                {tPlatform('profile.teamsDescription', { count: teams.length })}
              </CardDescription>
            </CardHeader>
            <CardContent>
              {teams.length === 0 ? (
                <p className="text-sm text-muted-foreground text-center py-4">
                  {tPlatform('noTeams')}
                </p>
              ) : (
                <div className="space-y-3">
                  {teams.map((team) => {
                    const RoleIcon = roleIcons[team.role] || UserIcon
                    return (
                      <div
                        key={team.id}
                        className="flex items-center gap-3 p-3 rounded-lg border bg-card hover:bg-accent/50 transition-colors"
                      >
                        <Avatar className="h-10 w-10">
                          <AvatarImage src={team.avatar_url || ''} alt={team.name} />
                          <AvatarFallback className="text-xs">
                            {getTeamInitials(team.name)}
                          </AvatarFallback>
                        </Avatar>
                        <div className="flex-1 min-w-0">
                          <p className="font-medium truncate">{team.name}</p>
                          <Badge 
                            variant="secondary" 
                            className={`text-xs ${roleColors[team.role] || ''}`}
                          >
                            <RoleIcon className="h-3 w-3 mr-1" />
                            {tTeams(`roles.${team.role}`)}
                          </Badge>
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}
