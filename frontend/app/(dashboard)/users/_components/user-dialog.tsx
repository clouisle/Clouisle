'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { toast } from 'sonner'
import { usersApi, type UserCreateData, type UserUpdateData, type User } from '@/lib/api/admin/users'
import { ssoApi } from '@/lib/api/admin/sso'
import type { SSOConnection } from '@/lib/api/auth'
import { rolesApi, type Role } from '@/lib/api/admin/roles'
import { ApiError } from '@/lib/api'
import { isValidEmail } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
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
import { Link as LinkIcon, Loader2, Unlink } from 'lucide-react'

interface UserDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  user?: User | null // 编辑时传入用户，创建时为 null
  onSuccess?: (user: User) => void
}

export function UserDialog({ open, onOpenChange, user, onSuccess }: UserDialogProps) {
  const t = useTranslations('users')
  const commonT = useTranslations('common')
  const authT = useTranslations('auth')
  const tSSO = useTranslations('sso')

  const isEditing = !!user

  const [currentUser, setCurrentUser] = React.useState<User | null>(null)
  const [roles, setRoles] = React.useState<Role[]>([])
  const [selectedRoles, setSelectedRoles] = React.useState<string[]>([])
  const [formData, setFormData] = React.useState({
    username: '',
    email: '',
    password: '',
    confirmPassword: '',
    is_active: true,
  })
  const [fieldErrors, setFieldErrors] = React.useState<Record<string, string>>({})
  const [isSubmitting, setIsSubmitting] = React.useState(false)
  const [disconnectingId, setDisconnectingId] = React.useState<string | null>(null)

  // 加载角色列表
  React.useEffect(() => {
    const fetchRoles = async () => {
      try {
        const data = await rolesApi.getRoles(1, 100)
        setRoles(data.items)
      } catch {
        // 获取角色失败
      }
    }
    fetchRoles()
  }, [])

  // 当 user 改变或 dialog 打开时重置表单
  React.useEffect(() => {
    if (open) {
      setCurrentUser(user ?? null)
      if (user) {
        setFormData({
          username: user.username,
          email: user.email,
          password: '',
          confirmPassword: '',
          is_active: user.is_active,
        })
        // 设置用户当前的角色
        setSelectedRoles(user.roles?.map(r => r.name) || [])
      } else {
        setFormData({
          username: '',
          email: '',
          password: '',
          confirmPassword: '',
          is_active: true,
        })
        setSelectedRoles([])
      }
      setFieldErrors({})
    }
  }, [open, user])

  const handleDisconnect = async (connectionId: string) => {
    if (!user) return
    try {
      setDisconnectingId(connectionId)
      await ssoApi.adminDisconnectConnection(connectionId)
      toast.success(tSSO('disconnectSuccess'))
      const updated = await usersApi.getUser(user.id)
      setCurrentUser(updated)
      onSuccess?.(updated)
    } catch {
      // 错误已由 API 客户端处理
    } finally {
      setDisconnectingId(null)
    }
  }
  
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setFieldErrors({})
    
    // 验证邮箱格式
    if (!isValidEmail(formData.email)) {
      setFieldErrors({ email: authT('invalidEmail') })
      return
    }

    // 验证密码
    if (!isEditing && formData.password.length < 6) {
      setFieldErrors({ password: authT('passwordTooShort') })
      return
    }
    
    if (formData.password && formData.password !== formData.confirmPassword) {
      setFieldErrors({ confirmPassword: authT('passwordMismatch') })
      return
    }
    
    setIsSubmitting(true)
    
    try {
      let result: User
      
      if (isEditing && user) {
        // 编辑用户
        const updateData: UserUpdateData = {
          email: formData.email,
          is_active: formData.is_active,
          roles: selectedRoles,
        }
        if (formData.password) {
          updateData.password = formData.password
        }
        result = await usersApi.updateUser(user.id, updateData)
        toast.success(t('userUpdated'))
      } else {
        // 创建用户
        const createData: UserCreateData = {
          username: formData.username,
          email: formData.email,
          password: formData.password,
          is_active: formData.is_active,
        }
        result = await usersApi.createUser(createData)
        toast.success(t('userCreated'))
      }
      
      onSuccess?.(result)
      onOpenChange(false)
    } catch (error) {
      if (error instanceof ApiError && error.isValidationError()) {
        const errors = error.getFieldErrors()
        // 处理密码验证错误（后端返回的是数组格式）
        if (error.data && typeof error.data === 'object' && 'errors' in error.data) {
          const errorData = error.data as { errors: string[] }
          if (Array.isArray(errorData.errors) && errorData.errors.length > 0) {
            // 将密码错误数组转换为可读的错误消息
            const passwordErrors = errorData.errors.map(err => {
              // 处理带参数的错误消息，如 "password_min_length:8"
              const [key, param] = err.split(':')
              if (key === 'password_min_length') {
                return authT('passwordMinLength', { length: param })
              } else if (key === 'password_require_uppercase') {
                return authT('passwordRequireUppercase')
              } else if (key === 'password_require_number') {
                return authT('passwordRequireNumber')
              } else if (key === 'password_require_special') {
                return authT('passwordRequireSpecial')
              } else if (key === 'password_recently_used') {
                return authT('passwordRecentlyUsed')
              }
              return err
            }).join('; ')
            setFieldErrors({ password: passwordErrors })
            return
          }
        }
        setFieldErrors(errors)
      }
    } finally {
      setIsSubmitting(false)
    }
  }
  
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[425px]">
        <DialogHeader>
          <DialogTitle>{isEditing ? t('editUser') : t('createUser')}</DialogTitle>
          <DialogDescription>
            {isEditing ? t('editUserDescription') : t('createUserDescription')}
          </DialogDescription>
        </DialogHeader>
        
        <form onSubmit={handleSubmit} className="grid gap-4">
          <div className="grid gap-2">
            <Label htmlFor="username">{authT('username')}</Label>
            <Input
              id="username"
              value={formData.username}
              onChange={(e) => setFormData({ ...formData, username: e.target.value })}
              disabled={isEditing}
              required={!isEditing}
              autoFocus={!isEditing}
            />
            {fieldErrors.username && (
              <p className="text-sm text-destructive">{fieldErrors.username}</p>
            )}
          </div>
          
          <div className="grid gap-2">
            <Label htmlFor="email">{authT('email')}</Label>
            <Input
              id="email"
              type="email"
              value={formData.email}
              onChange={(e) => setFormData({ ...formData, email: e.target.value })}
              required
              autoFocus={isEditing}
            />
            {fieldErrors.email && (
              <p className="text-sm text-destructive">{fieldErrors.email}</p>
            )}
          </div>
          
          <div className="grid gap-2">
            <Label htmlFor="password">
              {authT('password')}
              {isEditing && <span className="text-muted-foreground ml-1">({t('leaveBlankToKeep')})</span>}
            </Label>
            <Input
              id="password"
              type="password"
              value={formData.password}
              onChange={(e) => setFormData({ ...formData, password: e.target.value })}
              required={!isEditing}
              minLength={6}
            />
            {fieldErrors.password && (
              <p className="text-sm text-destructive">{fieldErrors.password}</p>
            )}
          </div>
          
          <div className="grid gap-2">
            <Label htmlFor="confirmPassword">{authT('confirmPassword')}</Label>
            <Input
              id="confirmPassword"
              type="password"
              value={formData.confirmPassword}
              onChange={(e) => setFormData({ ...formData, confirmPassword: e.target.value })}
              required={!isEditing && !!formData.password}
            />
            {fieldErrors.confirmPassword && (
              <p className="text-sm text-destructive">{fieldErrors.confirmPassword}</p>
            )}
          </div>

          {isEditing && currentUser?.sso_connections && currentUser.sso_connections.length > 0 && (
            <div className="grid gap-2">
              <Label>{tSSO('connectedAccounts')}</Label>
              <div className="space-y-2">
                {currentUser.sso_connections.map((connection: SSOConnection) => (
                  <div
                    key={connection.id}
                    className="flex items-center justify-between rounded-md border px-3 py-2"
                  >
                    <div className="flex items-center gap-3">
                      {connection.provider_icon_url ? (
                        <img
                          src={connection.provider_icon_url}
                          alt={connection.provider_display_name}
                          className="h-6 w-6 rounded"
                        />
                      ) : (
                        <LinkIcon className="h-5 w-5 text-muted-foreground" />
                      )}
                      <div>
                        <div className="text-sm font-medium">{connection.provider_display_name}</div>
                        {connection.provider_email && (
                          <div className="text-xs text-muted-foreground">{connection.provider_email}</div>
                        )}
                      </div>
                    </div>
                    <AlertDialog>
                      <AlertDialogTrigger
                        render={(props) => (
                          <Button
                            {...props}
                            type="button"
                            variant="outline"
                            size="sm"
                            disabled={disconnectingId === connection.id}
                          >
                            {disconnectingId === connection.id ? (
                              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                            ) : (
                              <Unlink className="mr-2 h-4 w-4" />
                            )}
                            {tSSO('disconnect')}
                          </Button>
                        )}
                      />
                      <AlertDialogContent>
                        <AlertDialogHeader>
                          <AlertDialogTitle>{tSSO('disconnect')}</AlertDialogTitle>
                          <AlertDialogDescription>
                            {tSSO('disconnectConfirm')}
                          </AlertDialogDescription>
                        </AlertDialogHeader>
                        <AlertDialogFooter>
                          <AlertDialogCancel>{commonT('cancel')}</AlertDialogCancel>
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
              </div>
            </div>
          )}

          {/* 角色选择 */}
          {isEditing && roles.length > 0 && (
            <div className="grid gap-2">
              <Label>{t('role')}</Label>
              <div className="space-y-2 max-h-40 overflow-y-auto rounded-md border p-3">
                {roles.map((role) => (
                  <div key={role.id} className="flex items-center space-x-2">
                    <Checkbox
                      id={`role-${role.id}`}
                      checked={selectedRoles.includes(role.name)}
                      onCheckedChange={(checked) => {
                        if (checked) {
                          setSelectedRoles([...selectedRoles, role.name])
                        } else {
                          setSelectedRoles(selectedRoles.filter(r => r !== role.name))
                        }
                      }}
                    />
                    <label
                      htmlFor={`role-${role.id}`}
                      className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70 cursor-pointer"
                    >
                      {role.name}
                      {role.description && (
                        <span className="ml-2 text-xs text-muted-foreground">
                          ({role.description})
                        </span>
                      )}
                    </label>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="flex items-center justify-between">
            <Label htmlFor="is_active">{t('active')}</Label>
            <Switch
              id="is_active"
              checked={formData.is_active}
              onCheckedChange={(checked) => setFormData({ ...formData, is_active: checked })}
            />
          </div>
          
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={isSubmitting}
            >
              {commonT('cancel')}
            </Button>
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting
                ? commonT('loading')
                : isEditing
                  ? commonT('save')
                  : commonT('create')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
