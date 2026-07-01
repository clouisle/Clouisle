'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { useRouter } from 'next/navigation'
import { toast } from 'sonner'
import { User, Shield, Loader2, Link as LinkIcon, Unlink, KeyRound, Download, Copy, Mail } from 'lucide-react'
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
import { usersApi, authApi, ssoApi, totpApi, type User as UserType, type SSOConnection, type PasswordStatus, type TOTPStatusResponse } from '@/lib/api'
import { useSiteSettings } from '@/contexts/site-settings-context'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { AlertCircle, Clock } from 'lucide-react'
import { formatDate } from '@/lib/utils'
import { TOTPSetupWizard } from './totp-setup-wizard'
import { InputOTP, InputOTPGroup, InputOTPSlot } from '@/components/ui/input-otp'
import { FieldError } from '@/components/ui/field'
import {
  clearValidationError,
  getValidationSummaryEntries,
  normalizeValidationErrors,
  formatValidationSummaryMessage
} from '@/lib/validation'
import { ApiError } from '@/lib/api/client'

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
  const [totpStatus, setTotpStatus] = React.useState<TOTPStatusResponse | null>(null)

  // Profile form
  const [savingProfile, setSavingProfile] = React.useState(false)
  const [emailVerificationCode, setEmailVerificationCode] = React.useState('')
  const [emailVerificationSent, setEmailVerificationSent] = React.useState(false)
  const [sendingProfileVerification, setSendingProfileVerification] = React.useState(false)
  const [profileData, setProfileData] = React.useState({
    username: '',
    email: '',
    avatar_url: '',
  })
  const [profileErrors, setProfileErrors] = React.useState<Record<string, string>>({})

  // Password form
  const [savingPassword, setSavingPassword] = React.useState(false)
  const [passwordData, setPasswordData] = React.useState({
    currentPassword: '',
    newPassword: '',
    confirmPassword: '',
  })
  const [passwordErrors, setPasswordErrors] = React.useState<Record<string, string>>({})

  // SSO
  const [disconnectingId, setDisconnectingId] = React.useState<string | null>(null)

  // Delete account
  const [deleting, setDeleting] = React.useState(false)
  const [deleteDialogOpen, setDeleteDialogOpen] = React.useState(false)
  const [deletePassword, setDeletePassword] = React.useState('')
  const [deleteErrors, setDeleteErrors] = React.useState<Record<string, string>>({})

  // TOTP
  const [setupWizardOpen, setSetupWizardOpen] = React.useState(false)
  const [disableTotpDialogOpen, setDisableTotpDialogOpen] = React.useState(false)
  const [disableTotpPassword, setDisableTotpPassword] = React.useState('')
  const [disableTotpCode, setDisableTotpCode] = React.useState('')
  const [useBackupCode, setUseBackupCode] = React.useState(false)
  const [disablingTotp, setDisablingTotp] = React.useState(false)
  const [disableTotpErrors, setDisableTotpErrors] = React.useState<Record<string, string>>({})
  const [regeneratingCodes, setRegeneratingCodes] = React.useState(false)
  const [regenerateCodesDialogOpen, setRegenerateCodesDialogOpen] = React.useState(false)
  const [regenerateCode, setRegenerateCode] = React.useState('')
  const [regenerateCodeErrors, setRegenerateCodeErrors] = React.useState<Record<string, string>>({})
  const [newBackupCodes, setNewBackupCodes] = React.useState<string[]>([])

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

      // Load TOTP status
      try {
        const status = await totpApi.getStatus()
        setTotpStatus(status)
      } catch {
        // TOTP status not available
      }
    } catch {
      // Error handled by API client
    } finally {
      setLoading(false)
    }
  }

  const profileSummaryEntries = React.useMemo(
    () => getValidationSummaryEntries(profileErrors, ['username', 'email', 'email_verification_code', 'avatar_url']),
    [profileErrors]
  )

  const passwordSummaryEntries = React.useMemo(
    () => getValidationSummaryEntries(passwordErrors, ['currentPassword', 'newPassword', 'confirmPassword']),
    [passwordErrors]
  )

  const deleteSummaryEntries = React.useMemo(
    () => getValidationSummaryEntries(deleteErrors, ['password']),
    [deleteErrors]
  )

  const disableTotpSummaryEntries = React.useMemo(
    () => getValidationSummaryEntries(disableTotpErrors, ['password', 'code']),
    [disableTotpErrors]
  )

  const regenerateCodeSummaryEntries = React.useMemo(
    () => getValidationSummaryEntries(regenerateCodeErrors, ['code']),
    [regenerateCodeErrors]
  )

  const emailChanged =
    !!user && isValidEmail(profileData.email) && profileData.email !== user.email
  const requiresEmailVerification =
    emailChanged && siteSettings?.email_verification === true

  const handleSendEmailVerification = async () => {
    if (!emailChanged) return

    try {
      setSendingProfileVerification(true)
      await authApi.sendVerification(profileData.email, 'profile_email')
      setEmailVerificationSent(true)
      toast.success(t('emailVerificationSent'))
    } finally {
      setSendingProfileVerification(false)
    }
  }

  const handleSaveProfile = async () => {
    if (!user) return

    setProfileErrors({})

    if (!isValidEmail(profileData.email)) {
      setProfileErrors({ email: t('invalidEmail') })
      return
    }

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

    if (updateData.email !== undefined && requiresEmailVerification) {
      if (!emailVerificationSent) {
        const message = t('emailVerificationRequired')
        setProfileErrors({ email_verification_code: message })
        toast.warning(message)
        return
      }
      if (emailVerificationCode.length !== 6) {
        setProfileErrors({ email_verification_code: tAuth('verificationCodeInvalid') })
        return
      }
      updateData.email_verification_code = emailVerificationCode
    }

    try {
      setSavingProfile(true)
      const updatedUser = await usersApi.updateProfile(updateData, { silent: true })
      setUser(updatedUser)
      setEmailVerificationCode('')
      setEmailVerificationSent(false)
      toast.success(t('profileUpdated'))
    } catch (error) {
      const errors = normalizeValidationErrors(error)
      if (Object.keys(errors).length > 0) {
        setProfileErrors(errors)
      } else if (error instanceof ApiError) {
        if (error.code === 5002) {
          setProfileErrors({ username: error.message })
        } else if (error.code === 5003) {
          setProfileErrors({ email: error.message })
        } else if (error.code === 5005) {
          setProfileErrors({ email_verification_code: error.message })
        }
      }
    } finally {
      setSavingProfile(false)
    }
  }

  const handleChangePassword = async () => {
    const hasPassword =
      user?.auth_source === 'local' || (user?.sso_connections && user.sso_connections.length === 0)

    setPasswordErrors({})

    if (hasPassword && !passwordData.currentPassword) {
      setPasswordErrors({ currentPassword: t('currentPasswordRequired') })
      return
    }

    if (!passwordData.newPassword) {
      setPasswordErrors({ newPassword: t('newPasswordRequired') })
      return
    }
    if (passwordData.newPassword.length < 6) {
      setPasswordErrors({ newPassword: t('newPasswordTooShort') })
      return
    }
    if (passwordData.newPassword !== passwordData.confirmPassword) {
      setPasswordErrors({ confirmPassword: t('passwordMismatch') })
      return
    }

    try {
      setSavingPassword(true)

      if (!hasPassword) {
        await usersApi.updateProfile({
          password: passwordData.newPassword,
        }, { silent: true })
      } else {
        await usersApi.changePassword({
          current_password: passwordData.currentPassword,
          new_password: passwordData.newPassword,
        }, { silent: true })
      }

      toast.success(t('passwordUpdated'))
      setPasswordData({
        currentPassword: '',
        newPassword: '',
        confirmPassword: '',
      })
      await loadUser()
    } catch (error) {
      const errors = normalizeValidationErrors(error)
      if (Object.keys(errors).length > 0) {
        setPasswordErrors(
          Object.fromEntries(
            Object.entries(errors).map(([field, message]) => [field === 'new_password' ? 'newPassword' : field, message])
          )
        )
      } else if (error instanceof ApiError && error.code === 2003) {
        setPasswordErrors({ currentPassword: error.message })
      }
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
    setDeleteErrors({})

    if (!deletePassword) {
      setDeleteErrors({ password: t('currentPasswordRequired') })
      return
    }

    try {
      setDeleting(true)
      await usersApi.deleteAccount(deletePassword, { silent: true })
      toast.success(t('accountDeleted'))
      localStorage.removeItem('access_token')
      onOpenChange(false)
      router.push('/login')
    } catch (error) {
      if (error instanceof ApiError && error.code === 2003) {
        setDeleteErrors({ password: error.message })
      } else if (error instanceof ApiError) {
        setDeleteErrors({ __all__: error.message })
      }
    } finally {
      setDeleting(false)
    }
  }

  const handleSetupTotpSuccess = async () => {
    await loadUser()
  }

  const handleDisableTotp = async () => {
    setDisableTotpErrors({})

    if (!disableTotpPassword || !disableTotpCode) {
      setDisableTotpErrors({
        ...(disableTotpPassword ? {} : { password: t('currentPasswordRequired') }),
        ...(disableTotpCode ? {} : { code: t('disableTwoFactorCodeLabel') }),
      })
      return
    }

    const code = useBackupCode ? disableTotpCode.replace('-', '') : disableTotpCode

    if ((useBackupCode && code.length !== 8) || (!useBackupCode && code.length !== 6)) {
      setDisableTotpErrors({ code: tAuth('verificationCodeInvalid') })
      return
    }

    try {
      setDisablingTotp(true)
      await totpApi.disable(disableTotpPassword, code, useBackupCode, { silent: true })
      toast.success(t('twoFactorDisabledSuccess'))
      setDisableTotpDialogOpen(false)
      setDisableTotpPassword('')
      setDisableTotpCode('')
      setUseBackupCode(false)
      setDisableTotpErrors({})
      await loadUser()
    } catch (error) {
      if (error instanceof ApiError) {
        if (error.code === 2003) {
          setDisableTotpErrors({ password: error.message })
        } else if (error.code === 5311) {
          setDisableTotpErrors({ code: error.message })
        } else {
          setDisableTotpErrors({ __all__: error.message })
        }
      }
    } finally {
      setDisablingTotp(false)
    }
  }

  const handleRegenerateBackupCodes = async () => {
    setRegenerateCodeErrors({})

    if (!regenerateCode || regenerateCode.length !== 6) {
      setRegenerateCodeErrors({ code: tAuth('verificationCodeInvalid') })
      return
    }

    try {
      setRegeneratingCodes(true)
      const result = await totpApi.regenerateBackupCodes(regenerateCode, { silent: true })
      setNewBackupCodes(result.codes)
      toast.success(t('backupCodesRegeneratedSuccess'))
      setRegenerateCode('')
      setRegenerateCodeErrors({})
      await loadUser()
    } catch (error) {
      if (error instanceof ApiError) {
        if (error.code === 5311) {
          setRegenerateCodeErrors({ code: error.message })
        } else {
          setRegenerateCodeErrors({ __all__: error.message })
        }
      }
    } finally {
      setRegeneratingCodes(false)
    }
  }

  const handleDownloadBackupCodes = () => {
    const content = newBackupCodes.join('\n')
    const blob = new Blob([content], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'clouisle-backup-codes.txt'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }

  const handleCopyBackupCodes = async () => {
    await navigator.clipboard.writeText(newBackupCodes.join('\n'))
    toast.success(tAuth('setupStep4CodesCopied'))
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
              {profileSummaryEntries.length > 0 && (
                <div className="rounded-md border border-destructive/30 bg-destructive/5 p-3 space-y-1">
                  {profileSummaryEntries.map(([field, message]) => (
                    <FieldError key={field}>
                      {formatValidationSummaryMessage(field, message)}
                    </FieldError>
                  ))}
                </div>
              )}

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
                  onChange={(e) => {
                    setProfileData((prev) => ({ ...prev, username: e.target.value }))
                    setProfileErrors((prev) => clearValidationError(prev, 'username'))
                  }}
                  aria-invalid={!!profileErrors.username}
                />
                <FieldError>{profileErrors.username}</FieldError>
              </div>

              <div className="space-y-2">
                <Label htmlFor="email">{t('email')}</Label>
                <Input
                  id="email"
                  type="email"
                  placeholder={t('emailPlaceholder')}
                  value={profileData.email}
                  onChange={(e) => {
                    setProfileData((prev) => ({ ...prev, email: e.target.value }))
                    setEmailVerificationCode('')
                    setEmailVerificationSent(false)
                    setProfileErrors((prev) => clearValidationError(prev, 'email'))
                    setProfileErrors((prev) => clearValidationError(prev, 'email_verification_code'))
                  }}
                  required
                  aria-invalid={!!profileErrors.email}
                />
                <FieldError>{profileErrors.email}</FieldError>
                {requiresEmailVerification && (
                  <div className="rounded-lg border bg-muted/50 p-3 space-y-3">
                    <div className="flex items-center justify-between gap-3">
                      <div className="flex items-center gap-2 text-sm text-muted-foreground">
                        <Mail className="h-4 w-4" />
                        <span>{t('emailVerificationCode')}</span>
                      </div>
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={handleSendEmailVerification}
                        disabled={sendingProfileVerification}
                      >
                        {sendingProfileVerification && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                        {emailVerificationSent ? t('resendEmailVerification') : t('sendEmailVerification')}
                      </Button>
                    </div>
                    {!emailVerificationSent && (
                      <FieldError>{profileErrors.email_verification_code}</FieldError>
                    )}
                    {emailVerificationSent && (
                      <div className="space-y-2">
                        <InputOTP
                          maxLength={6}
                          value={emailVerificationCode}
                          onChange={(value) => {
                            setEmailVerificationCode(value)
                            setProfileErrors((prev) => clearValidationError(prev, 'email_verification_code'))
                          }}
                        >
                          <InputOTPGroup>
                            {Array.from({ length: 6 }).map((_, index) => (
                              <InputOTPSlot key={index} index={index} />
                            ))}
                          </InputOTPGroup>
                        </InputOTP>
                        <FieldError>{profileErrors.email_verification_code}</FieldError>
                      </div>
                    )}
                  </div>
                )}
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

              {/* Two-Factor Authentication */}
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-base">{t('twoFactorAuth')}</CardTitle>
                  <CardDescription>{t('twoFactorAuthDescription')}</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  {totpStatus?.enabled ? (
                    <>
                      <div className="flex items-center justify-between rounded-lg border bg-muted/50 p-3">
                        <div className="flex items-center gap-3">
                          <div className="rounded-full bg-green-100 p-2 dark:bg-green-950">
                            <KeyRound className="h-4 w-4 text-green-600 dark:text-green-400" />
                          </div>
                          <div>
                            <p className="text-sm font-medium">{t('twoFactorEnabled')}</p>
                            {totpStatus.enabled_at && (
                              <p className="text-xs text-muted-foreground">
                                {t('twoFactorEnabledAt')}: {formatDateTime(totpStatus.enabled_at)}
                              </p>
                            )}
                          </div>
                        </div>
                      </div>
                      <div className="flex items-center justify-between text-sm">
                        <span className="text-muted-foreground">
                          {t('backupCodesRemaining', { count: totpStatus.remaining_backup_codes })}
                        </span>
                      </div>
                      <div className="flex gap-2">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => setRegenerateCodesDialogOpen(true)}
                        >
                          {t('regenerateBackupCodes')}
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => setDisableTotpDialogOpen(true)}
                        >
                          {t('disableTwoFactor')}
                        </Button>
                      </div>
                    </>
                  ) : (
                    <>
                      <div className="flex items-center justify-between rounded-lg border p-3">
                        <div className="flex items-center gap-3">
                          <div className="rounded-full bg-muted p-2">
                            <KeyRound className="h-4 w-4 text-muted-foreground" />
                          </div>
                          <div>
                            <p className="text-sm font-medium">{t('twoFactorDisabled')}</p>
                            <p className="text-xs text-muted-foreground">
                              {t('setupTwoFactorDescription')}
                            </p>
                          </div>
                        </div>
                      </div>
                      <Button
                        variant="default"
                        size="sm"
                        onClick={() => setSetupWizardOpen(true)}
                      >
                        <Shield className="mr-2 h-4 w-4" />
                        {t('enableTwoFactor')}
                      </Button>
                    </>
                  )}
                </CardContent>
              </Card>

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
                  {passwordSummaryEntries.length > 0 && (
                    <div className="rounded-md border border-destructive/30 bg-destructive/5 p-3 space-y-1">
                      {passwordSummaryEntries.map(([field, message]) => (
                        <FieldError key={field}>
                          {formatValidationSummaryMessage(field, message)}
                        </FieldError>
                      ))}
                    </div>
                  )}

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
                        onChange={(e) => {
                          setPasswordData((prev) => ({ ...prev, currentPassword: e.target.value }))
                          setPasswordErrors((prev) => clearValidationError(prev, 'currentPassword'))
                        }}
                        aria-invalid={!!passwordErrors.currentPassword}
                      />
                      <FieldError>{passwordErrors.currentPassword}</FieldError>
                    </div>
                  )}
                  <div className="space-y-2">
                    <Label htmlFor="new">{t('newPassword')}</Label>
                    <Input
                      id="new"
                      type="password"
                      placeholder={t('newPasswordPlaceholder')}
                      value={passwordData.newPassword}
                      onChange={(e) => {
                        setPasswordData((prev) => ({ ...prev, newPassword: e.target.value }))
                        setPasswordErrors((prev) => clearValidationError(prev, 'newPassword'))
                      }}
                      aria-invalid={!!passwordErrors.newPassword}
                    />
                    <FieldError>{passwordErrors.newPassword}</FieldError>
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="confirm">{t('confirmNewPassword')}</Label>
                    <Input
                      id="confirm"
                      type="password"
                      placeholder={t('confirmNewPasswordPlaceholder')}
                      value={passwordData.confirmPassword}
                      onChange={(e) => {
                        setPasswordData((prev) => ({ ...prev, confirmPassword: e.target.value }))
                        setPasswordErrors((prev) => clearValidationError(prev, 'confirmPassword'))
                      }}
                      aria-invalid={!!passwordErrors.confirmPassword}
                    />
                    <FieldError>{passwordErrors.confirmPassword}</FieldError>
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
                        {deleteSummaryEntries.length > 0 && (
                          <div className="rounded-md border border-destructive/30 bg-destructive/5 p-3 space-y-1">
                            {deleteSummaryEntries.map(([field, message]) => (
                              <FieldError key={field}>
                                {formatValidationSummaryMessage(field, message)}
                              </FieldError>
                            ))}
                          </div>
                        )}
                        <div className="space-y-2">
                          <Label htmlFor="delete-password">{t('currentPassword')}</Label>
                          <Input
                            id="delete-password"
                            type="password"
                            placeholder={t('currentPasswordPlaceholder')}
                            value={deletePassword}
                            onChange={(e) => {
                              setDeletePassword(e.target.value)
                              setDeleteErrors((prev) => clearValidationError(prev, 'password'))
                            }}
                            aria-invalid={!!deleteErrors.password}
                          />
                          <FieldError>{deleteErrors.password}</FieldError>
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

      {/* TOTP Setup Wizard */}
      <TOTPSetupWizard
        open={setupWizardOpen}
        onOpenChange={setSetupWizardOpen}
        onSuccess={handleSetupTotpSuccess}
      />

      {/* Disable TOTP Dialog */}
      <AlertDialog open={disableTotpDialogOpen} onOpenChange={setDisableTotpDialogOpen}>
        <AlertDialogContent className="z-[60]" overlayClassName="z-[60]">
          <AlertDialogHeader>
            <AlertDialogTitle>{t('disableTwoFactorTitle')}</AlertDialogTitle>
            <AlertDialogDescription>{t('disableTwoFactorConfirm')}</AlertDialogDescription>
          </AlertDialogHeader>
          <div className="space-y-4">
            {disableTotpSummaryEntries.length > 0 && (
              <div className="rounded-md border border-destructive/30 bg-destructive/5 p-3 space-y-1">
                {disableTotpSummaryEntries.map(([field, message]) => (
                  <FieldError key={field}>
                    {formatValidationSummaryMessage(field, message)}
                  </FieldError>
                ))}
              </div>
            )}
            <div className="space-y-2">
              <Label htmlFor="disable-password">{t('disableTwoFactorPasswordLabel')}</Label>
              <Input
                id="disable-password"
                type="password"
                value={disableTotpPassword}
                onChange={(e) => {
                  setDisableTotpPassword(e.target.value)
                  setDisableTotpErrors((prev) => clearValidationError(prev, 'password'))
                }}
                aria-invalid={!!disableTotpErrors.password}
              />
              <FieldError>{disableTotpErrors.password}</FieldError>
            </div>
            <div className="space-y-2">
              <Label htmlFor="disable-code">
                {useBackupCode ? tAuth('backupCode') : t('disableTwoFactorCodeLabel')}
              </Label>
              {useBackupCode ? (
                <Input
                  id="disable-code"
                  type="text"
                  placeholder={tAuth('backupCodePlaceholder')}
                  value={disableTotpCode}
                  onChange={(e) => {
                    setDisableTotpCode(e.target.value)
                    setDisableTotpErrors((prev) => clearValidationError(prev, 'code'))
                  }}
                  maxLength={9}
                  aria-invalid={!!disableTotpErrors.code}
                />
              ) : (
                <div className="flex justify-center">
                  <InputOTP
                    maxLength={6}
                    value={disableTotpCode}
                    onChange={(value) => {
                      setDisableTotpCode(value)
                      setDisableTotpErrors((prev) => clearValidationError(prev, 'code'))
                    }}
                  >
                    <InputOTPGroup>
                      <InputOTPSlot index={0} />
                      <InputOTPSlot index={1} />
                      <InputOTPSlot index={2} />
                      <InputOTPSlot index={3} />
                      <InputOTPSlot index={4} />
                      <InputOTPSlot index={5} />
                    </InputOTPGroup>
                  </InputOTP>
                </div>
              )}
              <FieldError className="text-center">{disableTotpErrors.code}</FieldError>
              <div className="flex justify-center">
                <Button
                  type="button"
                  variant="link"
                  size="sm"
                  onClick={() => {
                    setUseBackupCode(!useBackupCode)
                    setDisableTotpCode('')
                    setDisableTotpErrors((prev) => clearValidationError(prev, 'code'))
                  }}
                  className="text-xs"
                >
                  {useBackupCode ? tAuth('useTOTPCode') : tAuth('useBackupCode')}
                </Button>
              </div>
            </div>
          </div>
          <AlertDialogFooter>
            <AlertDialogCancel
              onClick={() => {
                setDisableTotpPassword('')
                setDisableTotpCode('')
                setUseBackupCode(false)
              }}
            >
              {tCommon('cancel')}
            </AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              onClick={handleDisableTotp}
              disabled={
                disablingTotp ||
                !disableTotpPassword ||
                (useBackupCode
                  ? disableTotpCode.replace('-', '').length !== 8
                  : disableTotpCode.length !== 6
                )
              }
            >
              {disablingTotp && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {t('disableTwoFactor')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Regenerate Backup Codes Dialog */}
      <AlertDialog open={regenerateCodesDialogOpen} onOpenChange={setRegenerateCodesDialogOpen}>
        <AlertDialogContent className="z-[60]" overlayClassName="z-[60]">
          <AlertDialogHeader>
            <AlertDialogTitle>{t('regenerateBackupCodes')}</AlertDialogTitle>
            <AlertDialogDescription>
              {newBackupCodes.length > 0
                ? tAuth('setupStep4Description')
                : tAuth('setupStep3Description')}
            </AlertDialogDescription>
          </AlertDialogHeader>
          {newBackupCodes.length === 0 ? (
            <>
              {regenerateCodeSummaryEntries.length > 0 && (
                <div className="rounded-md border border-destructive/30 bg-destructive/5 p-3 space-y-1">
                  {regenerateCodeSummaryEntries.map(([field, message]) => (
                    <FieldError key={field}>
                      {formatValidationSummaryMessage(field, message)}
                    </FieldError>
                  ))}
                </div>
              )}
              <div className="space-y-2">
                <Label>{tAuth('verificationCode6Digit')}</Label>
                <div className="flex justify-center">
                  <InputOTP
                    maxLength={6}
                    value={regenerateCode}
                    onChange={(value) => {
                      setRegenerateCode(value)
                      setRegenerateCodeErrors((prev) => clearValidationError(prev, 'code'))
                    }}
                  >
                    <InputOTPGroup>
                      <InputOTPSlot index={0} />
                      <InputOTPSlot index={1} />
                      <InputOTPSlot index={2} />
                      <InputOTPSlot index={3} />
                      <InputOTPSlot index={4} />
                      <InputOTPSlot index={5} />
                    </InputOTPGroup>
                  </InputOTP>
                </div>
                <FieldError className="text-center">{regenerateCodeErrors.code}</FieldError>
              </div>
              <AlertDialogFooter>
                <AlertDialogCancel onClick={() => setRegenerateCode('')}>
                  {tCommon('cancel')}
                </AlertDialogCancel>
                <AlertDialogAction
                  onClick={handleRegenerateBackupCodes}
                  disabled={regeneratingCodes || regenerateCode.length !== 6}
                >
                  {regeneratingCodes && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                  {t('regenerateBackupCodes')}
                </AlertDialogAction>
              </AlertDialogFooter>
            </>
          ) : (
            <>
              <div className="rounded-lg border bg-muted/50 p-4">
                <div className="grid grid-cols-2 gap-2 font-mono text-sm">
                  {newBackupCodes.map((code, index) => (
                    <div key={index} className="rounded bg-background p-2 text-center">
                      {code}
                    </div>
                  ))}
                </div>
              </div>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  className="flex-1"
                  onClick={handleDownloadBackupCodes}
                >
                  <Download className="mr-2 h-4 w-4" />
                  {tAuth('setupStep4Download')}
                </Button>
                <Button
                  variant="outline"
                  className="flex-1"
                  onClick={handleCopyBackupCodes}
                >
                  <Copy className="mr-2 h-4 w-4" />
                  {tAuth('setupStep4Copy')}
                </Button>
              </div>
              <AlertDialogFooter>
                <AlertDialogAction
                  onClick={() => {
                    setRegenerateCodesDialogOpen(false)
                    setNewBackupCodes([])
                  }}
                >
                  {tCommon('close')}
                </AlertDialogAction>
              </AlertDialogFooter>
            </>
          )}
        </AlertDialogContent>
      </AlertDialog>
    </Dialog>
  )
}
