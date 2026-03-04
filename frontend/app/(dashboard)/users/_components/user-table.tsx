'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { MoreHorizontal, Pencil, Trash2, UserCheck, UserX, Link as LinkIcon } from 'lucide-react'
import { toast } from 'sonner'
import { usersApi, type User } from '@/lib/api/admin/users'
import { Badge } from '@/components/ui/badge'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'

interface UserTableProps {
  users: User[]
  onEdit?: (user: User) => void
  onDelete?: (user: User) => void
  onStatusChange?: (user: User) => void
}

export function UserTable({ users, onEdit, onDelete, onStatusChange }: UserTableProps) {
  const t = useTranslations('users')

  return (
    <div className="rounded-md border">
      <table className="w-full">
        <thead>
          <tr className="border-b bg-muted/50">
            <th className="h-12 px-4 text-left align-middle font-medium">{t('allUsers')}</th>
            <th className="h-12 px-4 text-left align-middle font-medium">Email</th>
            <th className="h-12 px-4 text-left align-middle font-medium">{t('status')}</th>
            <th className="h-12 px-4 text-left align-middle font-medium">{t('createdAt')}</th>
            <th className="h-12 px-4 text-right align-middle font-medium w-[70px]"></th>
          </tr>
        </thead>
        <tbody>
          {users.map((user) => (
            <UserTableRow
              key={user.id}
              user={user}
              onEdit={onEdit}
              onDelete={onDelete}
              onStatusChange={onStatusChange}
            />
          ))}
          {users.length === 0 && (
            <tr>
              <td colSpan={5} className="h-24 text-center text-muted-foreground">
                {t('noUsers')}
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  )
}

interface UserTableRowProps {
  user: User
  onEdit?: (user: User) => void
  onDelete?: (user: User) => void
  onStatusChange?: (user: User) => void
}

function UserTableRow({ user, onEdit, onDelete, onStatusChange }: UserTableRowProps) {
  const t = useTranslations('users')
  const commonT = useTranslations('common')
  const [isChangingStatus, setIsChangingStatus] = React.useState(false)

  const handleToggleStatus = async () => {
    setIsChangingStatus(true)
    try {
      if (user.is_active) {
        await usersApi.deactivateUser(user.id)
        toast.success(t('userDeactivated'))
      } else {
        await usersApi.activateUser(user.id)
        toast.success(t('userActivated'))
      }
      onStatusChange?.(user)
    } catch {
      // 错误已由 API 客户端处理
    } finally {
      setIsChangingStatus(false)
    }
  }

  const formatDate = (dateString: string) => {
    const d = new Date(dateString)
    const year = d.getFullYear()
    const month = String(d.getMonth() + 1).padStart(2, '0')
    const day = String(d.getDate()).padStart(2, '0')
    const hour = String(d.getHours()).padStart(2, '0')
    const minute = String(d.getMinutes()).padStart(2, '0')
    return `${year}/${month}/${day} ${hour}:${minute}`
  }

  // 获取用户名首字母
  const getInitials = (name: string) => {
    return name
      .split(' ')
      .map((n) => n[0])
      .join('')
      .toUpperCase()
      .slice(0, 2)
  }

  return (
    <tr className="border-b hover:bg-muted/50">
      <td className="p-4">
        <div className="flex items-center gap-3">
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-muted text-sm font-medium">
            {getInitials(user.username)}
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-medium">{user.username}</span>
              {user.is_superuser && (
                <Badge variant="secondary" className="ml-2">{t('superuser')}</Badge>
              )}
              {/* SSO Connection Indicators */}
              {user.sso_connections && user.sso_connections.length > 0 && (
                <TooltipProvider>
                  <div className="flex items-center gap-1">
                    {user.sso_connections.map((conn) => (
                      <Tooltip key={conn.id}>
                        <TooltipTrigger>
                          {conn.provider_icon_url ? (
                            <img
                              src={conn.provider_icon_url}
                              alt={conn.provider_display_name}
                              className="h-4 w-4 rounded"
                            />
                          ) : (
                            <LinkIcon className="h-4 w-4 text-muted-foreground" />
                          )}
                        </TooltipTrigger>
                        <TooltipContent>
                          <div className="text-xs">
                            <p className="font-medium">{conn.provider_display_name}</p>
                            {conn.provider_email && (
                              <p className="text-muted-foreground">{conn.provider_email}</p>
                            )}
                          </div>
                        </TooltipContent>
                      </Tooltip>
                    ))}
                  </div>
                </TooltipProvider>
              )}
            </div>
          </div>
        </div>
      </td>
      <td className="p-4 text-muted-foreground">{user.email}</td>
      <td className="p-4">
        <Badge variant={user.is_active ? 'default' : 'outline'}>
          {t(user.is_active ? 'active' : 'inactive')}
        </Badge>
      </td>
      <td className="p-4 text-muted-foreground">{formatDate(user.created_at)}</td>
      <td className="p-4 text-right">
        <DropdownMenu>
          <DropdownMenuTrigger className="ring-offset-background focus-visible:ring-ring data-[state=open]:bg-accent inline-flex h-8 w-8 items-center justify-center rounded-md hover:bg-accent focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:outline-none disabled:pointer-events-none disabled:opacity-50">
            <MoreHorizontal className="h-4 w-4" />
            <span className="sr-only">{t('common.openMenu')}</span>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={() => onEdit?.(user)}>
              <Pencil className="mr-2 h-4 w-4" />
              {commonT('edit')}
            </DropdownMenuItem>

            {!user.is_superuser && (
              <>
                <DropdownMenuItem
                  onClick={handleToggleStatus}
                  disabled={isChangingStatus}
                >
                  {user.is_active ? (
                    <>
                      <UserX className="mr-2 h-4 w-4" />
                      {t('deactivate')}
                    </>
                  ) : (
                    <>
                      <UserCheck className="mr-2 h-4 w-4" />
                      {t('activate')}
                    </>
                  )}
                </DropdownMenuItem>

                <DropdownMenuSeparator />

                <DropdownMenuItem
                  onClick={() => onDelete?.(user)}
                  className="text-destructive focus:text-destructive"
                >
                  <Trash2 className="mr-2 h-4 w-4" />
                  {commonT('delete')}
                </DropdownMenuItem>
              </>
            )}
          </DropdownMenuContent>
        </DropdownMenu>
      </td>
    </tr>
  )
}

export type { User }
