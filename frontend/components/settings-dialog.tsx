'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { useRouter } from 'next/navigation'
import { toast } from 'sonner'
import { User, Shield, Loader2, Link as LinkIcon, Unlink } from 'lucide-react'
import { formatDateTime, isValidEmail } from '@/lib/utils'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { ImageUpload } from '@/components/ui/image-upload'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog'
import { usersApi, authApi, ssoApi, type User as UserType, type SSOConnection, type PasswordStatus } from '@/lib/api'
import { useSiteSettings } from '@/contexts/site-settings-context'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { AlertCircle, Clock } from 'lucide-react'
import { formatDate } from '@/lib/utils'

interface SettingsDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function SettingsDialog({ open, onOpenChange }: SettingsDialogProps) {
  const t = useTranslations('settings')
  const tCommon = useTranslations('common')
  const tSSO = useTranslations('sso')
  const tAuth = useTranslations('auth')
  const router = useRouter()
  const { settings: siteSettings } = useSiteSettings()

  const [loading, setLoading] = React.useState(true)
  const [user, setUser] = React.useState<UserType | null>(null)
  const [passwordStatus, setPasswordStatus] = React.useState<PasswordStatus | null>(null)

  // Profile form
  const [savingProfile, setSavingProfile] = React.useState(false)
  const [profileData, setProfileData] = React.useState({
    username: '',
    email: '',
    avatar_url: '',
  })

  // Password form
  const [savingPassword, setSavingPassword] = React.useState(false)
  const [passwordData, setPasswordData] = React.useState({
    currentPassword: '',
    newPassword: '',
    confirmPassword: '',
  })

  // SSO
  const [disconnectingId, setDisconnectingId] = React.useState<string | null>(null)

  // Delete account
  const [deleting, setDeleting] = React.useState(false)
  const [deleteDialogOpen, setDeleteDialogOpen] = React.useState(false)
  const [deletePassword, setDeletePassword] = React.useState('')

  // Load user when dialog opens
  React.useEffect(() => {
    if (open) {
      loadUser()
    }
  }, [open])

  const loadUser = async () => {
    try {
      setLoading(true)
      const userData = await authApi.getCurrentUser({ skipAuthRedirect: true })
      setUser(userData)
      setProfileData({
        username: userData.username,
        email: userData.email,
        avatar_url: userData.avatar_url || '',
      })

      // Load password status for local auth users
      if (userData.auth_source === 'local') {
        try {
          const status = await usersApi.getPasswordStatus()
          setPasswordStatus(status)
        } catch {
          // Password status not available
        }
      }
    } catch {
      // Error handled by API client
    } finally {
      setLoading(false)
    }
  }

  const handleSaveProfile = async () => {
    if (!user) return

    if (!isValidEmail(profileData.email)) {
      toast.error(t('invalidEmail'))
      return
    }

    try {
      setSavingProfile(true)
      const updateData: Record<string, string | null> = {}

      if (profileData.username !== user.username) {
        updateData.username = profileData.username
      }
      if (profileData.email !== user.email) {
        updateData.email = profileData.email
      }
      if (profileData.avatar_url !== (user.avatar_url || '')) {
        updateData.avatar_url = profileData.avatar_url || null
      }

      if (Object.keys(updateData).length === 0) {
        toast.info(t('noChanges'))
        return
      }

      const updatedUser = await usersApi.updateProfile(updateData)
      setUser(updatedUser)
      toast.success(t('profileUpdated'))
    } catch {
      // Error handled by API client
    } finally {
      setSavingProfile(false)
    }
  }

  const handleChangePassword = async () => {
    const hasPassword =
      user?.auth_source === 'local' || (user?.sso_connections && user.sso_connections.length === 0)

    if (hasPassword && !passwordData.currentPassword) {
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

      if (!hasPassword) {
        await usersApi.updateProfile({
          password: passwordData.newPassword,
        })
      } else {
        await usersApi.changePassword({
          current_password: passwordData.currentPassword,
          new_password: passwordData.newPassword,
        })
      }

      toast.success(t('passwordUpdated'))
      setPasswordData({
        currentPassword: '',
        newPassword: '',
        confirmPassword: '',
      })
      await loadUser()
    } catch {
      // Error handled by API client
    } finally {
      setSavingPassword(false)
    }
  }

  const handleDisconnect = async (connectionId: string) => {
    try {
      setDisconnectingId(connectionId)
      await ssoApi.disconnectConnection(connectionId)
      toast.success(tSSO('disconnectSuccess'))
      await loadUser()
    } catch {
      // Error handled by API client
    } finally {
      setDisconnectingId(null)
    }
  }

  const handleDeleteAccount = async () => {
    if (!deletePassword) {
      toast.error(t('currentPasswordRequired'))
      return
    }

    try {
      setDeleting(true)
      await usersApi.deleteAccount(deletePassword)
      toast.success(t('accountDeleted'))
      localStorage.removeItem('access_token')
      onOpenChange(false)
      router.push('/login')
    } catch {
      // Error handled by API client
    } finally {
      setDeleting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="!max-w-4xl max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{t('title')}</DialogTitle>
          <DialogDescription>{t('description')}</DialogDescription>
        </DialogHeader>

        {loading ? (
          <div className="space-y-4 py-4">
            <Skeleton className="h-10 w-48" />
            <Skeleton className="h-24 w-24 rounded-full" />
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
          </div>
        ) : (
          <Tabs defaultValue="profile" className="mt-4">
            <TabsList className="mb-4">
              <TabsTrigger value="profile">
                <User className="mr-1.5 h-4 w-4" />
                {t('profile')}
              </TabsTrigger>
              <TabsTrigger value="account">
                <Shield className="mr-1.5 h-4 w-4" />
                {t('account')}
              </TabsTrigger>
            </TabsList>

            {/* Profile Tab */}
            <TabsContent value="profile" className="space-y-6">
              <div className="space-y-2">
                <Label>{t('avatar')}</Label>
                <p className="text-sm text-muted-foreground">{t('avatarDescription')}</p>
                <div className="mt-2">
                  <ImageUpload
                    value={profileData.avatar_url}
                    onChange={(url) => setProfileData((prev) => ({ ...prev, avatar_url: url }))}
                    previewSize="lg"
                    category="avatars"
                  />
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="username">{t('username')}</Label>
                <Input
                  id="username"
                  placeholder={t('usernamePlaceholder')}
                  value={profileData.username}
                  onChange={(e) => setProfileData((prev) => ({ ...prev, username: e.target.value }))}
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="email">{t('email')}</Label>
                <Input
                  id="email"
                  type="email"
                  placeholder={t('emailPlaceholder')}
                  value={profileData.email}
                  onChange={(e) => setProfileData((prev) => ({ ...prev, email: e.target.value }))}
                  required
                />
              </div>

              <div className="flex justify-end">
                <Button onClick={handleSaveProfile} disabled={savingProfile}>
                  {savingProfile && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                  {t('saveChanges')}
                </Button>
              </div>
            </TabsContent>

            {/* Account Tab */}
            <TabsContent value="account" className="space-y-6">
              {/* SSO Connections */}
              {user?.sso_connections && user.sso_connections.length > 0 && (
                <Card>
                  <CardHeader className="pb-3">
                    <CardTitle className="text-base">{tSSO('connectedAccounts')}</CardTitle>
                    <CardDescription>{tSSO('connectedAccountsDescription')}</CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    {user.sso_connections.map((connection: SSOConnection) => (
                      <div
                        key={connection.id}
                        className="flex items-center justify-between rounded-lg border p-3"
                      >
                        <div className="flex items-center gap-3">
                          {connection.provider_icon_url && (
                            <img
                              src={connection.provider_icon_url}
                              alt={connection.provider_display_name}
                              className="h-8 w-8 rounded"
                            />
                          )}
                          <div>
                            <div className="flex items-center gap-2">
                              <p className="text-sm font-medium">{connection.provider_display_name}</p>
                              <LinkIcon className="h-3 w-3 text-muted-foreground" />
                            </div>
                            <p className="text-xs text-muted-foreground">
                              {tSSO('lastLogin')}: {formatDateTime(connection.last_login)}
                            </p>
                          </div>
                        </div>
                        <AlertDialog>
                          <AlertDialogTrigger
                            render={(props) => (
                              <Button
                                {...props}
                                variant="outline"
                                size="sm"
                                disabled={disconnectingId === connection.id}
                              >
                                {disconnectingId === connection.id ? (
                                  <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                                ) : (
                                  <Unlink className="mr-1 h-3 w-3" />
                                )}
                                {tSSO('disconnect')}
                              </Button>
                            )}
                          />
                          <AlertDialogContent>
                            <AlertDialogHeader>
                              <AlertDialogTitle>{tSSO('disconnect')}</AlertDialogTitle>
                              <AlertDialogDescription>{tSSO('disconnectConfirm')}</AlertDialogDescription>
                            </AlertDialogHeader>
                            <AlertDialogFooter>
                              <AlertDialogCancel>{tCommon('cancel')}</AlertDialogCancel>
                              <AlertDialogAction
                                variant="destructive"
                                onClick={() => handleDisconnect(connection.id)}
                              >
                                {tSSO('disconnect')}
                              </AlertDialogAction>
                            </AlertDialogFooter>
                          </AlertDialogContent>
                        </AlertDialog>
                      </div>
                    ))}
                  </CardContent>
                </Card>
              )}

              {/* Password */}
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-base">
                    {user?.auth_source === 'local' ||
                    (user?.sso_connections && user.sso_connections.length === 0)
                      ? t('changePassword')
                      : t('setPassword')}
                  </CardTitle>
                  <CardDescription>
                    {user?.auth_source === 'local' ||
                    (user?.sso_connections && user.sso_connections.length === 0)
                      ? t('changePasswordDescription')
                      : t('setPasswordDescription')}
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  {/* Password Status */}
                  {passwordStatus && !passwordStatus.is_exempt && (
                    <div className="space-y-3">
                      {passwordStatus.is_expired && (
                        <Alert className="border-destructive bg-destructive/10">
                          <AlertCircle className="h-4 w-4 text-destructive" />
                          <AlertDescription className="text-destructive">
                            {tAuth('passwordExpired')}
                          </AlertDescription>
                        </Alert>
                      )}
                      {!passwordStatus.is_expired &&
                        passwordStatus.days_until_expiration !== null &&
                        passwordStatus.days_until_expiration <= 7 && (
                          <Alert className="border-yellow-500 bg-yellow-50 dark:bg-yellow-950">
                            <Clock className="h-4 w-4 text-yellow-600 dark:text-yellow-400" />
                            <AlertDescription className="text-yellow-800 dark:text-yellow-200">
                              {tAuth('passwordExpiringSoon', {
                                days: passwordStatus.days_until_expiration,
                              })}
                            </AlertDescription>
                          </Alert>
                        )}
                      {passwordStatus.password_expires_at && (
                        <div className="rounded-lg border bg-muted/50 p-3">
                          <div className="flex items-center gap-2 text-sm">
                            <Clock className="h-4 w-4 text-muted-foreground" />
                            <span className="text-muted-foreground">
                              {tAuth('passwordExpiresAt')}:{' '}
                              <span className="font-medium text-foreground">
                                {formatDate(passwordStatus.password_expires_at)}
                              </span>
                            </span>
                          </div>
                        </div>
                      )}
                    </div>
                  )}

                  {(user?.auth_source === 'local' ||
                    (user?.sso_connections && user.sso_connections.length === 0)) && (
                    <div className="space-y-2">
                      <Label htmlFor="current">{t('currentPassword')}</Label>
                      <Input
                        id="current"
                        type="password"
                        placeholder={t('currentPasswordPlaceholder')}
                        value={passwordData.currentPassword}
                        onChange={(e) =>
                          setPasswordData((prev) => ({ ...prev, currentPassword: e.target.value }))
                        }
                      />
                    </div>
                  )}
                  <div className="space-y-2">
                    <Label htmlFor="new">{t('newPassword')}</Label>
                    <Input
                      id="new"
                      type="password"
                      placeholder={t('newPasswordPlaceholder')}
                      value={passwordData.newPassword}
                      onChange={(e) =>
                        setPasswordData((prev) => ({ ...prev, newPassword: e.target.value }))
                      }
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="confirm">{t('confirmNewPassword')}</Label>
                    <Input
                      id="confirm"
                      type="password"
                      placeholder={t('confirmNewPasswordPlaceholder')}
                      value={passwordData.confirmPassword}
                      onChange={(e) =>
                        setPasswordData((prev) => ({ ...prev, confirmPassword: e.target.value }))
                      }
                    />
                  </div>
                  <div className="flex justify-end">
                    <Button onClick={handleChangePassword} disabled={savingPassword}>
                      {savingPassword && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                      {user?.auth_source === 'local' ||
                      (user?.sso_connections && user.sso_connections.length === 0)
                        ? t('updatePassword')
                        : t('setPassword')}
                    </Button>
                  </div>
                </CardContent>
              </Card>

              {/* Danger Zone */}
              {siteSettings.allow_account_deletion && (
                <Card className="border-destructive">
                  <CardHeader className="pb-3">
                    <CardTitle className="text-base text-destructive">{t('dangerZone')}</CardTitle>
                    <CardDescription>{t('deleteAccountDescription')}</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="flex justify-end">
                      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
                        <AlertDialogTrigger
                          render={<Button variant="destructive" size="sm">{t('deleteAccount')}</Button>}
                        />
                      <AlertDialogContent>
                        <AlertDialogHeader>
                          <AlertDialogTitle>{t('deleteAccount')}</AlertDialogTitle>
                          <AlertDialogDescription>{t('deleteAccountConfirm')}</AlertDialogDescription>
                        </AlertDialogHeader>
                        <div className="space-y-2">
                          <Label htmlFor="delete-password">{t('currentPassword')}</Label>
                          <Input
                            id="delete-password"
                            type="password"
                            placeholder={t('currentPasswordPlaceholder')}
                            value={deletePassword}
                            onChange={(e) => setDeletePassword(e.target.value)}
                          />
                        </div>
                        <AlertDialogFooter>
                          <AlertDialogCancel onClick={() => setDeletePassword('')}>
                            {tCommon('cancel')}
                          </AlertDialogCancel>
                          <AlertDialogAction
                            onClick={handleDeleteAccount}
                            disabled={deleting || !deletePassword}
                            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                          >
                            {deleting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                            {t('deleteAccount')}
                          </AlertDialogAction>
                        </AlertDialogFooter>
                      </AlertDialogContent>
                    </AlertDialog>
                    </div>
                  </CardContent>
                </Card>
              )}
            </TabsContent>
          </Tabs>
        )}
      </DialogContent>
    </Dialog>
  )
}
