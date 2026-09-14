export type RouteMatchMode = 'exact' | 'prefix'
export type PermissionRequirement = string | string[]

export interface RoutePermissionConfig {
  path: string
  permission: PermissionRequirement | null
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
  { path: '/dashboard/observability', permission: 'admin:dashboard:access', matchMode: 'prefix' },
  { path: '/teams', permission: 'admin:team:read' },
  { path: '/knowledge-bases', permission: 'admin:knowledge-base:read' },
  { path: '/activities', permission: ['admin:conversation:read', 'workflow:read'] },
  { path: '/users', permission: 'admin:user:read' },
  { path: '/roles', permission: 'admin:role:read' },
  { path: '/permissions', permission: 'admin:permission:read' },
  { path: '/models', permission: 'admin:model:read' },
  { path: '/apps', permission: 'admin:app:read', matchMode: 'prefix' },
  { path: '/capabilities', permission: 'admin:capability:read', matchMode: 'prefix' },
  { path: '/api-keys', permission: 'apikey:read' },
  { path: '/app/api-keys', permission: 'apikey:read' },
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
      { path: '/site-settings/memory', permission: 'admin:settings:read' },
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
    path: '/site-settings/memory',
    translationKey: 'memory',
    descriptionKey: 'memoryDescription',
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

const ROUTE_PERMISSION_ENTRIES: Array<[string, PermissionRequirement]> = FLAT_ROUTE_PERMISSION_CONFIG.flatMap((config) =>
  config.permission ? [[config.path, config.permission] as const] : []
)

export const ROUTE_PERMISSION_MAP: Record<string, PermissionRequirement> = Object.fromEntries(ROUTE_PERMISSION_ENTRIES)

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
  const permission = getRoutePermissionConfig(pathname)?.permission
  return typeof permission === 'string' ? permission : permission?.[0] ?? null
}

const ADMIN_ROUTE_PREFIXES = [
  '/dashboard',
  '/teams',
  '/knowledge-bases',
  '/activities',
  '/users',
  '/roles',
  '/permissions',
  '/models',
  '/apps',
  '/capabilities',
  '/api-keys',
  '/memories',
  '/notifications',
  '/audit-logs',
  '/site-settings',
]

export function canAccessRoute(
  pathname: string,
  hasPermission: (permission: string) => boolean,
  isSuperuser = false
): boolean {
  const config = getRoutePermissionConfig(pathname)
  if (!config) {
    // Fail-closed for any unmapped admin-prefixed path
    const isAdminPath = ADMIN_ROUTE_PREFIXES.some(
      (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`)
    )
    if (isAdminPath) {
      return isSuperuser
    }
    return true
  }
  if (config.requiresSuperuser && !isSuperuser) {
    return false
  }
  if (!config.permission) {
    return true
  }
  if (Array.isArray(config.permission)) {
    return config.permission.every((permission) => hasPermission(permission))
  }
  return hasPermission(config.permission)
}
