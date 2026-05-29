export type RouteMatchMode = 'exact' | 'prefix'

export interface RoutePermissionConfig {
  path: string
  permission: string | null
  requiresSuperuser?: boolean
  matchMode?: RouteMatchMode
  children?: RoutePermissionConfig[]
}

export interface SiteSettingsNavItem {
  path: string
  translationKey: string
  descriptionKey: string
  requiresSuperuser?: boolean
}

export const ROUTE_PERMISSION_CONFIG: RoutePermissionConfig[] = [
  { path: '/dashboard', permission: 'admin:dashboard:access' },
  { path: '/teams', permission: 'team:read' },
  { path: '/knowledge-bases', permission: 'admin:knowledge-base:read' },
  { path: '/activities', permission: 'conversation:read' },
  { path: '/users', permission: 'admin:user:read' },
  { path: '/roles', permission: 'admin:role:read' },
  { path: '/permissions', permission: 'admin:permission:read' },
  { path: '/models', permission: 'admin:model:read' },
  { path: '/capabilities', permission: 'admin:capability:read', matchMode: 'prefix' },
  { path: '/api-keys', permission: 'apikey:read' },
  { path: '/memories', permission: 'admin:memory:read' },
  { path: '/notifications', permission: 'admin:dashboard:access' },
  { path: '/audit-logs', permission: 'audit:read' },
  {
    path: '/site-settings',
    permission: 'admin:settings:read',
    matchMode: 'prefix',
    children: [
      { path: '/site-settings', permission: 'admin:settings:read' },
      { path: '/site-settings/security', permission: 'admin:settings:read' },
      { path: '/site-settings/notifications', permission: 'admin:settings:read' },
      { path: '/site-settings/storage', permission: 'admin:settings:read' },
      { path: '/site-settings/sso', permission: 'admin:sso:read' },
    ],
  },
]

export const SITE_SETTINGS_NAV_ITEMS: SiteSettingsNavItem[] = [
  {
    path: '/site-settings',
    translationKey: 'general',
    descriptionKey: 'generalDescription',
  },
  {
    path: '/site-settings/security',
    translationKey: 'security',
    descriptionKey: 'securityDescription',
  },
  {
    path: '/site-settings/notifications',
    translationKey: 'notifications.title',
    descriptionKey: 'notifications.description',
  },
  {
    path: '/site-settings/storage',
    translationKey: 'storage',
    descriptionKey: 'storageDescription',
  },
  {
    path: '/site-settings/sso',
    translationKey: 'sso',
    descriptionKey: 'ssoDescription',
  },
]

function flattenRouteConfigs(configs: RoutePermissionConfig[]): RoutePermissionConfig[] {
  return configs.flatMap((config) => [config, ...(config.children ? flattenRouteConfigs(config.children) : [])])
}

const FLAT_ROUTE_PERMISSION_CONFIG = flattenRouteConfigs(ROUTE_PERMISSION_CONFIG)

const ROUTE_PERMISSION_ENTRIES: Array<[string, string]> = FLAT_ROUTE_PERMISSION_CONFIG.flatMap((config) =>
  config.permission ? [[config.path, config.permission]] : []
)

export const ROUTE_PERMISSION_MAP: Record<string, string> = Object.fromEntries(ROUTE_PERMISSION_ENTRIES)

export function getRoutePermissionConfig(pathname: string): RoutePermissionConfig | null {
  return (
    FLAT_ROUTE_PERMISSION_CONFIG
      .filter((config) => {
        const matchMode = config.matchMode ?? 'exact'
        if (matchMode === 'exact') {
          return pathname === config.path
        }
        return pathname === config.path || pathname.startsWith(`${config.path}/`)
      })
      .sort((a, b) => b.path.length - a.path.length)[0] ?? null
  )
}

export function getRequiredPermissionForPath(pathname: string): string | null {
  return getRoutePermissionConfig(pathname)?.permission ?? null
}

export function canAccessRoute(
  pathname: string,
  hasPermission: (permission: string) => boolean,
  isSuperuser = false
): boolean {
  const config = getRoutePermissionConfig(pathname)
  if (!config) {
    return true
  }
  if (config.requiresSuperuser && !isSuperuser) {
    return false
  }
  if (!config.permission) {
    return true
  }
  return hasPermission(config.permission)
}
