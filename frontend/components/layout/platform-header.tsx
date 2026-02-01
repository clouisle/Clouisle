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
  Grid3x3,
  Home,
  LayoutDashboard,
  LogOut,
  User,
  Palette,
  AppWindow,
  Info,
  Github,
  ExternalLink,
} from 'lucide-react'
import { authApi, type User as UserType } from '@/lib/api'
import { useSiteSettings } from '@/contexts/site-settings-context'

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
import { TeamSwitcher } from '@/components/team-switcher'
import { useSettings } from '@/hooks/use-settings'
import { cn } from '@/lib/utils'
import { APP_VERSION, BUILD_DATE, APP_NAME, GITHUB_URL, DOCS_URL, CHANGELOG_URL } from '@/lib/constants'

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
  const [settingsOpen, setSettingsOpen] = React.useState(false)
  const [aboutOpen, setAboutOpen] = React.useState(false)
  const { settings: siteSettings } = useSiteSettings()
  const { platformHeaderVariant, mounted } = useSettings()

  // 使用默认值直到 mounted，避免水合不匹配
  const effectiveHeaderVariant = mounted ? platformHeaderVariant : 'centered'

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

  const isActive = (href: string, exact?: boolean) => 
    exact ? pathname === href : pathname.startsWith(href)

  return (
    <header className="sticky top-0 z-50 w-full border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="container flex h-14 max-w-screen-2xl items-center justify-between px-8">
        {/* Left Side - Logo and Team Switcher */}
        <div className="flex items-center gap-3">
          {/* Logo */}
          <Link href="/app" className="flex items-center space-x-2">
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
                <Grid3x3 className="size-5" />
              )}
            </div>
          </Link>

          {/* Separator */}
          <span className="text-muted-foreground/40 text-xl font-light select-none">/</span>

          {/* Team Switcher */}
          <TeamSwitcher />
        </div>

        {/* Navigation - 根据布局变体调整位置 */}
        <nav className={cn(
          'flex items-center gap-1',
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
                  className="gap-2 cursor-pointer"
                >
                  <Icon className="size-4" />
                  {/* 极简模式只显示图标 */}
                  {effectiveHeaderVariant !== 'minimal' && (
                    <span className="hidden sm:inline">{t(`nav.${item.key}`)}</span>
                  )}
                </Button>
              </Link>
            )
          })}
        </nav>

        {/* Spacer for default layout */}
        {effectiveHeaderVariant === 'default' && <div className="flex-1" />}

        {/* Right Side Actions */}
        <div className="flex items-center gap-2">
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
                </Button>
              )}
            />
            <DropdownMenuContent align="end" className="w-56">
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
              <Link href="/app/settings/profile">
                <DropdownMenuItem>
                  <User className="mr-2 h-4 w-4" />
                  {t('profile.title')}
                </DropdownMenuItem>
              </Link>
              <DropdownMenuSeparator />
              <Link href="/dashboard">
                <DropdownMenuItem>
                  <LayoutDashboard className="mr-2 h-4 w-4" />
                  {t('admin')}
                </DropdownMenuItem>
              </Link>
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={() => setAboutOpen(true)}>
                <Info className="mr-2 h-4 w-4" />
                {t('about')}
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={handleLogout}>
                <LogOut className="mr-2 h-4 w-4" />
                {t('logout')}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>

      {/* Settings Drawer */}
      <SettingsDrawer open={settingsOpen} onOpenChange={setSettingsOpen} showSidebarStyle={false} showPlatformHeader={true} />

      {/* About Dialog */}
      <Dialog open={aboutOpen} onOpenChange={setAboutOpen}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader className="sr-only">
            <DialogTitle>{t('about')}</DialogTitle>
            <DialogDescription>{t('aboutDescription')}</DialogDescription>
          </DialogHeader>
          
          <div className="flex flex-col items-center py-6">
            {/* Logo 和名称 */}
            <div className="flex aspect-square size-10 items-center justify-center rounded-sm bg-primary text-primary-foreground overflow-hidden mb-4">
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
                <Grid3x3 className="size-8" />
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
              Build In {BUILD_DATE}
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
              {APP_NAME} {APP_VERSION} {t('aboutLatest')}
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
