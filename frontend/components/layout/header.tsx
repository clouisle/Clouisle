'use client'

import * as React from 'react'
import { usePathname, useRouter } from 'next/navigation'
import { useTranslations } from 'next-intl'
import {
  Activity,
  Bell,
  Brain,
  Database,
  FileText,
  Key,
  KeyRound,
  Palette,
  Search,
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

const SEARCHABLE_DASHBOARD_ROUTES = [
  { titleKey: 'teams', url: '/teams', icon: UsersRound },
  { titleKey: 'knowledgeBases', url: '/knowledge-bases', icon: Database },
  { titleKey: 'activities', url: '/activities', icon: Activity },
  { titleKey: 'users', url: '/users', icon: Users },
  { titleKey: 'roles', url: '/roles', icon: Shield },
  { titleKey: 'permissions', url: '/permissions', icon: Key },
  { titleKey: 'models', url: '/models', icon: Bot },
  { titleKey: 'tools', url: '/tools', icon: Wrench },
  { titleKey: 'apiKeys', url: '/api-keys', icon: KeyRound },
  { titleKey: 'memories', url: '/memories', icon: Brain },
  { titleKey: 'notifications', url: '/notifications', icon: Bell },
  { titleKey: 'auditLogs', url: '/audit-logs', icon: FileText },
] as const

export function Header() {
  const t = useTranslations('common')
  const tNav = useTranslations('nav')
  const router = useRouter()
  const pathname = usePathname()
  const { hasPermission, isSuperuser } = usePermissions()
  const [settingsOpen, setSettingsOpen] = React.useState(false)
  const [searchQuery, setSearchQuery] = React.useState('')
  const [searchOpen, setSearchOpen] = React.useState(false)

  const accessibleRoutes = React.useMemo(
    () => SEARCHABLE_DASHBOARD_ROUTES.filter((item) => canAccessRoute(item.url, hasPermission, isSuperuser)),
    [hasPermission, isSuperuser]
  )
  const normalizedQuery = searchQuery.trim().toLowerCase()
  const filteredRoutes = normalizedQuery
    ? accessibleRoutes.filter((item) => tNav(item.titleKey).toLowerCase().includes(normalizedQuery) || item.url.includes(normalizedQuery))
    : accessibleRoutes
  const currentSearchRoute = accessibleRoutes.find((item) => pathname === item.url)

  const navigateToSearch = (url: string) => {
    const query = searchQuery.trim()
    if (!query) return

    const params = new URLSearchParams()
    params.set('search', query)
    router.push(`${url}?${params.toString()}`)
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
                      key={item.url}
                      type="button"
                      className="flex w-full items-center gap-2 rounded-sm px-2 py-2 text-left text-sm hover:bg-muted"
                      onMouseDown={(event) => event.preventDefault()}
                      onClick={() => navigateToSearch(item.url)}
                    >
                      <Icon className="h-4 w-4 text-muted-foreground" />
                      <span className="flex-1">{tNav(item.titleKey)}</span>
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
