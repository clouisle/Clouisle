'use client'

import * as React from 'react'
import Link from 'next/link'
import Image from 'next/image'
import { usePathname, useRouter } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { toast } from 'sonner'
import {
  LayoutDashboard,
  Users,
  Shield,
  Key,
  KeyRound,
  Settings,
  HelpCircle,
  LogOut,
  ChevronUp,
  UsersRound,
  Bot,
  Database,
  AppWindow,
  Wrench,
  Activity,
  FileText,
  Bell,
  User,
  Brain,
} from 'lucide-react'
import { authApi, type User as UserType } from '@/lib/api'
import { useSiteSettings } from '@/contexts/site-settings-context'
import { usePermissions } from '@/hooks/use-permissions'
import { ROUTE_PERMISSION_MAP } from '@/lib/route-permissions'
import { SettingsDialog } from '@/components/settings-dialog'
import { DefaultSiteIcon } from '@/components/default-site-icon'
import { getBrandingVisibility } from '@/lib/theme-config'

import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from '@/components/ui/sidebar'
import type { SidebarVariant } from '@/hooks/use-settings'

type CollapsibleVariant = 'offExamples' | 'icon' | 'none'
type SideVariant = 'left' | 'right'

interface AppSidebarProps {
  variant?: SidebarVariant
  collapsible?: CollapsibleVariant
  side?: SideVariant
}

export function AppSidebar({ variant = 'inset', collapsible = 'icon', side = 'left' }: AppSidebarProps) {
  const t = useTranslations('nav')
  const tPlatform = useTranslations('platform')
  const pathname = usePathname()
  const router = useRouter()
  const [user, setUser] = React.useState<UserType | null>(null)
  const [profileOpen, setProfileOpen] = React.useState(false)
  const { settings: siteSettings } = useSiteSettings()
  const { hasPermission, canAccessDashboard } = usePermissions()

  React.useEffect(() => {
    const fetchUser = async () => {
      try {
        const userData = await authApi.getCurrentUser({ skipAuthRedirect: true })
        setUser(userData)
      } catch {
        // 获取用户信息失败，可能未登录
      }
    }
    fetchUser()
  }, [])

  // 获取用户名首字母作为头像占位
  const getInitials = (name: string) => {
    return name
      .split(' ')
      .map((n) => n[0])
      .join('')
      .toUpperCase()
      .slice(0, 2)
  }

  const handleLogout = async () => {
    try {
      // 调用后端注销接口，将 token 加入黑名单
      await authApi.logout()
    } catch {
      // 即使后端注销失败，也继续客户端清理
    }
    // 清除 token
    localStorage.removeItem('access_token')
    // 显示提示
    toast.success(t('logoutSuccess'))
    // 跳转到登录页
    router.push('/login')
  }

  const generalItems = [
    {
      title: t('dashboard'),
      url: '/dashboard',
      icon: LayoutDashboard,
      permission: ROUTE_PERMISSION_MAP['/dashboard'],
    },
    {
      title: t('teams'),
      url: '/teams',
      icon: UsersRound,
      permission: ROUTE_PERMISSION_MAP['/teams'],
    },
    {
      title: t('knowledgeBases'),
      url: '/knowledge-bases',
      icon: Database,
      permission: ROUTE_PERMISSION_MAP['/knowledge-bases'],
    },
    {
      title: t('activities'),
      url: '/activities',
      icon: Activity,
      permission: ROUTE_PERMISSION_MAP['/activities'],
    },
  ]

  const systemItems = [
    {
      title: t('users'),
      url: '/users',
      icon: Users,
      permission: ROUTE_PERMISSION_MAP['/users'],
    },
    {
      title: t('roles'),
      url: '/roles',
      icon: Shield,
      permission: ROUTE_PERMISSION_MAP['/roles'],
    },
    {
      title: t('permissions'),
      url: '/permissions',
      icon: Key,
      permission: ROUTE_PERMISSION_MAP['/permissions'],
    },
  ]

  const resourceItems = [
    {
      title: t('models'),
      url: '/models',
      icon: Bot,
      permission: ROUTE_PERMISSION_MAP['/models'],
    },
    {
      title: t('apps'),
      url: '/apps',
      icon: AppWindow,
      permission: ROUTE_PERMISSION_MAP['/apps'],
    },
    {
      title: t('capabilities'),
      url: '/capabilities',
      icon: Wrench,
      permission: ROUTE_PERMISSION_MAP['/capabilities'],
    },
    {
      title: t('apiKeys'),
      url: '/api-keys',
      icon: KeyRound,
      permission: ROUTE_PERMISSION_MAP['/api-keys'],
    },
    {
      title: t('memories'),
      url: '/memories',
      icon: Brain,
      permission: ROUTE_PERMISSION_MAP['/memories'],
    },
  ]

  const monitoringItems = [
    {
      title: t('observability'),
      url: '/dashboard/observability',
      icon: Activity,
      permission: ROUTE_PERMISSION_MAP['/dashboard/observability'],
    },
    {
      title: t('notifications'),
      url: '/notifications',
      icon: Bell,
      permission: ROUTE_PERMISSION_MAP['/notifications'],
    },
    {
      title: t('auditLogs'),
      url: '/audit-logs',
      icon: FileText,
      permission: ROUTE_PERMISSION_MAP['/audit-logs'],
    },
  ]

  const settingsItems = [
    {
      title: t('siteSettings'),
      url: '/site-settings',
      icon: Settings,
      permission: ROUTE_PERMISSION_MAP['/site-settings'],
    },
    {
      title: t('helpCenter'),
      url: '/help',
      icon: HelpCircle,
      permission: null, // No permission required
    },
  ]

  // Filter menu items based on permissions
  const filteredGeneralItems = generalItems.filter(
    (item) => !item.permission || hasPermission(item.permission)
  )
  const filteredSystemItems = systemItems.filter(
    (item) => !item.permission || hasPermission(item.permission)
  )
  const filteredResourceItems = resourceItems.filter(
    (item) => !item.permission || hasPermission(item.permission)
  )
  const filteredMonitoringItems = monitoringItems.filter(
    (item) => !item.permission || hasPermission(item.permission)
  )
  const filteredSettingsItems = settingsItems.filter(
    (item) => !item.permission || hasPermission(item.permission)
  )

  const isActive = (url: string) => (url === '/dashboard' ? pathname === url : pathname.startsWith(url))
  const { showIcon: showBrandIcon, showName: showBrandName } = getBrandingVisibility(
    siteSettings.theme_branding_display
  )

  return (
    <Sidebar variant={variant} collapsible={collapsible} side={side}>
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <Link href="/dashboard">
              <SidebarMenuButton size="lg" tooltip={siteSettings.site_name || 'Clouisle'}>
                {showBrandIcon && (
                  <div className={`flex aspect-square size-8 items-center justify-center rounded-lg overflow-hidden ${siteSettings.site_icon ? 'bg-primary text-primary-foreground' : ''}`}>
                    {siteSettings.site_icon ? (
                      <Image
                        src={siteSettings.site_icon}
                        alt={siteSettings.site_name}
                        width={32}
                        height={32}
                        className="size-full object-cover"
                        unoptimized
                      />
                    ) : (
                      <DefaultSiteIcon width={32} height={32} className="size-full" />
                    )}
                  </div>
                )}
                {showBrandName && (
                  <div className="flex flex-col gap-0.5 leading-none group-data-[collapsible=icon]:hidden">
                    <span className="font-semibold">{siteSettings.site_name || 'Clouisle'}</span>
                    <span className="text-xs text-muted-foreground">{tPlatform('admin')}</span>
                  </div>
                )}
                {!showBrandIcon && !showBrandName && (
                  <div className="flex flex-col gap-0.5 leading-none group-data-[collapsible=icon]:hidden">
                    <span className="text-xs text-muted-foreground">{tPlatform('admin')}</span>
                  </div>
                )}
              </SidebarMenuButton>
            </Link>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>

      <SidebarContent>
        {/* General */}
        {filteredGeneralItems.length > 0 && (
          <SidebarGroup>
            <SidebarGroupLabel>{t('general')}</SidebarGroupLabel>
            <SidebarGroupContent>
              <SidebarMenu>
                {filteredGeneralItems.map((item) => (
                  <SidebarMenuItem key={item.title}>
                    <Link href={item.url}>
                      <SidebarMenuButton isActive={isActive(item.url)}>
                        <item.icon />
                        <span>{item.title}</span>
                      </SidebarMenuButton>
                    </Link>
                  </SidebarMenuItem>
                ))}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        )}

        {/* System - only show if user has dashboard access and there are visible items */}
        {canAccessDashboard && filteredSystemItems.length > 0 && (
          <SidebarGroup>
            <SidebarGroupLabel>{t('system')}</SidebarGroupLabel>
            <SidebarGroupContent>
              <SidebarMenu>
                {filteredSystemItems.map((item) => (
                  <SidebarMenuItem key={item.title}>
                    <Link href={item.url}>
                      <SidebarMenuButton isActive={isActive(item.url)}>
                        <item.icon />
                        <span>{item.title}</span>
                      </SidebarMenuButton>
                    </Link>
                  </SidebarMenuItem>
                ))}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        )}

        {/* Resources - only show if user has dashboard access and there are visible items */}
        {canAccessDashboard && filteredResourceItems.length > 0 && (
          <SidebarGroup>
            <SidebarGroupLabel>{t('resources')}</SidebarGroupLabel>
            <SidebarGroupContent>
              <SidebarMenu>
                {filteredResourceItems.map((item) => (
                  <SidebarMenuItem key={item.title}>
                    <Link href={item.url}>
                      <SidebarMenuButton isActive={isActive(item.url)}>
                        <item.icon />
                        <span>{item.title}</span>
                      </SidebarMenuButton>
                    </Link>
                  </SidebarMenuItem>
                ))}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        )}

        {/* Monitoring - only show if user has dashboard access and there are visible items */}
        {canAccessDashboard && filteredMonitoringItems.length > 0 && (
          <SidebarGroup>
            <SidebarGroupLabel>{t('monitoring')}</SidebarGroupLabel>
            <SidebarGroupContent>
              <SidebarMenu>
                {filteredMonitoringItems.map((item) => (
                  <SidebarMenuItem key={item.title}>
                    <Link href={item.url}>
                      <SidebarMenuButton isActive={isActive(item.url)}>
                        <item.icon />
                        <span>{item.title}</span>
                      </SidebarMenuButton>
                    </Link>
                  </SidebarMenuItem>
                ))}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        )}

        {/* Settings */}
        {filteredSettingsItems.length > 0 && (
          <SidebarGroup>
            <SidebarGroupLabel>{t('settings')}</SidebarGroupLabel>
            <SidebarGroupContent>
              <SidebarMenu>
                {filteredSettingsItems.map((item) => (
                  <SidebarMenuItem key={item.title}>
                    <Link href={item.url}>
                      <SidebarMenuButton isActive={isActive(item.url)}>
                        <item.icon />
                        <span>{item.title}</span>
                      </SidebarMenuButton>
                    </Link>
                  </SidebarMenuItem>
                ))}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        )}
      </SidebarContent>

      <SidebarFooter>
        <SidebarMenu>
          <SidebarMenuItem>
            <DropdownMenu>
              <DropdownMenuTrigger 
                render={(props) => (
                  <SidebarMenuButton 
                    {...props} 
                    size="lg" 
                    tooltip={user?.username || 'User'}
                  >
                    <Avatar className="h-8 w-8 rounded-lg">
                      <AvatarImage src={user?.avatar_url || undefined} alt={user?.username || 'User'} />
                      <AvatarFallback className="rounded-lg">
                        {user ? getInitials(user.username) : 'U'}
                      </AvatarFallback>
                    </Avatar>
                    <div className="grid flex-1 text-left text-sm leading-tight group-data-[collapsible=icon]:hidden">
                      <span className="truncate font-semibold">{user?.username || '...'}</span>
                      <span className="truncate text-xs text-muted-foreground">
                        {user?.email || '...'}
                      </span>
                    </div>
                    <ChevronUp className="ml-auto size-4 group-data-[collapsible=icon]:hidden" />
                  </SidebarMenuButton>
                )}
              />
              <DropdownMenuContent
                className="w-[--radix-dropdown-menu-trigger-width] min-w-56 rounded-lg"
                side="top"
                align="start"
                sideOffset={4}
              >
                <Link href="/app">
                  <DropdownMenuItem>
                    <AppWindow className="mr-2 h-4 w-4" />
                    {t('workspace')}
                  </DropdownMenuItem>
                </Link>
                <DropdownMenuItem onClick={() => setProfileOpen(true)}>
                  <User className="mr-2 h-4 w-4" />
                  {t('profile')}
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={handleLogout}>
                  <LogOut className="mr-2 h-4 w-4" />
                  {t('logout')}
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>

      {/* Profile Settings Dialog */}
      <SettingsDialog open={profileOpen} onOpenChange={setProfileOpen} />
    </Sidebar>
  )
}
