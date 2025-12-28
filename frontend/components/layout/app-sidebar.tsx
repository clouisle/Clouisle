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
  Settings,
  HelpCircle,
  LogOut,
  ChevronUp,
  UsersRound,
  Globe,
  Bot,
  Database,
  AppWindow,
  MessageSquare,
} from 'lucide-react'
import { authApi, type User } from '@/lib/api'
import { useSiteSettings } from '@/contexts/site-settings-context'

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
  const pathname = usePathname()
  const router = useRouter()
  const [user, setUser] = React.useState<User | null>(null)
  const { settings: siteSettings } = useSiteSettings()

  React.useEffect(() => {
    const fetchUser = async () => {
      try {
        const userData = await authApi.getCurrentUser()
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
    },
    {
      title: t('teams'),
      url: '/teams',
      icon: UsersRound,
    },
    {
      title: t('knowledgeBases'),
      url: '/knowledge-bases',
      icon: Database,
    },
    {
      title: t('conversations'),
      url: '/conversations',
      icon: MessageSquare,
    },
  ]

  const adminItems = [
    {
      title: t('users'),
      url: '/users',
      icon: Users,
    },
    {
      title: t('roles'),
      url: '/roles',
      icon: Shield,
    },
    {
      title: t('permissions'),
      url: '/permissions',
      icon: Key,
    },
    {
      title: t('models'),
      url: '/models',
      icon: Bot,
    },
  ]

  const otherItems = [
    {
      title: t('siteSettings'),
      url: '/site-settings',
      icon: Settings,
    },
    {
      title: t('helpCenter'),
      url: '/help',
      icon: HelpCircle,
    },
  ]

  const isActive = (url: string) => pathname.startsWith(url)

  return (
    <Sidebar variant={variant} collapsible={collapsible} side={side}>
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <Link href="/dashboard">
              <SidebarMenuButton size="lg" tooltip={siteSettings.site_name || 'Clouisle'}>
                <div className="flex aspect-square size-8 items-center justify-center rounded-lg bg-primary text-primary-foreground overflow-hidden">
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
                    <Globe className="size-5" />
                  )}
                </div>
                <div className="flex flex-col gap-0.5 leading-none group-data-[collapsible=icon]:hidden">
                  <span className="font-semibold">{siteSettings.site_name || 'Clouisle'}</span>
                  <span className="text-xs text-muted-foreground">Admin Panel</span>
                </div>
              </SidebarMenuButton>
            </Link>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>

      <SidebarContent>
        {/* General */}
        <SidebarGroup>
          <SidebarGroupLabel>{t('general')}</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {generalItems.map((item) => (
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

        {/* Admin */}
        <SidebarGroup>
          <SidebarGroupLabel>{t('admin')}</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {adminItems.map((item) => (
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

        {/* Other */}
        <SidebarGroup>
          <SidebarGroupLabel>{t('other')}</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {otherItems.map((item) => (
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
                      <AvatarImage src={user?.avatar_url || ''} alt={user?.username || 'User'} />
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
                <Link href="/settings/profile">
                  <DropdownMenuItem>
                    <Settings className="mr-2 h-4 w-4" />
                    {t('settings')}
                  </DropdownMenuItem>
                </Link>
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
    </Sidebar>
  )
}
