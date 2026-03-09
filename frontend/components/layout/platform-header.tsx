'use client'

import * as React from 'react'
import Link from 'next/link'
import Image from 'next/image'
import { usePathname, useRouter } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { toast } from 'sonner'
import {
  Bot,
  Database,
  Wrench,
  Home,
  LayoutDashboard,
  LogOut,
  Palette,
  AppWindow,
  Info,
  Settings,
  Bell,
  Brain,
  Menu,
  X,
  Key,
} from 'lucide-react'
import { authApi, type User as UserType } from '@/lib/api'
import { notificationsApi } from '@/lib/api'
import { useSiteSettings } from '@/contexts/site-settings-context'
import { usePermissions } from '@/hooks/use-permissions'
import { useTeam } from '@/contexts/team-context'

import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { SettingsDrawer } from '@/components/settings-drawer'
import { SettingsDialog } from '@/components/settings-dialog'
import { TeamSwitcher } from '@/components/team-switcher'
import { useSettings } from '@/hooks/use-settings'
import { cn, formatDateTime } from '@/lib/utils'
import { APP_VERSION, BUILD_DATE, APP_NAME, GITHUB_URL, DOCS_URL, CHANGELOG_URL } from '@/lib/constants'
import { DefaultSiteIcon } from '@/components/default-site-icon'

const navItems = [
  {
    key: 'home',
    href: '/app',
    icon: Home,
    exact: true,
  },
  {
    key: 'apps',
    href: '/app/apps',
    icon: AppWindow,
  },
  {
    key: 'kb',
    href: '/app/kb',
    icon: Database,
  },
  {
    key: 'tools',
    href: '/app/tools',
    icon: Wrench,
  },
  {
    key: 'models',
    href: '/app/models',
    icon: Bot,
  },
]

export function PlatformHeader() {
  const t = useTranslations('platform')
  const tCommon = useTranslations('common')
  const pathname = usePathname()
  const router = useRouter()
  const [user, setUser] = React.useState<UserType | null>(null)
  const [unreadCount, setUnreadCount] = React.useState(0)
  const [settingsOpen, setSettingsOpen] = React.useState(false)
  const [profileOpen, setProfileOpen] = React.useState(false)
  const [aboutOpen, setAboutOpen] = React.useState(false)
  const [mobileMenuOpen, setMobileMenuOpen] = React.useState(false)
  const { settings: siteSettings } = useSiteSettings()
  const { platformHeaderVariant, mounted } = useSettings()
  const { canAccessDashboard } = usePermissions()
  const { currentTeam, isLoading: isTeamLoading } = useTeam()

  // 没有团队时隐藏导航
  const hideNav = !isTeamLoading && !currentTeam

  // 使用默认值直到 mounted，避免水合不匹配
  const effectiveHeaderVariant = mounted ? platformHeaderVariant : 'centered'

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

  const [prevUnreadCount, setPrevUnreadCount] = React.useState(0)

  const fetchUnread = React.useCallback(async () => {
    try {
      const data = await notificationsApi.unreadCount({ silent: true, skipAuthRedirect: true })
      setUnreadCount(data.total)
    } catch {
      // 忽略读取失败，不触发重定向
    }
  }, [])

  // 请求浏览器通知权限（在用户交互时调用）
  const requestNotificationPermission = React.useCallback(async () => {
    if ('Notification' in window && Notification.permission === 'default') {
      await Notification.requestPermission()
    }
  }, [])

  // 检测新通知并发送浏览器通知
  React.useEffect(() => {
    if (unreadCount > prevUnreadCount && prevUnreadCount > 0) {
      // 有新通知
      const newCount = unreadCount - prevUnreadCount
      if ('Notification' in window && Notification.permission === 'granted') {
        // 浏览器通知需要完整的 URL
        const iconUrl = siteSettings.site_icon
          ? (siteSettings.site_icon.startsWith('http') ? siteSettings.site_icon : `${window.location.origin}${siteSettings.site_icon}`)
          : `${window.location.origin}/clouisle-dark.svg`
        const notification = new Notification(siteSettings.site_name || 'Clouisle', {
          body: t('newNotifications', { count: newCount }),
          icon: iconUrl,
        })
        // 点击通知跳转到通知页面
        notification.onclick = () => {
          window.focus()
          router.push('/app/notifications')
          notification.close()
        }
      }
    }
    setPrevUnreadCount(unreadCount)
  }, [unreadCount, prevUnreadCount, siteSettings.site_name, siteSettings.site_icon, t, router])

  React.useEffect(() => {
    fetchUnread()
  }, [fetchUnread, pathname])

  // 轮询未读通知数量（每 30 秒）
  React.useEffect(() => {
    const interval = setInterval(fetchUnread, 30000)
    return () => clearInterval(interval)
  }, [fetchUnread])

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

  const isActive = (href: string, exact?: boolean) =>
    exact ? pathname === href : pathname.startsWith(href)

  return (
    <header className="sticky top-0 z-50 w-full border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="container flex h-14 max-w-screen-2xl items-center justify-between px-4 sm:px-8">
        {/* Left Side - Logo and Team Switcher */}
        <div className="flex items-center gap-2 sm:gap-3 min-w-0 flex-1 sm:flex-initial">
          {/* Logo */}
          <Link href="/app" className="flex items-center space-x-2 shrink-0">
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
          </Link>

          {/* Separator and Team Switcher - 没有团队时隐藏 */}
          {!hideNav && (
            <>
              <span className="text-muted-foreground/40 text-xl font-light select-none hidden sm:inline">/</span>
              <div className="min-w-0 flex-1 sm:flex-initial">
                <TeamSwitcher />
              </div>
            </>
          )}
        </div>

        {/* Desktop Navigation - 根据布局变体调整位置，没有团队时隐藏 */}
        {!hideNav && (
          <nav className={cn(
            'hidden md:flex items-center gap-1',
            effectiveHeaderVariant === 'centered' && 'absolute left-1/2 -translate-x-1/2',
            effectiveHeaderVariant === 'default' && 'ml-6'
          )}>
            {navItems.map((item) => {
              const Icon = item.icon
              return (
                <Link key={item.key} href={item.href}>
                  <Button
                    variant={isActive(item.href, 'exact' in item ? item.exact : false) ? 'secondary' : 'ghost'}
                    size="sm"
                    className="gap-2 cursor-pointer relative"
                  >
                    <Icon className="size-4" />
                    {/* 极简模式只显示图标 */}
                    {effectiveHeaderVariant !== 'minimal' && (
                      <span>{t(`nav.${item.key}`)}</span>
                    )}
                    {item.key === 'notifications' && unreadCount > 0 && (
                      <span className="absolute -top-1 -right-1 inline-flex min-w-4 items-center justify-center rounded-full bg-destructive px-1 text-[10px] text-destructive-foreground">
                        {unreadCount > 99 ? '99+' : unreadCount}
                      </span>
                    )}
                  </Button>
                </Link>
              )
            })}
          </nav>
        )}

        {/* Spacer for default layout */}
        {effectiveHeaderVariant === 'default' && <div className="flex-1 hidden md:block" />}

        {/* Right Side Actions */}
        <div className="flex items-center gap-1 sm:gap-2 shrink-0">
          {/* Mobile Menu Toggle - 没有团队时隐藏 */}
          {!hideNav && (
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 cursor-pointer md:hidden"
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            >
              {mobileMenuOpen ? <X className="h-4 w-4" /> : <Menu className="h-4 w-4" />}
              <span className="sr-only">{mobileMenuOpen ? tCommon('close') : tCommon('menu')}</span>
            </Button>
          )}

          {/* Settings Drawer Toggle */}
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8 cursor-pointer"
            onClick={() => setSettingsOpen(true)}
          >
            <Palette className="h-4 w-4" />
            <span className="sr-only">{tCommon('appearanceSettings')}</span>
          </Button>

          {/* User Menu */}
          <DropdownMenu>
            <DropdownMenuTrigger
              render={(props) => (
                <Button {...props} variant="ghost" className="relative h-8 w-8 rounded-full">
                  <Avatar className="h-8 w-8">
                    <AvatarImage src={user?.avatar_url || undefined} alt={user?.username || 'User'} />
                    <AvatarFallback>
                      {user ? getInitials(user.username) : 'U'}
                    </AvatarFallback>
                  </Avatar>
                  {unreadCount > 0 && (
                    <span className="absolute -top-1 -right-1 inline-flex min-w-4 items-center justify-center rounded-full bg-destructive px-1 text-[10px] text-white">
                      {unreadCount > 99 ? '99+' : unreadCount}
                    </span>
                  )}
                </Button>
              )}
            />
            <DropdownMenuContent align="end" className="w-56">
              {/* User Info */}
              <div className="flex items-center justify-start gap-2 p-2">
                <div className="flex flex-col space-y-1 leading-none">
                  {user?.username && <p className="font-medium">{user.username}</p>}
                  {user?.email && (
                    <p className="w-auto truncate text-sm text-muted-foreground">
                      {user.email}
                    </p>
                  )}
                </div>
              </div>
              <DropdownMenuSeparator />

              {/* Account Settings */}
              <DropdownMenuItem onClick={() => setProfileOpen(true)}>
                <Settings className="mr-2 h-4 w-4" />
                {t('profile.title')}
              </DropdownMenuItem>

              {/* API Keys */}
              <DropdownMenuItem onClick={() => router.push('/app/api-keys')}>
                <Key className="mr-2 h-4 w-4" />
                {t('apiKeys')}
              </DropdownMenuItem>
              <DropdownMenuSeparator />

              {/* Features */}
              <DropdownMenuItem
                onClick={() => {
                  requestNotificationPermission()
                  router.push('/app/notifications')
                }}
              >
                <Bell className="mr-2 h-4 w-4" />
                {t('nav.notifications')}
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => router.push('/app/memories')}>
                <Brain className="mr-2 h-4 w-4" />
                {t('nav.memories')}
              </DropdownMenuItem>

              {/* Admin Access */}
              {canAccessDashboard && (
                <>
                  <DropdownMenuSeparator />
                  <Link href="/dashboard">
                    <DropdownMenuItem>
                      <LayoutDashboard className="mr-2 h-4 w-4" />
                      {t('admin')}
                    </DropdownMenuItem>
                  </Link>
                </>
              )}

              {/* System */}
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={() => setAboutOpen(true)}>
                <Info className="mr-2 h-4 w-4" />
                {t('about')}
              </DropdownMenuItem>
              <DropdownMenuItem onClick={handleLogout}>
                <LogOut className="mr-2 h-4 w-4" />
                {t('logout')}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>

      {/* Mobile Navigation Menu */}
      {!hideNav && mobileMenuOpen && (
        <div className="md:hidden border-t bg-background">
          <nav className="container max-w-screen-2xl px-4 py-2 space-y-1">
            {navItems.map((item) => {
              const Icon = item.icon
              return (
                <Link key={item.key} href={item.href} onClick={() => setMobileMenuOpen(false)}>
                  <Button
                    variant={isActive(item.href, 'exact' in item ? item.exact : false) ? 'secondary' : 'ghost'}
                    size="sm"
                    className="w-full justify-start gap-2 cursor-pointer relative"
                  >
                    <Icon className="size-4" />
                    <span>{t(`nav.${item.key}`)}</span>
                    {item.key === 'notifications' && unreadCount > 0 && (
                      <span className="ml-auto inline-flex min-w-4 items-center justify-center rounded-full bg-destructive px-1 text-[10px] text-destructive-foreground">
                        {unreadCount > 99 ? '99+' : unreadCount}
                      </span>
                    )}
                  </Button>
                </Link>
              )
            })}
          </nav>
        </div>
      )}

      {/* Settings Drawer */}
      <SettingsDrawer open={settingsOpen} onOpenChange={setSettingsOpen} showSidebarStyle={false} showPlatformHeader={true} />

      {/* Profile Settings Dialog */}
      <SettingsDialog open={profileOpen} onOpenChange={setProfileOpen} />

      {/* About Dialog */}
      <Dialog open={aboutOpen} onOpenChange={setAboutOpen}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader className="sr-only">
            <DialogTitle>{t('about')}</DialogTitle>
            <DialogDescription>{t('aboutDescription')}</DialogDescription>
          </DialogHeader>
          
          <div className="flex flex-col items-center py-6">
            {/* Logo 和名称 */}
            <div className={`flex aspect-square size-10 items-center justify-center rounded-sm overflow-hidden mb-4 ${siteSettings.site_icon ? 'bg-primary text-primary-foreground' : ''}`}>
              {siteSettings.site_icon ? (
                <Image
                  src={siteSettings.site_icon}
                  alt={siteSettings.site_name}
                  width={64}
                  height={64}
                  className="size-full object-cover"
                  unoptimized
                />
              ) : (
                <DefaultSiteIcon width={64} height={64} className="size-full" />
              )}
            </div>
            
            <h2 className="text-2xl font-bold mb-1">
              {siteSettings.site_name || APP_NAME}
            </h2>
            
            <p className="text-sm text-muted-foreground mb-4">
              Version {APP_VERSION}
            </p>
            
            {/* 版权和链接 */}
            <p className="text-sm text-muted-foreground mb-2">
              © {new Date().getFullYear()} {APP_NAME}. {t('aboutRights')}
            </p>

            <p className="text-sm text-muted-foreground mb-4">
              {t('aboutBuildDate')}: {BUILD_DATE !== 'dev' ? formatDateTime(BUILD_DATE) : BUILD_DATE}
            </p>
            
            <div className="flex items-center gap-1 text-sm">
              <a 
                href={GITHUB_URL}
                target="_blank" 
                rel="noopener noreferrer"
                className="text-primary hover:underline"
              >
                GitHub
              </a>
              <span className="text-muted-foreground">,</span>
              <a 
                href={DOCS_URL}
                target="_blank" 
                rel="noopener noreferrer"
                className="text-primary hover:underline"
              >
                {t('aboutDocs')}
              </a>
            </div>
          </div>
          
          {/* 底部 */}
          <div className="flex items-center justify-between border-t pt-4">
            <p className="text-sm text-muted-foreground">
              {APP_NAME} {APP_VERSION}
            </p>
            <a
              href={CHANGELOG_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center justify-center whitespace-nowrap rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring border border-input bg-background shadow-xs hover:bg-accent hover:text-accent-foreground h-8 px-3"
            >
              {t('aboutChangelog')}
            </a>
          </div>
        </DialogContent>
      </Dialog>
    </header>
  )
}
