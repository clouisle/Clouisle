'use client'

import * as React from 'react'
import { usePathname, useRouter } from 'next/navigation'
import { useTranslations } from 'next-intl'
import {
  Activity,
  BarChart3,
  Bell,
  Brain,
  Database,
  FileText,
  Key,
  KeyRound,
  LayoutDashboard,
  Palette,
  Search,
  Settings,
  Shield,
  Users,
  UsersRound,
  Wrench,
  Bot,
} from 'lucide-react'

import { SidebarTrigger } from '@/components/ui/sidebar'
import { Separator } from '@/components/ui/separator'
import { Input } from '@/components/ui/input'
import { SettingsDrawer } from '@/components/settings-drawer'
import { canAccessRoute } from '@/lib/route-permissions'
import { usePermissions } from '@/hooks/use-permissions'

type SearchTranslationNamespace = 'nav' | 'dashboard' | 'siteSettings' | 'activities' | 'tools' | 'models' | 'auditLogs' | 'sso' | 'common'

type SearchTranslationKey = `${SearchTranslationNamespace}:${string}`

interface SearchRouteItem {
  titleKey: SearchTranslationKey
  url: string
  icon: React.ElementType
  parentKey?: SearchTranslationKey
  keywords?: string[]
}

const SEARCHABLE_DASHBOARD_ROUTES: SearchRouteItem[] = [
  { titleKey: 'nav:dashboard', url: '/dashboard', icon: LayoutDashboard },
  { titleKey: 'dashboard:tabs.overview', url: '/dashboard?tab=overview', icon: LayoutDashboard, parentKey: 'nav:dashboard', keywords: ['overview'] },
  { titleKey: 'dashboard:tabs.models', url: '/dashboard?tab=models', icon: BarChart3, parentKey: 'nav:dashboard', keywords: ['models', 'usage', 'tokens'] },
  { titleKey: 'dashboard:tabs.analytics', url: '/dashboard?tab=analytics', icon: BarChart3, parentKey: 'nav:dashboard', keywords: ['analytics', 'workflow'] },
  { titleKey: 'nav:teams', url: '/teams', icon: UsersRound, keywords: ['default team', 'team members'] },
  { titleKey: 'nav:knowledgeBases', url: '/knowledge-bases', icon: Database, keywords: ['kb', 'documents', 'search test'] },
  { titleKey: 'nav:activities', url: '/activities', icon: Activity },
  { titleKey: 'activities:conversations', url: '/activities', icon: Activity, parentKey: 'nav:activities', keywords: ['chat history', 'conversation logs'] },
  { titleKey: 'activities:workflowRuns', url: '/activities', icon: Activity, parentKey: 'nav:activities', keywords: ['workflow runs', 'run history'] },
  { titleKey: 'activities:filters.status', url: '/activities', icon: Activity, parentKey: 'nav:activities', keywords: ['success', 'failed', 'running', 'pending', 'cancelled', 'timeout'] },
  { titleKey: 'activities:filters.triggerType', url: '/activities', icon: Activity, parentKey: 'nav:activities', keywords: ['manual', 'webhook', 'cron'] },
  { titleKey: 'nav:users', url: '/users', icon: Users, keywords: ['user status', 'roles', '2fa', 'totp'] },
  { titleKey: 'nav:roles', url: '/roles', icon: Shield, keywords: ['system roles', 'permissions'] },
  { titleKey: 'nav:permissions', url: '/permissions', icon: Key, keywords: ['permission scope', 'access control'] },
  { titleKey: 'nav:models', url: '/models', icon: Bot },
  { titleKey: 'models:provider', url: '/models', icon: Bot, parentKey: 'nav:models', keywords: ['provider filter'] },
  { titleKey: 'models:modelType', url: '/models', icon: Bot, parentKey: 'nav:models', keywords: ['model type', 'chat', 'embedding'] },
  { titleKey: 'models:testConnection', url: '/models', icon: Bot, parentKey: 'nav:models', keywords: ['test model', 'connection'] },
  { titleKey: 'nav:tools', url: '/tools', icon: Wrench },
  { titleKey: 'tools:createMenu.http', url: '/tools', icon: Wrench, parentKey: 'nav:tools', keywords: ['http tool', 'api tool'] },
  { titleKey: 'tools:createMenu.code', url: '/tools/code', icon: Wrench, parentKey: 'nav:tools', keywords: ['code tool', 'python', 'runtime'] },
  { titleKey: 'tools:createMenu.mcp', url: '/tools', icon: Wrench, parentKey: 'nav:tools', keywords: ['mcp server'] },
  { titleKey: 'tools:filters.builtin', url: '/tools', icon: Wrench, parentKey: 'nav:tools', keywords: ['builtin tools'] },
  { titleKey: 'tools:filters.custom', url: '/tools', icon: Wrench, parentKey: 'nav:tools', keywords: ['custom tools'] },
  { titleKey: 'nav:apiKeys', url: '/api-keys', icon: KeyRound, keywords: ['token', 'secret key'] },
  { titleKey: 'nav:memories', url: '/memories', icon: Brain, keywords: ['memory entities', 'agent memory'] },
  { titleKey: 'nav:notifications', url: '/notifications', icon: Bell, keywords: ['message delivery', 'announcement'] },
  { titleKey: 'nav:auditLogs', url: '/audit-logs', icon: FileText },
  { titleKey: 'auditLogs:exportCSV', url: '/audit-logs', icon: FileText, parentKey: 'nav:auditLogs', keywords: ['csv'] },
  { titleKey: 'auditLogs:exportJSON', url: '/audit-logs', icon: FileText, parentKey: 'nav:auditLogs', keywords: ['json'] },
  { titleKey: 'nav:siteSettings', url: '/site-settings', icon: Settings },
  { titleKey: 'siteSettings:general', url: '/site-settings', icon: Settings, parentKey: 'nav:siteSettings' },
  { titleKey: 'siteSettings:siteInfo', url: '/site-settings', icon: Settings, parentKey: 'siteSettings:general' },
  { titleKey: 'siteSettings:siteBranding', url: '/site-settings', icon: Settings, parentKey: 'siteSettings:general' },
  { titleKey: 'siteSettings:defaultLanguage', url: '/site-settings', icon: Settings, parentKey: 'siteSettings:general' },
  { titleKey: 'siteSettings:security', url: '/site-settings/security', icon: Shield, parentKey: 'nav:siteSettings' },
  { titleKey: 'siteSettings:registration', url: '/site-settings/security', icon: Shield, parentKey: 'siteSettings:security' },
  { titleKey: 'siteSettings:passwordPolicy', url: '/site-settings/security', icon: Shield, parentKey: 'siteSettings:security' },
  { titleKey: 'siteSettings:passwordExpiration', url: '/site-settings/security', icon: Shield, parentKey: 'siteSettings:security' },
  { titleKey: 'siteSettings:sessionSettings', url: '/site-settings/security', icon: Shield, parentKey: 'siteSettings:security' },
  { titleKey: 'siteSettings:loginSecurity', url: '/site-settings/security', icon: Shield, parentKey: 'siteSettings:security' },
  { titleKey: 'siteSettings:twoFactorAuthentication', url: '/site-settings/security', icon: Shield, parentKey: 'siteSettings:security', keywords: ['2fa', 'totp', 'mfa'] },
  { titleKey: 'siteSettings:ssoSettings', url: '/site-settings/security', icon: Shield, parentKey: 'siteSettings:security', keywords: ['single sign on'] },
  { titleKey: 'siteSettings:notifications.title', url: '/site-settings/notifications', icon: Bell, parentKey: 'nav:siteSettings' },
  { titleKey: 'siteSettings:autoNotifications.tab', url: '/site-settings/notifications', icon: Bell, parentKey: 'siteSettings:notifications.title' },
  { titleKey: 'siteSettings:notifications.email', url: '/site-settings/notifications', icon: Bell, parentKey: 'siteSettings:notifications.title' },
  { titleKey: 'siteSettings:notifications.dingtalk', url: '/site-settings/notifications', icon: Bell, parentKey: 'siteSettings:notifications.title' },
  { titleKey: 'siteSettings:notifications.wechat', url: '/site-settings/notifications', icon: Bell, parentKey: 'siteSettings:notifications.title' },
  { titleKey: 'siteSettings:notifications.feishu', url: '/site-settings/notifications', icon: Bell, parentKey: 'siteSettings:notifications.title' },
  { titleKey: 'siteSettings:notifications.webhook', url: '/site-settings/notifications', icon: Bell, parentKey: 'siteSettings:notifications.title' },
  { titleKey: 'siteSettings:notifications.slack', url: '/site-settings/notifications', icon: Bell, parentKey: 'siteSettings:notifications.title' },
  { titleKey: 'siteSettings:storage', url: '/site-settings/storage', icon: Database, parentKey: 'nav:siteSettings' },
  { titleKey: 'siteSettings:auditLogStorage', url: '/site-settings/storage', icon: Database, parentKey: 'siteSettings:storage' },
  { titleKey: 'siteSettings:manualArchive', url: '/site-settings/storage', icon: Database, parentKey: 'siteSettings:storage' },
  { titleKey: 'siteSettings:sso', url: '/site-settings/sso', icon: Shield, parentKey: 'nav:siteSettings' },
  { titleKey: 'sso:addProvider', url: '/site-settings/sso', icon: Shield, parentKey: 'siteSettings:sso' },
  { titleKey: 'sso:testConnection', url: '/site-settings/sso', icon: Shield, parentKey: 'siteSettings:sso' },
]

export function Header() {
  const t = useTranslations('common')
  const tNav = useTranslations('nav')
  const tDashboard = useTranslations('dashboard')
  const tSiteSettings = useTranslations('siteSettings')
  const tActivities = useTranslations('activities')
  const tTools = useTranslations('tools')
  const tModels = useTranslations('models')
  const tAuditLogs = useTranslations('auditLogs')
  const tSso = useTranslations('sso')
  const router = useRouter()
  const pathname = usePathname()
  const { hasPermission, isSuperuser } = usePermissions()
  const [settingsOpen, setSettingsOpen] = React.useState(false)
  const [searchQuery, setSearchQuery] = React.useState('')
  const [searchOpen, setSearchOpen] = React.useState(false)

  const translateSearchKey = React.useCallback((key: SearchTranslationKey) => {
    const [namespace, translationKey] = key.split(':') as [SearchTranslationNamespace, string]
    const translators = {
      nav: tNav,
      dashboard: tDashboard,
      siteSettings: tSiteSettings,
      activities: tActivities,
      tools: tTools,
      models: tModels,
      auditLogs: tAuditLogs,
      sso: tSso,
      common: t,
    }
    const translator = translators[namespace]
    return translator.has(translationKey) ? translator(translationKey) : translationKey
  }, [t, tActivities, tAuditLogs, tDashboard, tModels, tNav, tSiteSettings, tSso, tTools])

  const accessibleRoutes = React.useMemo(
    () => SEARCHABLE_DASHBOARD_ROUTES.filter((item) => canAccessRoute(item.url.split('?')[0], hasPermission, isSuperuser)),
    [hasPermission, isSuperuser]
  )
  const normalizedQuery = searchQuery.trim().toLowerCase()
  const filteredRoutes = normalizedQuery
    ? accessibleRoutes.filter((item) => {
      const searchableText = [
        translateSearchKey(item.titleKey),
        item.parentKey ? translateSearchKey(item.parentKey) : '',
        item.url,
        ...(item.keywords || []),
      ].join(' ').toLowerCase()
      return searchableText.includes(normalizedQuery)
    })
    : accessibleRoutes
  const currentSearchRoute = accessibleRoutes.find((item) => pathname === item.url.split('?')[0])

  const navigateToSearch = (url: string) => {
    const query = searchQuery.trim()
    if (!query) return

    const [path, existingQuery] = url.split('?')
    const params = new URLSearchParams(existingQuery)
    params.set('search', query)
    router.push(`${path}?${params.toString()}`)
    setSearchOpen(false)
  }

  const handleSearchKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key !== 'Enter') return

    const targetRoute = currentSearchRoute || filteredRoutes[0]
    if (targetRoute) {
      navigateToSearch(targetRoute.url)
    }
  }

  return (
    <header className="sticky top-0 z-40 flex h-12 shrink-0 items-center gap-2 bg-background px-4 md:rounded-t-xl">
      <SidebarTrigger 
        className="-ms-1 size-8 border border-border rounded-md" 
        title={t('toggleSidebar')}
      />
      <Separator orientation="vertical" className="h-6! self-center! mx-2" />
      
      {/* Search */}
      <div
        className="relative w-64"
        onBlur={(event) => {
          if (!event.currentTarget.contains(event.relatedTarget)) {
            setSearchOpen(false)
          }
        }}
      >
        <Search className="absolute start-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
        <Input
          type="search"
          value={searchQuery}
          placeholder={`${t('search')}...`}
          className="w-full h-8 ps-7 text-sm"
          onChange={(event) => {
            setSearchQuery(event.target.value)
            setSearchOpen(true)
          }}
          onFocus={() => setSearchOpen(true)}
          onKeyDown={handleSearchKeyDown}
        />

        {searchOpen && searchQuery.trim().length > 0 && (
          <div className="absolute start-0 top-full z-50 mt-1 w-80 rounded-md border bg-popover p-1 text-popover-foreground shadow-md">
            {filteredRoutes.length > 0 ? (
              <div className="max-h-80 overflow-y-auto">
                {filteredRoutes.map((item) => {
                  const Icon = item.icon
                  return (
                    <button
                      key={`${item.url}-${item.titleKey}`}
                      type="button"
                      className="flex w-full items-center gap-2 rounded-sm px-2 py-2 text-left text-sm hover:bg-muted"
                      onMouseDown={(event) => event.preventDefault()}
                      onClick={() => navigateToSearch(item.url)}
                    >
                      <Icon className="h-4 w-4 text-muted-foreground" />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate">{translateSearchKey(item.titleKey)}</span>
                        {item.parentKey && (
                          <span className="block truncate text-xs text-muted-foreground">
                            {translateSearchKey(item.parentKey)}
                          </span>
                        )}
                      </span>
                      <span className="text-xs text-muted-foreground">{item.url}</span>
                    </button>
                  )
                })}
              </div>
            ) : (
              <div className="px-2 py-6 text-center text-sm text-muted-foreground">
                {t('noResults')}
              </div>
            )}
          </div>
        )}
      </div>

      <div className="ms-auto flex items-center gap-1.5">
        {/* Appearance Settings */}
        <button
          onClick={() => setSettingsOpen(true)}
          className="rounded-md hover:bg-muted text-muted-foreground hover:text-foreground size-8 inline-flex items-center justify-center transition-colors cursor-pointer"
          title={t('appearanceSettings')}
        >
          <Palette className="h-4 w-4" />
        </button>
      </div>

      <SettingsDrawer open={settingsOpen} onOpenChange={setSettingsOpen} />
    </header>
  )
}
